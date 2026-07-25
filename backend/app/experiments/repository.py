"""Experiment Platform — repository layer (RedForge V3, Epic 4).

Dependency inversion: the service + subscriber depend on these interfaces, never on
SQLAlchemy. Maps rows ↔ pure domain objects across the four experiment tables.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import select

from app.experiments.domain import (
    Experiment,
    ExperimentConfiguration,
    ExperimentJobReference,
    ExperimentNote,
    ExperimentSnapshot,
    ExperimentTimelineEvent,
)


class ExperimentRepository(ABC):
    @abstractmethod
    async def add(self, experiment: Experiment) -> Experiment: ...
    @abstractmethod
    async def get(self, experiment_id: str) -> Optional[Experiment]: ...
    @abstractmethod
    async def update(self, experiment: Experiment) -> Optional[Experiment]: ...
    @abstractmethod
    async def delete(self, experiment_id: str) -> bool: ...
    @abstractmethod
    async def list(self, *, project_id: Optional[str] = None, status: Optional[str] = None,
                   limit: int = 200) -> list[Experiment]: ...


class TimelineRepository(ABC):
    @abstractmethod
    async def add(self, event: ExperimentTimelineEvent) -> ExperimentTimelineEvent: ...
    @abstractmethod
    async def list(self, experiment_id: str, *, limit: int = 500) -> list[ExperimentTimelineEvent]: ...


class NoteRepository(ABC):
    @abstractmethod
    async def add(self, note: ExperimentNote) -> ExperimentNote: ...
    @abstractmethod
    async def list(self, experiment_id: str) -> list[ExperimentNote]: ...
    @abstractmethod
    async def delete(self, note_id: str) -> bool: ...


class JobRefRepository(ABC):
    @abstractmethod
    async def upsert(self, ref: ExperimentJobReference) -> None: ...
    @abstractmethod
    async def list(self, experiment_id: str) -> list[ExperimentJobReference]: ...


class _SessionMixin:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal


class SqlExperimentRepository(_SessionMixin, ExperimentRepository):

    @staticmethod
    def _to_domain(row) -> Experiment:
        snap = None
        if row.snapshot:
            snap = ExperimentSnapshot(**{k: row.snapshot.get(k) for k in
                ("foundation_model", "dataset_version", "dataset_content_hash", "strategy",
                 "provider", "hyperparameters", "resource_estimate", "gpu", "redforge_version",
                 "platform") if k in row.snapshot})
        return Experiment(
            id=row.id, name=row.name, status=Experiment.coerce_status(row.status),
            description=row.description or "",
            configuration=ExperimentConfiguration.from_dict(row.configuration or {}),
            snapshot=snap, tags=list(row.tags or []), metrics=dict(row.metrics or {}),
            project_id=row.project_id, parent_experiment_id=row.parent_experiment_id,
            created_at=row.created_at, updated_at=row.updated_at, concluded_at=row.concluded_at)

    @staticmethod
    def _apply(row, e: Experiment) -> None:
        row.name = e.name
        row.status = e.status.value
        row.description = e.description
        row.configuration = e.configuration.to_dict()
        row.snapshot = e.snapshot.to_dict() if e.snapshot else None
        row.tags = e.tags or []
        row.metrics = e.metrics or {}
        row.project_id = e.project_id
        row.parent_experiment_id = e.parent_experiment_id
        row.concluded_at = e.concluded_at

    async def add(self, experiment: Experiment) -> Experiment:
        from app.db.models import ExperimentRecord
        row = ExperimentRecord(id=experiment.id, created_at=experiment.created_at)
        self._apply(row, experiment)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, experiment_id: str) -> Optional[Experiment]:
        from app.db.models import ExperimentRecord
        async with self._factory()() as db:
            row = await db.get(ExperimentRecord, experiment_id)
            return self._to_domain(row) if row else None

    async def update(self, experiment: Experiment) -> Optional[Experiment]:
        from app.db.models import ExperimentRecord
        async with self._factory()() as db:
            row = await db.get(ExperimentRecord, experiment.id)
            if row is None:
                return None
            self._apply(row, experiment)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def delete(self, experiment_id: str) -> bool:
        from app.db.models import (ExperimentJobRefRecord, ExperimentNoteRecord,
                                   ExperimentRecord, ExperimentTimelineRecord)
        async with self._factory()() as db:
            row = await db.get(ExperimentRecord, experiment_id)
            if row is None:
                return False
            for model in (ExperimentTimelineRecord, ExperimentNoteRecord, ExperimentJobRefRecord):
                children = (await db.execute(select(model).where(
                    model.experiment_id == experiment_id))).scalars().all()
                for c in children:
                    await db.delete(c)
            await db.delete(row)
            await db.commit()
            return True

    async def list(self, *, project_id=None, status=None, limit: int = 200) -> list[Experiment]:
        from app.db.models import ExperimentRecord
        stmt = select(ExperimentRecord).order_by(ExperimentRecord.updated_at.desc())
        if project_id is not None:
            stmt = stmt.where(ExperimentRecord.project_id == project_id)
        if status is not None:
            stmt = stmt.where(ExperimentRecord.status == status)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]


class SqlTimelineRepository(_SessionMixin, TimelineRepository):

    @staticmethod
    def _to_domain(row) -> ExperimentTimelineEvent:
        return ExperimentTimelineEvent(
            id=row.id, experiment_id=row.experiment_id, kind=row.kind, title=row.title or "",
            payload=dict(row.payload or {}), source=row.source or "system", at=row.at)

    async def add(self, event: ExperimentTimelineEvent) -> ExperimentTimelineEvent:
        from app.db.models import ExperimentTimelineRecord
        row = ExperimentTimelineRecord(
            id=event.id, experiment_id=event.experiment_id, kind=event.kind, title=event.title,
            payload=event.payload or {}, source=event.source, at=event.at)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def list(self, experiment_id: str, *, limit: int = 500) -> list[ExperimentTimelineEvent]:
        from app.db.models import ExperimentTimelineRecord
        async with self._factory()() as db:
            rows = (await db.execute(select(ExperimentTimelineRecord).where(
                ExperimentTimelineRecord.experiment_id == experiment_id)
                .order_by(ExperimentTimelineRecord.at.desc()).limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]


class SqlNoteRepository(_SessionMixin, NoteRepository):

    @staticmethod
    def _to_domain(row) -> ExperimentNote:
        return ExperimentNote(id=row.id, experiment_id=row.experiment_id, body=row.body,
                              created_at=row.created_at)

    async def add(self, note: ExperimentNote) -> ExperimentNote:
        from app.db.models import ExperimentNoteRecord
        row = ExperimentNoteRecord(id=note.id, experiment_id=note.experiment_id, body=note.body)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def list(self, experiment_id: str) -> list[ExperimentNote]:
        from app.db.models import ExperimentNoteRecord
        async with self._factory()() as db:
            rows = (await db.execute(select(ExperimentNoteRecord).where(
                ExperimentNoteRecord.experiment_id == experiment_id)
                .order_by(ExperimentNoteRecord.created_at.desc()))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def delete(self, note_id: str) -> bool:
        from app.db.models import ExperimentNoteRecord
        async with self._factory()() as db:
            row = await db.get(ExperimentNoteRecord, note_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True


class SqlJobRefRepository(_SessionMixin, JobRefRepository):

    async def upsert(self, ref: ExperimentJobReference) -> None:
        from app.db.models import ExperimentJobRefRecord
        from uuid import uuid4
        async with self._factory()() as db:
            existing = (await db.execute(select(ExperimentJobRefRecord).where(
                ExperimentJobRefRecord.experiment_id == ref.experiment_id,
                ExperimentJobRefRecord.job_id == ref.job_id).limit(1))).scalar_one_or_none()
            if existing is None:
                db.add(ExperimentJobRefRecord(id=str(uuid4()), experiment_id=ref.experiment_id,
                                              job_id=ref.job_id, job_type=ref.job_type, status=ref.status))
            else:
                existing.status = ref.status or existing.status
                if ref.job_type:
                    existing.job_type = ref.job_type
            await db.commit()

    async def list(self, experiment_id: str) -> list[ExperimentJobReference]:
        from app.db.models import ExperimentJobRefRecord
        async with self._factory()() as db:
            rows = (await db.execute(select(ExperimentJobRefRecord).where(
                ExperimentJobRefRecord.experiment_id == experiment_id)
                .order_by(ExperimentJobRefRecord.updated_at.desc()))).scalars().all()
            return [ExperimentJobReference(experiment_id=r.experiment_id, job_id=r.job_id,
                                           job_type=r.job_type or "", status=r.status or "",
                                           updated_at=r.updated_at) for r in rows]
