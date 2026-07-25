"""Dataset Platform — repository layer (RedForge V3, Epic 3).

Dependency inversion: the service depends on these interfaces, never on SQLAlchemy.
Maps ``V3DatasetRecord`` / ``V3DatasetVersionRecord`` rows ↔ pure domain objects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import select

from app.datasets.domain import (
    Dataset,
    DatasetSchema,
    DatasetStatistics,
    DatasetVersion,
)


class DatasetRepository(ABC):
    @abstractmethod
    async def add(self, dataset: Dataset) -> Dataset: ...
    @abstractmethod
    async def get(self, dataset_id: str) -> Optional[Dataset]: ...
    @abstractmethod
    async def update(self, dataset: Dataset) -> Optional[Dataset]: ...
    @abstractmethod
    async def delete(self, dataset_id: str) -> bool: ...
    @abstractmethod
    async def list(self, *, project_id: Optional[str] = None, status: Optional[str] = None,
                   limit: int = 200) -> list[Dataset]: ...


class DatasetVersionRepository(ABC):
    @abstractmethod
    async def add(self, version: DatasetVersion) -> DatasetVersion: ...
    @abstractmethod
    async def get(self, version_id: str) -> Optional[DatasetVersion]: ...
    @abstractmethod
    async def get_by_number(self, dataset_id: str, version: int) -> Optional[DatasetVersion]: ...
    @abstractmethod
    async def list(self, dataset_id: str) -> list[DatasetVersion]: ...
    @abstractmethod
    async def update(self, version: DatasetVersion) -> Optional[DatasetVersion]: ...


class _SessionMixin:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal


class SqlDatasetRepository(_SessionMixin, DatasetRepository):

    @staticmethod
    def _to_domain(row) -> Dataset:
        sch = row.schema or {}
        st = row.statistics or {}
        return Dataset(
            id=row.id, name=row.name, format=Dataset.coerce_format(row.format),
            kind=row.kind, status=Dataset.coerce_status(row.status),
            description=row.description or "", project_id=row.project_id,
            current_version=row.current_version or 0,
            schema=DatasetSchema(kind=sch.get("kind", row.kind), columns=sch.get("columns", [])),
            statistics=DatasetStatistics(**{k: st.get(k, 0) for k in
                ("record_count", "byte_size", "estimated_tokens", "avg_length", "column_count")}),
            content_hash=row.content_hash or "", tags=list(row.tags or []),
            metadata=dict(row.dataset_metadata or {}),
            created_at=row.created_at, updated_at=row.updated_at,
        )

    @staticmethod
    def _apply(row, d: Dataset) -> None:
        row.name = d.name
        row.format = d.format.value
        row.kind = d.kind
        row.status = d.status.value
        row.description = d.description
        row.project_id = d.project_id
        row.current_version = d.current_version
        row.schema = d.schema.to_dict()
        row.statistics = d.statistics.to_dict()
        row.content_hash = d.content_hash
        row.tags = d.tags or []
        row.dataset_metadata = d.metadata or {}

    async def add(self, dataset: Dataset) -> Dataset:
        from app.db.models import V3DatasetRecord
        row = V3DatasetRecord(id=dataset.id)
        self._apply(row, dataset)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, dataset_id: str) -> Optional[Dataset]:
        from app.db.models import V3DatasetRecord
        async with self._factory()() as db:
            row = await db.get(V3DatasetRecord, dataset_id)
            return self._to_domain(row) if row else None

    async def update(self, dataset: Dataset) -> Optional[Dataset]:
        from app.db.models import V3DatasetRecord
        async with self._factory()() as db:
            row = await db.get(V3DatasetRecord, dataset.id)
            if row is None:
                return None
            self._apply(row, dataset)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def delete(self, dataset_id: str) -> bool:
        from app.db.models import V3DatasetRecord, V3DatasetVersionRecord
        async with self._factory()() as db:
            row = await db.get(V3DatasetRecord, dataset_id)
            if row is None:
                return False
            versions = (await db.execute(select(V3DatasetVersionRecord).where(
                V3DatasetVersionRecord.dataset_id == dataset_id))).scalars().all()
            for v in versions:
                await db.delete(v)
            await db.delete(row)
            await db.commit()
            return True

    async def list(self, *, project_id=None, status=None, limit: int = 200) -> list[Dataset]:
        from app.db.models import V3DatasetRecord
        stmt = select(V3DatasetRecord).order_by(V3DatasetRecord.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(V3DatasetRecord.project_id == project_id)
        if status is not None:
            stmt = stmt.where(V3DatasetRecord.status == status)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]


class SqlDatasetVersionRepository(_SessionMixin, DatasetVersionRepository):

    @staticmethod
    def _to_domain(row, *, with_records: bool = True) -> DatasetVersion:
        return DatasetVersion(
            id=row.id, dataset_id=row.dataset_id, version=row.version,
            records=list(row.records or []) if with_records else [],
            record_count=row.record_count or 0, note=row.note or "",
            content_hash=row.content_hash or "", artifact_id=row.artifact_id,
            created_at=row.created_at,
        )

    async def add(self, version: DatasetVersion) -> DatasetVersion:
        from app.db.models import V3DatasetVersionRecord
        row = V3DatasetVersionRecord(
            id=version.id, dataset_id=version.dataset_id, version=version.version,
            records=version.records, record_count=version.record_count, note=version.note,
            content_hash=version.content_hash, artifact_id=version.artifact_id)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, version_id: str) -> Optional[DatasetVersion]:
        from app.db.models import V3DatasetVersionRecord
        async with self._factory()() as db:
            row = await db.get(V3DatasetVersionRecord, version_id)
            return self._to_domain(row) if row else None

    async def get_by_number(self, dataset_id: str, version: int) -> Optional[DatasetVersion]:
        from app.db.models import V3DatasetVersionRecord
        async with self._factory()() as db:
            row = (await db.execute(select(V3DatasetVersionRecord).where(
                V3DatasetVersionRecord.dataset_id == dataset_id,
                V3DatasetVersionRecord.version == version).limit(1))).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list(self, dataset_id: str) -> list[DatasetVersion]:
        from app.db.models import V3DatasetVersionRecord
        async with self._factory()() as db:
            rows = (await db.execute(select(V3DatasetVersionRecord).where(
                V3DatasetVersionRecord.dataset_id == dataset_id)
                .order_by(V3DatasetVersionRecord.version))).scalars().all()
            return [self._to_domain(r, with_records=False) for r in rows]

    async def update(self, version: DatasetVersion) -> Optional[DatasetVersion]:
        from app.db.models import V3DatasetVersionRecord
        async with self._factory()() as db:
            row = await db.get(V3DatasetVersionRecord, version.id)
            if row is None:
                return None
            row.artifact_id = version.artifact_id
            row.note = version.note
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)
