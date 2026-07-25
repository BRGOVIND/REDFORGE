"""Artifact Registry — pure domain model (RedForge V3, Epic 2).

The Artifact is the **spine of the platform** (Constitution §6): the universal,
lineage-tracked unit of everything RedForge produces. Every stage's output is an
Artifact; every later stage consumes one. This module is pure — no SQLAlchemy, no
FastAPI, no I/O. Persistence is the repository's job; these objects never touch the
database or the filesystem.

Key modeling decisions (all per the Constitution, which governs where it and the
Epic's suggested entity list differ):
- **Versioning is artifacts-sharing-a-lineage** (§6.6): a new version is a new
  Artifact with the same ``lineage_id`` and an incremented ``version``, linked to
  its predecessor by a ``SUPERSEDES`` edge. There is no separate version table.
- **Lineage is a DAG** (§6.5): parent→child edges (``artifact_edges``), not a tree —
  a Merged Model has two parents (foundation + adapter).
- **Two backings** (§6.3): file-backed (bytes on disk) and data-backed (a row in an
  owning context's table, referenced — no data migration).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ArtifactStatus(str, Enum):
    """Lifecycle (Constitution §6.4). ``draft`` and ``invalid`` make production
    honest — a failed production is a first-class invalid artifact with a reason,
    not a missing row."""
    DRAFT = "draft"
    READY = "ready"
    INVALID = "invalid"
    ARCHIVED = "archived"


class RelationshipType(str, Enum):
    """Edge semantics in the lineage graph. Production edges (DERIVED_FROM /
    PRODUCED_FROM) form the provenance DAG; SUPERSEDES forms the version chain;
    CONSUMED records that an artifact was an input to producing another."""
    DERIVED_FROM = "derived_from"     # child was derived from parent (produced by a stage)
    PRODUCED_FROM = "produced_from"   # alias/explicit production edge
    SUPERSEDES = "supersedes"         # child is a newer version of parent
    CONSUMED = "consumed"             # parent was consumed as input to child
    CONTAINS = "contains"             # parent contains child (grouping)


# Edge relationship types that count as "production lineage" for ancestor/descendant
# traversal (as opposed to versioning, which uses SUPERSEDES).
PRODUCTION_RELATIONSHIPS = frozenset({
    RelationshipType.DERIVED_FROM, RelationshipType.PRODUCED_FROM, RelationshipType.CONSUMED,
})


def _coerce(enum_cls, value, default):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


@dataclass
class Checksum:
    algorithm: str = "sha256"
    value: str = ""

    def to_dict(self) -> Optional[dict]:
        return {"algorithm": self.algorithm, "value": self.value} if self.value else None


@dataclass
class ArtifactLocation:
    """Where an artifact's content lives. Exactly one backing is populated:
    file-backed → ``file_path``; data-backed → ``table``/``row_id``."""
    kind: str = "data"                       # "file" | "data"
    file_path: Optional[str] = None
    table: Optional[str] = None
    row_id: Optional[str] = None

    @property
    def is_file(self) -> bool:
        return self.kind == "file"

    def to_dict(self) -> dict:
        return {"kind": self.kind, "file_path": self.file_path,
                "table": self.table, "row_id": self.row_id}

    @staticmethod
    def file(path: str) -> "ArtifactLocation":
        return ArtifactLocation(kind="file", file_path=path)

    @staticmethod
    def data(table: str, row_id: str) -> "ArtifactLocation":
        return ArtifactLocation(kind="data", table=table, row_id=row_id)


@dataclass
class ArtifactReference:
    """A lightweight pointer to an artifact, used by consumers and lineage payloads."""
    id: str
    type: str
    name: str = ""
    version: int = 1
    status: str = ArtifactStatus.READY.value

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "name": self.name,
                "version": self.version, "status": self.status}


@dataclass
class ArtifactEdge:
    """A directed lineage edge (parent → child) with a typed relationship."""
    id: str
    parent_id: str
    child_id: str
    relationship: RelationshipType = RelationshipType.DERIVED_FROM
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "parent_id": self.parent_id, "child_id": self.child_id,
                "relationship": self.relationship.value, "metadata": self.metadata or {},
                "created_at": self.created_at.isoformat() if self.created_at else None}

    @staticmethod
    def coerce_relationship(value) -> RelationshipType:
        return _coerce(RelationshipType, value, RelationshipType.DERIVED_FROM)


@dataclass
class ArtifactLineage:
    """A computed view of an artifact's place in the DAG (returned by the lineage
    service — never persisted as a table; the edges are the source of truth)."""
    artifact_id: str
    ancestors: list[ArtifactReference] = field(default_factory=list)
    descendants: list[ArtifactReference] = field(default_factory=list)
    parents: list[ArtifactReference] = field(default_factory=list)
    children: list[ArtifactReference] = field(default_factory=list)
    edges: list[ArtifactEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "ancestors": [a.to_dict() for a in self.ancestors],
            "descendants": [d.to_dict() for d in self.descendants],
            "parents": [p.to_dict() for p in self.parents],
            "children": [c.to_dict() for c in self.children],
            "edges": [e.to_dict() for e in self.edges],
        }


@dataclass
class Artifact:
    """The universal produced unit. Identity is its ``id``; version identity is
    ``lineage_id`` (the version chain) + ``version``."""

    id: str
    type: str
    name: str
    status: ArtifactStatus = ArtifactStatus.DRAFT
    location: ArtifactLocation = field(default_factory=ArtifactLocation)
    producer: str = ""                                # e.g. "job:<id>", "user_import", "foundation_service"
    project_id: Optional[str] = None
    experiment_id: Optional[str] = None               # reserved for the Experiments epic (nullable)
    description: str = ""
    size_bytes: Optional[int] = None
    checksum: Optional[Checksum] = None
    tags: list[str] = field(default_factory=list)
    lineage_id: str = ""                              # stable version-chain id (defaults to id for v1)
    version: int = 1
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    archived_at: Optional[datetime] = None

    def as_reference(self) -> ArtifactReference:
        return ArtifactReference(id=self.id, type=self.type, name=self.name,
                                 version=self.version, status=self.status.value)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "name": self.name,
            "status": self.status.value, "location": self.location.to_dict(),
            "producer": self.producer, "project_id": self.project_id,
            "experiment_id": self.experiment_id, "description": self.description,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum.to_dict() if self.checksum else None,
            "tags": self.tags or [], "lineage_id": self.lineage_id or self.id,
            "version": self.version, "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }

    @staticmethod
    def coerce_status(value) -> ArtifactStatus:
        return _coerce(ArtifactStatus, value, ArtifactStatus.DRAFT)
