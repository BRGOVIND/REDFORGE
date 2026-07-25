"""Dataset Platform — application service (RedForge V3, Epic 3).

Owns the Dataset bounded context's logic. Composes the proven ``datasets_lab`` pure
helpers (parsing / statistics / analysis / splitting) rather than duplicating them
(§2.16 single source of truth), and publishes every dataset version to the Artifact
Registry (§2.4, §6). Depends on repository *interfaces* and the Artifact Registry
service — never on SQLAlchemy.
"""
from __future__ import annotations

import json
from typing import Optional
from uuid import uuid4

from app.artifacts.checksum import sha256_bytes
from app.datasets.domain import (
    Dataset,
    DatasetFormat,
    DatasetPreview,
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
from app.datasets_lab import analysis as ds_analysis  # pure helpers — reuse, don't duplicate
from app.datasets_lab import parsers as ds_parsers
from app.datasets_lab import splitting as ds_splitting
from app.logging_config import get_logger

logger = get_logger("dataset-platform")


def _hash_records(records: list) -> str:
    return sha256_bytes(json.dumps(records, ensure_ascii=False, sort_keys=True).encode("utf-8"))


class DatasetPlatformService:
    def __init__(self, dataset_repo: Optional[DatasetRepository] = None,
                 version_repo: Optional[DatasetVersionRepository] = None,
                 artifact_registry=None) -> None:
        self._datasets = dataset_repo or SqlDatasetRepository()
        self._versions = version_repo or SqlDatasetVersionRepository()
        self._artifacts = artifact_registry  # None → resolve the singleton lazily

    def _registry(self):
        if self._artifacts is not None:
            return self._artifacts
        from app.artifacts import artifact_registry
        return artifact_registry

    # -- import / register ----------------------------------------------------

    async def import_bytes(self, *, name: str, data: bytes, filename: str = "",
                           fmt: Optional[str] = None, project_id: Optional[str] = None,
                           description: str = "") -> dict:
        """Parse raw bytes (reusing datasets_lab parsers), analyze, register the
        dataset + its first version, and publish a dataset Artifact."""
        detected = fmt or (ds_parsers.detect_format(filename) if filename else "jsonl")
        parsed = ds_parsers.parse(data, detected)
        return await self._create(
            name=name, records=parsed["records"], kind=parsed["kind"],
            fmt=parsed["format"], columns=parsed["columns"], byte_size=len(data),
            project_id=project_id, description=description, note="imported")

    async def register(self, *, name: str, records: list, fmt: str = "jsonl",
                       kind: str = "records", project_id: Optional[str] = None,
                       description: str = "") -> dict:
        """Register a dataset from inline records."""
        columns = sorted({k for r in records if isinstance(r, dict) for k in r.keys()}) \
            if kind == "records" else []
        byte_size = len(json.dumps(records, ensure_ascii=False).encode("utf-8"))
        return await self._create(name=name, records=records, kind=kind, fmt=fmt,
                                  columns=columns, byte_size=byte_size,
                                  project_id=project_id, description=description, note="registered")

    async def _create(self, *, name, records, kind, fmt, columns, byte_size,
                      project_id, description, note) -> dict:
        stats = ds_analysis.statistics(records, kind, byte_size)
        dataset = Dataset(
            id=str(uuid4()), name=name, format=Dataset.coerce_format(fmt), kind=kind,
            status=DatasetStatus.READY, description=description, project_id=project_id,
            current_version=1, content_hash=_hash_records(records),
            statistics=DatasetStatistics(
                record_count=stats.get("record_count", len(records)), byte_size=byte_size,
                estimated_tokens=stats.get("estimated_tokens", 0),
                avg_length=stats.get("avg_length", 0.0), column_count=len(columns)),
        )
        dataset.schema.kind = kind
        dataset.schema.columns = columns
        await self._datasets.add(dataset)
        version = await self._add_version(dataset, records, version_num=1, note=note, parent_artifact=None)
        result = dataset.to_dict()
        result["version_id"] = version.id
        result["artifact_id"] = version.artifact_id
        logger.info("registered v3 dataset %s (%d records)", dataset.id, dataset.statistics.record_count)
        return result

    async def _add_version(self, dataset: Dataset, records: list, *, version_num: int,
                           note: str, parent_artifact: Optional[str]) -> DatasetVersion:
        version = DatasetVersion(
            id=str(uuid4()), dataset_id=dataset.id, version=version_num, records=records,
            record_count=len(records), note=note, content_hash=_hash_records(records))
        await self._versions.add(version)
        # Publish a data-backed dataset Artifact for this version (spine).
        parents = [(parent_artifact, "derived_from")] if parent_artifact else []
        artifact = await self._registry().register(
            type="dataset", name=f"{dataset.name} v{version_num}",
            table="v3_dataset_versions", row_id=version.id, producer="dataset_platform",
            project_id=dataset.project_id, parents=parents,
            metadata={"dataset_id": dataset.id, "version": version_num,
                      "record_count": version.record_count, "format": dataset.format.value,
                      "content_hash": version.content_hash})
        await self._registry().publish(artifact["id"])
        version.artifact_id = artifact["id"]
        await self._versions.update(version)
        return version

    # -- reads ----------------------------------------------------------------

    async def get(self, dataset_id: str) -> Optional[dict]:
        d = await self._datasets.get(dataset_id)
        return d.to_dict() if d else None

    async def list(self, *, project_id: Optional[str] = None) -> list[dict]:
        return [d.to_dict() for d in await self._datasets.list(project_id=project_id)]

    async def versions(self, dataset_id: str) -> list[dict]:
        return [v.to_dict() for v in await self._versions.list(dataset_id)]

    async def preview(self, dataset_id: str, *, offset: int = 0, limit: int = 50) -> Optional[dict]:
        d = await self._datasets.get(dataset_id)
        if d is None:
            return None
        version = await self._versions.get_by_number(dataset_id, d.current_version)
        if version is None:
            return DatasetPreview(rows=[], total=0, offset=offset).to_dict()
        rows = version.records[offset:offset + limit]
        return DatasetPreview(rows=rows, total=len(version.records), offset=offset).to_dict()

    async def statistics(self, dataset_id: str) -> Optional[dict]:
        d = await self._datasets.get(dataset_id)
        return d.statistics.to_dict() if d else None

    async def validate(self, dataset_id: str) -> Optional[dict]:
        """Quality validation, reusing the datasets_lab analyzer."""
        d = await self._datasets.get(dataset_id)
        if d is None:
            return None
        version = await self._versions.get_by_number(dataset_id, d.current_version)
        records = version.records if version else []
        byte_size = d.statistics.byte_size
        report = ds_analysis.analyze(records, d.kind, d.schema.columns, byte_size)
        issues = report.get("issues", {})
        critical = bool(issues.get("unsafe_samples")) or bool(issues.get("malformed_conversations"))
        result = DatasetValidationResult(
            valid=(report.get("score", 0) >= 50 and not critical),
            score=report.get("score", 0), grade=report.get("grade", "unknown"),
            issues=issues, suggestions=report.get("suggestions", []))
        return result.to_dict()

    # -- processing (produces a new version) ----------------------------------

    async def split(self, dataset_id: str, *, train: float = 0.8, val: float = 0.1,
                    test: float = 0.1, seed: int = 42) -> Optional[dict]:
        """Deterministic train/val/test split → a new version (artifact-published)."""
        d = await self._datasets.get(dataset_id)
        if d is None:
            return None
        version = await self._versions.get_by_number(dataset_id, d.current_version)
        if version is None:
            return None
        result = ds_splitting.split(version.records, train=train, val=val, test=test, seed=seed)
        # Store the split as a new version whose records carry a split marker.
        combined = (
            [{**(r if isinstance(r, dict) else {"text": r}), "_split": "train"} for r in result["train"]]
            + [{**(r if isinstance(r, dict) else {"text": r}), "_split": "validation"} for r in result["validation"]]
            + [{**(r if isinstance(r, dict) else {"text": r}), "_split": "test"} for r in result["test"]])
        new_num = d.current_version + 1
        new_version = await self._add_version(d, combined, version_num=new_num,
                                              note="split train/val/test", parent_artifact=version.artifact_id)
        d.current_version = new_num
        await self._datasets.update(d)
        return {"dataset_id": dataset_id, "version": new_num, "version_id": new_version.id,
                "artifact_id": new_version.artifact_id, "statistics": result["statistics"]}

    async def delete(self, dataset_id: str) -> bool:
        return await self._datasets.delete(dataset_id)


dataset_platform = DatasetPlatformService()
