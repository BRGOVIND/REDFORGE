"""Training Platform — repository layer (RedForge V3, Epic 3).

Dependency inversion: the V3 training service/execution depend on these interfaces,
never on SQLAlchemy. Maps ``V3TrainingRunRecord`` / ``V3CheckpointRecord`` rows ↔
pure domain objects. Distinct from the legacy ``training_service`` (strangler-fig).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import select

from app.training.domain import (
    AdapterConfiguration,
    HyperparameterSet,
    TrainingCheckpoint,
    TrainingConfiguration,
    TrainingEstimate,
    TrainingRun,
)


class TrainingRunRepository(ABC):
    @abstractmethod
    async def add(self, run: TrainingRun) -> TrainingRun: ...
    @abstractmethod
    async def get(self, run_id: str) -> Optional[TrainingRun]: ...
    @abstractmethod
    async def update(self, run: TrainingRun) -> Optional[TrainingRun]: ...
    @abstractmethod
    async def delete(self, run_id: str) -> bool: ...
    @abstractmethod
    async def list(self, *, project_id: Optional[str] = None, status: Optional[str] = None,
                   limit: int = 200) -> list[TrainingRun]: ...


class CheckpointRepository(ABC):
    @abstractmethod
    async def add(self, checkpoint: TrainingCheckpoint) -> TrainingCheckpoint: ...
    @abstractmethod
    async def list(self, run_id: str) -> list[TrainingCheckpoint]: ...


class _SessionMixin:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal


class SqlTrainingRunRepository(_SessionMixin, TrainingRunRepository):

    @staticmethod
    def _to_domain(row) -> TrainingRun:
        cfg = row.config or {}
        config = TrainingConfiguration(
            foundation_model_id=row.foundation_model_id, base_model=row.base_model,
            dataset_id=row.dataset_id, dataset_version=row.dataset_version,
            strategy=row.strategy, provider=row.provider,
            hyperparameters=HyperparameterSet.from_dict(cfg.get("hyperparameters", {})),
            adapter=AdapterConfiguration(**{k: v for k, v in (cfg.get("adapter") or {}).items()
                                            if k in ("rank", "alpha", "dropout")}),
            strategy_params=cfg.get("strategy_params", {}))
        est = None
        if row.estimate:
            est = TrainingEstimate(**{k: row.estimate.get(k) for k in
                ("vram_mb", "disk_mb", "duration_seconds", "checkpoint_size_mb", "adapter_size_mb",
                 "fits_hardware", "warnings") if k in row.estimate})
        return TrainingRun(
            id=row.id, name=row.name, configuration=config,
            status=TrainingRun.coerce_status(row.status), metrics=dict(row.metrics or {}),
            estimate=est, job_id=row.job_id, project_id=row.project_id,
            output_dir=row.output_dir or "", logs=list(row.logs or []), error=row.error,
            run_artifact_id=row.run_artifact_id, adapter_artifact_id=row.adapter_artifact_id,
            created_at=row.created_at, started_at=row.started_at, completed_at=row.completed_at)

    @staticmethod
    def _apply(row, r: TrainingRun) -> None:
        c = r.configuration
        row.name = r.name
        row.foundation_model_id = c.foundation_model_id
        row.base_model = c.base_model
        row.dataset_id = c.dataset_id
        row.dataset_version = c.dataset_version
        row.strategy = c.strategy
        row.provider = c.provider
        row.status = r.status.value
        row.config = c.to_dict()
        row.hyperparameters = c.hyperparameters.to_dict()
        row.metrics = r.metrics or {}
        row.estimate = r.estimate.to_dict() if r.estimate else {}
        row.job_id = r.job_id
        row.project_id = r.project_id
        row.output_dir = r.output_dir
        row.logs = r.logs or []
        row.error = r.error
        row.run_artifact_id = r.run_artifact_id
        row.adapter_artifact_id = r.adapter_artifact_id
        row.started_at = r.started_at
        row.completed_at = r.completed_at

    async def add(self, run: TrainingRun) -> TrainingRun:
        from app.db.models import V3TrainingRunRecord
        row = V3TrainingRunRecord(id=run.id, created_at=run.created_at, base_model=run.configuration.base_model)
        self._apply(row, run)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, run_id: str) -> Optional[TrainingRun]:
        from app.db.models import V3TrainingRunRecord
        async with self._factory()() as db:
            row = await db.get(V3TrainingRunRecord, run_id)
            return self._to_domain(row) if row else None

    async def update(self, run: TrainingRun) -> Optional[TrainingRun]:
        from app.db.models import V3TrainingRunRecord
        async with self._factory()() as db:
            row = await db.get(V3TrainingRunRecord, run.id)
            if row is None:
                return None
            self._apply(row, run)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def delete(self, run_id: str) -> bool:
        from app.db.models import V3CheckpointRecord, V3TrainingRunRecord
        async with self._factory()() as db:
            row = await db.get(V3TrainingRunRecord, run_id)
            if row is None:
                return False
            cps = (await db.execute(select(V3CheckpointRecord).where(
                V3CheckpointRecord.run_id == run_id))).scalars().all()
            for cp in cps:
                await db.delete(cp)
            await db.delete(row)
            await db.commit()
            return True

    async def list(self, *, project_id=None, status=None, limit: int = 200) -> list[TrainingRun]:
        from app.db.models import V3TrainingRunRecord
        stmt = select(V3TrainingRunRecord).order_by(V3TrainingRunRecord.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(V3TrainingRunRecord.project_id == project_id)
        if status is not None:
            stmt = stmt.where(V3TrainingRunRecord.status == status)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]


class SqlCheckpointRepository(_SessionMixin, CheckpointRepository):

    @staticmethod
    def _to_domain(row) -> TrainingCheckpoint:
        return TrainingCheckpoint(
            id=row.id, run_id=row.run_id, step=row.step, epoch=row.epoch or 0.0,
            loss=row.loss, val_loss=row.val_loss, path=row.path or "",
            is_best=bool(row.is_best), artifact_id=row.artifact_id, created_at=row.created_at)

    async def add(self, checkpoint: TrainingCheckpoint) -> TrainingCheckpoint:
        from app.db.models import V3CheckpointRecord
        row = V3CheckpointRecord(
            id=checkpoint.id, run_id=checkpoint.run_id, step=checkpoint.step, epoch=checkpoint.epoch,
            loss=checkpoint.loss, val_loss=checkpoint.val_loss, path=checkpoint.path,
            is_best=int(checkpoint.is_best), artifact_id=checkpoint.artifact_id)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def list(self, run_id: str) -> list[TrainingCheckpoint]:
        from app.db.models import V3CheckpointRecord
        async with self._factory()() as db:
            rows = (await db.execute(select(V3CheckpointRecord).where(
                V3CheckpointRecord.run_id == run_id).order_by(V3CheckpointRecord.step))).scalars().all()
            return [self._to_domain(r) for r in rows]
