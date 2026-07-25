"""Dataset Platform — pure domain model (RedForge V3, Epic 3).

Datasets as first-class, versioned, artifact-published entities (Constitution §3.5,
§5.9, §12). Pure: no SQLAlchemy, no FastAPI, no I/O. The service composes the proven
``datasets_lab`` pure helpers (parsing/analysis/splitting) for the heavy lifting; this
module owns only the V3 domain shapes.

Distinct from the legacy ``datasets_lab`` (V2) — additive, strangler-fig. Every
dataset version is published to the Artifact Registry (kind ``dataset``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DatasetFormat(str, Enum):
    JSON = "json"
    JSONL = "jsonl"
    CSV = "csv"
    PARQUET = "parquet"
    TXT = "txt"
    MD = "md"
    UNKNOWN = "unknown"


class DatasetStatus(str, Enum):
    REGISTERED = "registered"
    IMPORTING = "importing"
    READY = "ready"
    INVALID = "invalid"
    ARCHIVED = "archived"


def _coerce(enum_cls, value, default):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


@dataclass
class DatasetSchema:
    kind: str = "records"                 # "records" | "text"
    columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "columns": self.columns}


@dataclass
class DatasetStatistics:
    record_count: int = 0
    byte_size: int = 0
    estimated_tokens: int = 0
    avg_length: float = 0.0
    column_count: int = 0

    def to_dict(self) -> dict:
        return {"record_count": self.record_count, "byte_size": self.byte_size,
                "estimated_tokens": self.estimated_tokens, "avg_length": self.avg_length,
                "column_count": self.column_count}


@dataclass
class DatasetValidationResult:
    valid: bool
    score: float
    grade: str
    issues: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"valid": self.valid, "score": self.score, "grade": self.grade,
                "issues": self.issues, "suggestions": self.suggestions}


@dataclass
class DatasetPreview:
    rows: list = field(default_factory=list)
    total: int = 0
    offset: int = 0

    def to_dict(self) -> dict:
        return {"rows": self.rows, "total": self.total, "offset": self.offset}


@dataclass
class DatasetVersion:
    id: str
    dataset_id: str
    version: int
    records: list = field(default_factory=list)      # inline records/text (data-backed)
    record_count: int = 0
    note: str = ""
    content_hash: str = ""
    artifact_id: Optional[str] = None                # the published dataset artifact
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self, *, with_records: bool = False) -> dict:
        d = {"id": self.id, "dataset_id": self.dataset_id, "version": self.version,
             "record_count": self.record_count, "note": self.note,
             "content_hash": self.content_hash, "artifact_id": self.artifact_id,
             "created_at": self.created_at.isoformat() if self.created_at else None}
        if with_records:
            d["records"] = self.records
        return d


@dataclass
class Dataset:
    id: str
    name: str
    format: DatasetFormat = DatasetFormat.JSONL
    kind: str = "records"
    status: DatasetStatus = DatasetStatus.REGISTERED
    description: str = ""
    project_id: Optional[str] = None
    current_version: int = 0
    schema: DatasetSchema = field(default_factory=DatasetSchema)
    statistics: DatasetStatistics = field(default_factory=DatasetStatistics)
    content_hash: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "format": self.format.value, "kind": self.kind,
            "status": self.status.value, "description": self.description,
            "project_id": self.project_id, "current_version": self.current_version,
            "schema": self.schema.to_dict(), "statistics": self.statistics.to_dict(),
            "content_hash": self.content_hash, "tags": self.tags or [],
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def coerce_format(value) -> DatasetFormat:
        return _coerce(DatasetFormat, value, DatasetFormat.UNKNOWN)

    @staticmethod
    def coerce_status(value) -> DatasetStatus:
        return _coerce(DatasetStatus, value, DatasetStatus.REGISTERED)
