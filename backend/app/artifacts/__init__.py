"""Artifact Registry (RedForge V3, Epic 2) — the platform spine.

The canonical source of truth for every artifact RedForge produces, with lineage,
versioning, checksums, and pluggable storage (Constitution §3.4, §6). A Platform
Service (Layer ③): every domain engine registers its outputs here; consumers query
and traverse lineage here.

Layering: domain (pure) → repository (persistence) → service (logic) → storage
(pluggable). Services depend on repository interfaces, never SQLAlchemy.
"""
from app.artifacts.artifact_types import (
    ArtifactTypeDef,
    get_artifact_type,
    is_file_backed,
    list_artifact_types,
    register_artifact_type,
)
from app.artifacts.domain import (
    Artifact,
    ArtifactEdge,
    ArtifactLineage,
    ArtifactLocation,
    ArtifactReference,
    ArtifactStatus,
    Checksum,
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
from app.artifacts.service import (
    ArtifactLineageService,
    ArtifactQueryService,
    ArtifactRegistryService,
    ArtifactStorageService,
    ArtifactVersionService,
    artifact_lineage,
    artifact_query,
    artifact_registry,
    artifact_versions,
)
from app.artifacts.storage import (
    LocalStorageProvider,
    StorageProvider,
    get_storage_provider,
    list_storage_providers,
    register_storage_provider,
)

__all__ = [
    # types
    "ArtifactTypeDef", "get_artifact_type", "is_file_backed", "list_artifact_types",
    "register_artifact_type",
    # domain
    "Artifact", "ArtifactEdge", "ArtifactLineage", "ArtifactLocation", "ArtifactReference",
    "ArtifactStatus", "Checksum", "RelationshipType",
    # repositories
    "ArtifactRepository", "ArtifactRelationshipRepository", "ArtifactVersionRepository",
    "SqlArtifactRepository", "SqlArtifactRelationshipRepository", "SqlArtifactVersionRepository",
    # services + singletons
    "ArtifactRegistryService", "ArtifactQueryService", "ArtifactLineageService",
    "ArtifactVersionService", "ArtifactStorageService",
    "artifact_registry", "artifact_query", "artifact_lineage", "artifact_versions",
    # storage
    "StorageProvider", "LocalStorageProvider", "get_storage_provider",
    "list_storage_providers", "register_storage_provider",
]
