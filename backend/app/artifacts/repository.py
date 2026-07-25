"""Artifact Registry — repository layer (RedForge V3, Epic 2).

Dependency inversion (Constitution §4): services depend on these interfaces, never
on SQLAlchemy. The only place that knows ``ArtifactRecord`` / ``ArtifactEdgeRecord``
rows exist. Maps rows ↔ pure domain objects in both directions.

Three concerns, three interfaces:
- :class:`ArtifactRepository` — the artifact index (CRUD + search).
- :class:`ArtifactRelationshipRepository` — the lineage DAG edges.
- :class:`ArtifactVersionRepository` — version-chain queries (over the artifact
  index, keyed by ``lineage_id``; versioning is artifacts-sharing-a-lineage per
  Constitution §6.6, so this reads the same table through a versioning lens).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import and_, or_, select

from app.artifacts.domain import (
    Artifact,
    ArtifactEdge,
    ArtifactLocation,
    Checksum,
    RelationshipType,
)


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

class ArtifactRepository(ABC):
    @abstractmethod
    async def add(self, artifact: Artifact) -> Artifact: ...

    @abstractmethod
    async def get(self, artifact_id: str) -> Optional[Artifact]: ...

    @abstractmethod
    async def update(self, artifact: Artifact) -> Optional[Artifact]: ...

    @abstractmethod
    async def delete(self, artifact_id: str) -> bool: ...

    @abstractmethod
    async def search(self, *, type: Optional[str] = None, status: Optional[str] = None,
                     project_id: Optional[str] = None, experiment_id: Optional[str] = None,
                     tag: Optional[str] = None, query: Optional[str] = None,
                     limit: int = 200) -> list[Artifact]: ...

    @abstractmethod
    async def get_many(self, ids: list[str]) -> list[Artifact]: ...


class ArtifactRelationshipRepository(ABC):
    @abstractmethod
    async def add_edge(self, edge: ArtifactEdge) -> ArtifactEdge: ...

    @abstractmethod
    async def edges_from(self, parent_id: str) -> list[ArtifactEdge]: ...

    @abstractmethod
    async def edges_to(self, child_id: str) -> list[ArtifactEdge]: ...

    @abstractmethod
    async def delete_for_artifact(self, artifact_id: str) -> int: ...


class ArtifactVersionRepository(ABC):
    @abstractmethod
    async def list_versions(self, lineage_id: str) -> list[Artifact]: ...

    @abstractmethod
    async def next_version_number(self, lineage_id: str) -> int: ...


# ---------------------------------------------------------------------------
# SQL implementations
# ---------------------------------------------------------------------------

class _SessionMixin:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal


class SqlArtifactRepository(_SessionMixin, ArtifactRepository):

    @staticmethod
    def _to_domain(row) -> Artifact:
        checksum = None
        if row.checksum_value:
            checksum = Checksum(algorithm=row.checksum_algorithm or "sha256", value=row.checksum_value)
        return Artifact(
            id=row.id, type=row.type, name=row.name,
            status=Artifact.coerce_status(row.status),
            location=ArtifactLocation(kind=row.location_kind or "data", file_path=row.location_path,
                                      table=row.location_table, row_id=row.location_row_id),
            producer=row.producer or "", project_id=row.project_id, experiment_id=row.experiment_id,
            description=row.description or "", size_bytes=row.size_bytes, checksum=checksum,
            tags=list(row.tags or []), lineage_id=row.lineage_id or row.id, version=row.version or 1,
            metadata=dict(row.artifact_metadata or {}),
            created_at=row.created_at, updated_at=row.updated_at, archived_at=row.archived_at,
        )

    @staticmethod
    def _apply(row, a: Artifact) -> None:
        row.type = a.type
        row.name = a.name
        row.status = a.status.value
        row.producer = a.producer
        row.project_id = a.project_id
        row.experiment_id = a.experiment_id
        row.description = a.description
        row.location_kind = a.location.kind
        row.location_path = a.location.file_path
        row.location_table = a.location.table
        row.location_row_id = a.location.row_id
        row.size_bytes = a.size_bytes
        row.checksum_algorithm = a.checksum.algorithm if a.checksum else None
        row.checksum_value = a.checksum.value if a.checksum else None
        row.tags = a.tags or []
        row.lineage_id = a.lineage_id or a.id
        row.version = a.version
        row.artifact_metadata = a.metadata or {}
        row.archived_at = a.archived_at

    async def add(self, artifact: Artifact) -> Artifact:
        from app.db.models import ArtifactRecord
        if not artifact.lineage_id:
            artifact.lineage_id = artifact.id
        row = ArtifactRecord(id=artifact.id)
        self._apply(row, artifact)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, artifact_id: str) -> Optional[Artifact]:
        from app.db.models import ArtifactRecord
        async with self._factory()() as db:
            row = await db.get(ArtifactRecord, artifact_id)
            return self._to_domain(row) if row else None

    async def update(self, artifact: Artifact) -> Optional[Artifact]:
        from app.db.models import ArtifactRecord
        async with self._factory()() as db:
            row = await db.get(ArtifactRecord, artifact.id)
            if row is None:
                return None
            self._apply(row, artifact)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def delete(self, artifact_id: str) -> bool:
        from app.db.models import ArtifactRecord
        async with self._factory()() as db:
            row = await db.get(ArtifactRecord, artifact_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def search(self, *, type=None, status=None, project_id=None, experiment_id=None,
                     tag=None, query=None, limit: int = 200) -> list[Artifact]:
        from app.db.models import ArtifactRecord
        stmt = select(ArtifactRecord).order_by(ArtifactRecord.created_at.desc())
        if type is not None:
            stmt = stmt.where(ArtifactRecord.type == type)
        if status is not None:
            stmt = stmt.where(ArtifactRecord.status == status)
        if project_id is not None:
            stmt = stmt.where(ArtifactRecord.project_id == project_id)
        if experiment_id is not None:
            stmt = stmt.where(ArtifactRecord.experiment_id == experiment_id)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(ArtifactRecord.name.ilike(like),
                                  ArtifactRecord.description.ilike(like)))
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
        out = [self._to_domain(r) for r in rows]
        if tag:  # tags are a JSON list — filter in Python (portable across SQLite/PG)
            out = [a for a in out if tag in (a.tags or [])]
        return out

    async def get_many(self, ids: list[str]) -> list[Artifact]:
        from app.db.models import ArtifactRecord
        if not ids:
            return []
        async with self._factory()() as db:
            rows = (await db.execute(
                select(ArtifactRecord).where(ArtifactRecord.id.in_(ids)))).scalars().all()
        by_id = {r.id: self._to_domain(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]


class SqlArtifactRelationshipRepository(_SessionMixin, ArtifactRelationshipRepository):

    @staticmethod
    def _to_domain(row) -> ArtifactEdge:
        return ArtifactEdge(
            id=row.id, parent_id=row.parent_id, child_id=row.child_id,
            relationship=ArtifactEdge.coerce_relationship(row.relationship),
            metadata=dict(row.edge_metadata or {}), created_at=row.created_at,
        )

    async def add_edge(self, edge: ArtifactEdge) -> ArtifactEdge:
        from app.db.models import ArtifactEdgeRecord
        row = ArtifactEdgeRecord(
            id=edge.id, parent_id=edge.parent_id, child_id=edge.child_id,
            relationship=edge.relationship.value, edge_metadata=edge.metadata or {},
        )
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def edges_from(self, parent_id: str) -> list[ArtifactEdge]:
        from app.db.models import ArtifactEdgeRecord
        async with self._factory()() as db:
            rows = (await db.execute(
                select(ArtifactEdgeRecord).where(ArtifactEdgeRecord.parent_id == parent_id))).scalars().all()
        return [self._to_domain(r) for r in rows]

    async def edges_to(self, child_id: str) -> list[ArtifactEdge]:
        from app.db.models import ArtifactEdgeRecord
        async with self._factory()() as db:
            rows = (await db.execute(
                select(ArtifactEdgeRecord).where(ArtifactEdgeRecord.child_id == child_id))).scalars().all()
        return [self._to_domain(r) for r in rows]

    async def delete_for_artifact(self, artifact_id: str) -> int:
        from app.db.models import ArtifactEdgeRecord
        async with self._factory()() as db:
            rows = (await db.execute(
                select(ArtifactEdgeRecord).where(or_(
                    ArtifactEdgeRecord.parent_id == artifact_id,
                    ArtifactEdgeRecord.child_id == artifact_id)))).scalars().all()
            for r in rows:
                await db.delete(r)
            await db.commit()
            return len(rows)


class SqlArtifactVersionRepository(_SessionMixin, ArtifactVersionRepository):

    async def list_versions(self, lineage_id: str) -> list[Artifact]:
        from app.db.models import ArtifactRecord
        async with self._factory()() as db:
            rows = (await db.execute(
                select(ArtifactRecord).where(ArtifactRecord.lineage_id == lineage_id)
                .order_by(ArtifactRecord.version))).scalars().all()
        return [SqlArtifactRepository._to_domain(r) for r in rows]

    async def next_version_number(self, lineage_id: str) -> int:
        versions = await self.list_versions(lineage_id)
        return (max((a.version for a in versions), default=0)) + 1
