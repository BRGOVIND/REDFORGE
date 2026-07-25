"""Artifact Registry — application services (RedForge V3, Epic 2).

The registry is the librarian of the platform (Constitution §3.4, §6): it owns the
index, the lineage DAG, metadata, checksums, and location resolution — and nothing
else. It does not produce artifacts (engines produce) and does not interpret their
contents (owning contexts interpret). Services depend on repository *interfaces*
(dependency inversion) and never touch SQLAlchemy.

Five cohesive services (the Epic's suggested service list, consolidated to real
concerns rather than one-method wrappers):
- ArtifactRegistryService — register / publish / archive / delete / tag / resolve / validate
- ArtifactQueryService — search / list / get
- ArtifactLineageService — parents / children / ancestors / descendants / lineage
- ArtifactVersionService — version / history / current
- ArtifactStorageService — file-backed integrity via the pluggable StorageProvider
"""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from app.artifacts import events as artifact_events
from app.artifacts.artifact_types import get_artifact_type, is_file_backed
from app.artifacts.domain import (
    Artifact,
    ArtifactEdge,
    ArtifactLineage,
    ArtifactLocation,
    ArtifactReference,
    ArtifactStatus,
    Checksum,
    PRODUCTION_RELATIONSHIPS,
    RelationshipType,
)
from app.artifacts.repository import (
    ArtifactRelationshipRepository,
    ArtifactRepository,
    ArtifactVersionRepository,
    SqlArtifactRelationshipRepository,
    SqlArtifactRepository,
    SqlArtifactVersionRepository,
)
from app.artifacts.storage import StorageProvider, get_storage_provider
from app.logging_config import get_logger

logger = get_logger("artifacts")


class ArtifactStorageService:
    """File-backed integrity via the pluggable StorageProvider. Data-backed
    artifacts don't use storage (their bytes are a DB row)."""

    def __init__(self, provider: Optional[StorageProvider] = None) -> None:
        self._storage = provider or get_storage_provider()

    def stat(self, location: ArtifactLocation) -> tuple[Optional[int], Optional[Checksum]]:
        """Return (size_bytes, checksum) for a file-backed location, or (None, None)."""
        if not location.is_file or not location.file_path:
            return None, None
        size = self._storage.size(location.file_path)
        digest = self._storage.checksum(location.file_path)
        return size, (Checksum(value=digest) if digest else None)

    def verify(self, artifact: Artifact) -> tuple[bool, str]:
        """Integrity check. File-backed: the file exists and (if a checksum was
        recorded) still matches. Data-backed: the reference is well-formed. Honest —
        returns a reason, never silently passes a broken artifact."""
        loc = artifact.location
        if loc.is_file:
            if not loc.file_path or not self._storage.exists(loc.file_path):
                return False, "file-backed artifact missing on disk"
            if artifact.checksum and artifact.checksum.value:
                now = self._storage.checksum(loc.file_path)
                if now != artifact.checksum.value:
                    return False, "checksum mismatch — file changed since registration"
            return True, "ok"
        # data-backed
        if not loc.table or not loc.row_id:
            return False, "data-backed artifact has an incomplete table reference"
        return True, "ok"


class ArtifactRegistryService:
    """The registry facade — the primary way anything registers an artifact."""

    def __init__(self, repository: Optional[ArtifactRepository] = None,
                 relationships: Optional[ArtifactRelationshipRepository] = None,
                 storage: Optional[ArtifactStorageService] = None) -> None:
        self._repo = repository or SqlArtifactRepository()
        self._edges = relationships or SqlArtifactRelationshipRepository()
        self._storage = storage or ArtifactStorageService()

    async def register(self, *, type: str, name: str, location: Optional[ArtifactLocation] = None,
                       file_path: Optional[str] = None, table: Optional[str] = None,
                       row_id: Optional[str] = None,
                       producer: str = "", project_id: Optional[str] = None,
                       experiment_id: Optional[str] = None, description: str = "",
                       tags: Optional[list[str]] = None, metadata: Optional[dict] = None,
                       parents: Optional[list[tuple[str, str]]] = None,
                       status: str = "draft") -> dict:
        """Register a new artifact (starts ``draft`` by default). ``parents`` is a
        list of (parent_artifact_id, relationship) — the lineage edges. File-backed
        artifacts get their size/checksum computed from the location automatically.

        This is the single entry point for putting anything into the platform spine.
        Idempotency is the caller's concern (register is a create); consumers that
        want "register-or-get" search first."""
        # Build the location: explicit object wins, else convenience kwargs, else
        # default shape from the type's backing.
        if location is not None:
            loc = location
        elif file_path:
            loc = ArtifactLocation.file(file_path)
        elif table and row_id:
            loc = ArtifactLocation.data(table, row_id)
        else:
            loc = ArtifactLocation(kind="file") if is_file_backed(type) else ArtifactLocation(kind="data")
        artifact = Artifact(
            id=str(uuid4()), type=type, name=name,
            status=Artifact.coerce_status(status), location=loc, producer=producer,
            project_id=project_id, experiment_id=experiment_id, description=description,
            tags=list(tags or []), metadata=metadata or {},
        )
        artifact.lineage_id = artifact.id
        # File-backed: stat the bytes for size + checksum (honest integrity).
        if loc.is_file and loc.file_path:
            size, checksum = self._storage.stat(loc)
            artifact.size_bytes, artifact.checksum = size, checksum
        created = await self._repo.add(artifact)
        # Lineage edges to declared parents.
        for parent_id, rel in (parents or []):
            await self._edges.add_edge(ArtifactEdge(
                id=str(uuid4()), parent_id=parent_id, child_id=created.id,
                relationship=ArtifactEdge.coerce_relationship(rel),
            ))
        logger.info("registered artifact %s (%s) status=%s", created.id, created.type, created.status.value)
        return created.to_dict()

    async def get(self, artifact_id: str) -> Optional[dict]:
        a = await self._repo.get(artifact_id)
        return a.to_dict() if a else None

    async def publish(self, artifact_id: str) -> Optional[dict]:
        """Transition an artifact draft → ready and emit ``artifact.published``.
        Re-stats file-backed bytes so size/checksum reflect the final content."""
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        if a.location.is_file and a.location.file_path:
            a.size_bytes, a.checksum = self._storage.stat(a.location)
        a.status = ArtifactStatus.READY
        updated = await self._repo.update(a)
        await artifact_events.emit(artifact_events.ARTIFACT_PUBLISHED,
                                   {"id": artifact_id, "type": a.type, "experiment_id": a.experiment_id})
        return updated.to_dict() if updated else None

    async def archive(self, artifact_id: str) -> Optional[dict]:
        from datetime import datetime, timezone
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        a.status = ArtifactStatus.ARCHIVED
        a.archived_at = datetime.now(timezone.utc)
        updated = await self._repo.update(a)
        await artifact_events.emit(artifact_events.ARTIFACT_ARCHIVED, {"id": artifact_id})
        return updated.to_dict() if updated else None

    async def invalidate(self, artifact_id: str, reason: str = "") -> Optional[dict]:
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        a.status = ArtifactStatus.INVALID
        if reason:
            a.metadata = {**(a.metadata or {}), "invalid_reason": reason}
        updated = await self._repo.update(a)
        await artifact_events.emit(artifact_events.ARTIFACT_INVALIDATED,
                                   {"id": artifact_id, "reason": reason})
        return updated.to_dict() if updated else None

    async def tag(self, artifact_id: str, tags: list[str]) -> Optional[dict]:
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        merged = list(dict.fromkeys([*(a.tags or []), *tags]))  # union, order-stable
        a.tags = merged
        updated = await self._repo.update(a)
        return updated.to_dict() if updated else None

    async def resolve(self, artifact_id: str) -> Optional[dict]:
        """Resolve an artifact to its consumable form: the file path (file-backed) or
        the table reference (data-backed). This is how a consumer turns an artifact
        into something it can open/read."""
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        return {"id": a.id, "type": a.type, "status": a.status.value,
                "location": a.location.to_dict()}

    async def validate(self, artifact_id: str) -> Optional[dict]:
        """Integrity-check an artifact; mark it invalid (honestly) if broken."""
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        ok, reason = self._storage.verify(a)
        if not ok and a.status != ArtifactStatus.INVALID:
            await self.invalidate(artifact_id, reason)
        return {"id": artifact_id, "valid": ok, "reason": reason}

    async def delete(self, artifact_id: str) -> bool:
        """Hard-delete an artifact and its lineage edges. (Retention-policy-aware
        purging that refuses to orphan descendants is a later concern; delete here
        is the explicit operator action.)"""
        await self._edges.delete_for_artifact(artifact_id)
        return await self._repo.delete(artifact_id)


class ArtifactQueryService:
    def __init__(self, repository: Optional[ArtifactRepository] = None) -> None:
        self._repo = repository or SqlArtifactRepository()

    async def search(self, **kwargs) -> list[dict]:
        return [a.to_dict() for a in await self._repo.search(**kwargs)]

    async def get(self, artifact_id: str) -> Optional[dict]:
        a = await self._repo.get(artifact_id)
        return a.to_dict() if a else None


class ArtifactLineageService:
    """Lineage DAG traversal (Constitution §6.5). Answers provenance (ancestors) and
    impact (descendants) generically — the capability the prior architecture lacked."""

    def __init__(self, repository: Optional[ArtifactRepository] = None,
                 relationships: Optional[ArtifactRelationshipRepository] = None) -> None:
        self._repo = repository or SqlArtifactRepository()
        self._edges = relationships or SqlArtifactRelationshipRepository()

    async def _refs(self, ids: list[str]) -> list[ArtifactReference]:
        arts = await self._repo.get_many(ids)
        return [a.as_reference() for a in arts]

    async def parents(self, artifact_id: str) -> list[dict]:
        edges = [e for e in await self._edges.edges_to(artifact_id)
                 if e.relationship in PRODUCTION_RELATIONSHIPS]
        refs = await self._refs([e.parent_id for e in edges])
        return [r.to_dict() for r in refs]

    async def children(self, artifact_id: str) -> list[dict]:
        edges = [e for e in await self._edges.edges_from(artifact_id)
                 if e.relationship in PRODUCTION_RELATIONSHIPS]
        refs = await self._refs([e.child_id for e in edges])
        return [r.to_dict() for r in refs]

    async def _walk(self, artifact_id: str, direction: str, limit: int = 500) -> list[str]:
        """BFS over production edges. direction: 'up' (ancestors) | 'down' (descendants)."""
        seen: set[str] = set()
        order: list[str] = []
        frontier = [artifact_id]
        while frontier and len(order) < limit:
            nxt: list[str] = []
            for node in frontier:
                edges = (await self._edges.edges_to(node)) if direction == "up" \
                    else (await self._edges.edges_from(node))
                for e in edges:
                    if e.relationship not in PRODUCTION_RELATIONSHIPS:
                        continue
                    neighbor = e.parent_id if direction == "up" else e.child_id
                    if neighbor not in seen and neighbor != artifact_id:
                        seen.add(neighbor)
                        order.append(neighbor)
                        nxt.append(neighbor)
            frontier = nxt
        return order

    async def lineage(self, artifact_id: str) -> Optional[dict]:
        a = await self._repo.get(artifact_id)
        if a is None:
            return None
        ancestors = await self._walk(artifact_id, "up")
        descendants = await self._walk(artifact_id, "down")
        parent_edges = await self._edges.edges_to(artifact_id)
        child_edges = await self._edges.edges_from(artifact_id)
        lineage = ArtifactLineage(
            artifact_id=artifact_id,
            ancestors=await self._refs(ancestors),
            descendants=await self._refs(descendants),
            parents=await self._refs([e.parent_id for e in parent_edges
                                      if e.relationship in PRODUCTION_RELATIONSHIPS]),
            children=await self._refs([e.child_id for e in child_edges
                                       if e.relationship in PRODUCTION_RELATIONSHIPS]),
            edges=[*parent_edges, *child_edges],
        )
        return lineage.to_dict()


class ArtifactVersionService:
    """Versioning as artifacts-sharing-a-lineage (Constitution §6.6)."""

    def __init__(self, repository: Optional[ArtifactRepository] = None,
                 versions: Optional[ArtifactVersionRepository] = None,
                 relationships: Optional[ArtifactRelationshipRepository] = None) -> None:
        self._repo = repository or SqlArtifactRepository()
        self._versions = versions or SqlArtifactVersionRepository()
        self._edges = relationships or SqlArtifactRelationshipRepository()

    async def create_version(self, artifact_id: str, *, location: Optional[ArtifactLocation] = None,
                             metadata: Optional[dict] = None, description: Optional[str] = None) -> Optional[dict]:
        """Create the next version of an artifact: a new artifact sharing the
        predecessor's ``lineage_id``, with an incremented ``version`` and a
        ``SUPERSEDES`` edge (new → old). Emits ``artifact.version_created``."""
        prev = await self._repo.get(artifact_id)
        if prev is None:
            return None
        next_num = await self._versions.next_version_number(prev.lineage_id or prev.id)
        new = Artifact(
            id=str(uuid4()), type=prev.type, name=prev.name,
            status=ArtifactStatus.DRAFT,
            location=location or prev.location, producer=prev.producer,
            project_id=prev.project_id, experiment_id=prev.experiment_id,
            description=description if description is not None else prev.description,
            tags=list(prev.tags or []), lineage_id=prev.lineage_id or prev.id,
            version=next_num, metadata={**(prev.metadata or {}), **(metadata or {})},
        )
        created = await self._repo.add(new)
        await self._edges.add_edge(ArtifactEdge(
            id=str(uuid4()), parent_id=prev.id, child_id=created.id,
            relationship=RelationshipType.SUPERSEDES,
        ))
        await artifact_events.emit(artifact_events.ARTIFACT_VERSION_CREATED,
                                   {"id": created.id, "lineage_id": created.lineage_id,
                                    "version": created.version, "supersedes": prev.id})
        return created.to_dict()

    async def history(self, artifact_id: str) -> list[dict]:
        a = await self._repo.get(artifact_id)
        if a is None:
            return []
        versions = await self._versions.list_versions(a.lineage_id or a.id)
        return [v.to_dict() for v in versions]


# Module-level singletons (default SQL repositories). Tests construct their own with
# injected fakes/in-memory sessions.
artifact_registry = ArtifactRegistryService()
artifact_query = ArtifactQueryService()
artifact_lineage = ArtifactLineageService()
artifact_versions = ArtifactVersionService()
