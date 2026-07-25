"""Dataset Platform (RedForge V3, Epic 3).

First-class, versioned, artifact-published datasets (Constitution §3.5, §5.9, §12).
Composes the proven ``datasets_lab`` pure helpers; publishes every version to the
Artifact Registry; processes through the Job System. Additive and local-only;
distinct from the legacy ``datasets_lab`` (strangler-fig).
"""
from app.datasets.domain import (
    Dataset,
    DatasetFormat,
    DatasetPreview,
    DatasetSchema,
    DatasetStatistics,
    DatasetStatus,
    DatasetValidationResult,
    DatasetVersion,
)
from app.datasets.repository import (
    DatasetRepository,
    DatasetVersionRepository,
    SqlDatasetRepository,
    SqlDatasetVersionRepository,
)
from app.datasets.service import DatasetPlatformService, dataset_platform

__all__ = [
    "Dataset", "DatasetVersion", "DatasetFormat", "DatasetStatus", "DatasetSchema",
    "DatasetStatistics", "DatasetValidationResult", "DatasetPreview",
    "DatasetRepository", "DatasetVersionRepository",
    "SqlDatasetRepository", "SqlDatasetVersionRepository",
    "DatasetPlatformService", "dataset_platform",
]
