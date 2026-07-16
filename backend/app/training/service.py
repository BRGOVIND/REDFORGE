"""Training run persistence service (DB CRUD + history + checkpoints).

Pure data layer over ``training_runs`` / ``checkpoints``. Live progress is the
store's job; this owns the durable record. No provider/runtime coupling.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Checkpoint, TrainingRun


def _run_dict(r: TrainingRun) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "name": r.name,
        "base_model": r.base_model,
        "dataset_id": r.dataset_id,
        "method": r.method,
        "backend": r.backend,
        "config": r.config or {},
        "status": r.status,
        "metrics": r.metrics or {},
        "output_dir": r.output_dir or "",
        "notes": r.notes or "",
        "duration_seconds": r.duration_seconds,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def _cp_dict(c: Checkpoint) -> dict:
    return {
        "id": c.id,
        "run_id": c.run_id,
        "step": c.step,
        "epoch": c.epoch,
        "loss": c.loss,
        "val_loss": c.val_loss,
        "path": c.path,
        "is_best": bool(c.is_best),
        "note": c.note or "",
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


class TrainingService:
    async def list(self, db: AsyncSession, *, project_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        stmt = select(TrainingRun).order_by(TrainingRun.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(TrainingRun.project_id == project_id)
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return [_run_dict(r) for r in rows]

    async def get(self, db: AsyncSession, run_id: str) -> Optional[dict]:
        r = await db.get(TrainingRun, run_id)
        return _run_dict(r) if r else None

    async def create(self, db: AsyncSession, *, name: str, base_model: str,
                     dataset_id: Optional[str], method: str, backend: str,
                     config: dict, output_dir: str = "",
                     project_id: Optional[str] = None) -> dict:
        r = TrainingRun(
            id=str(uuid4()), project_id=project_id, name=name.strip() or "Training run",
            base_model=base_model, dataset_id=dataset_id, method=method, backend=backend,
            config=config, status="pending", output_dir=output_dir,
        )
        db.add(r)
        await db.commit()
        await db.refresh(r)
        return _run_dict(r)

    async def update_notes(self, db: AsyncSession, run_id: str, notes: str) -> Optional[dict]:
        r = await db.get(TrainingRun, run_id)
        if r is None:
            return None
        r.notes = notes
        await db.commit()
        await db.refresh(r)
        return _run_dict(r)

    async def set_status(self, db: AsyncSession, run_id: str, status: str) -> Optional[dict]:
        r = await db.get(TrainingRun, run_id)
        if r is None:
            return None
        r.status = status
        await db.commit()
        await db.refresh(r)
        return _run_dict(r)

    async def delete(self, db: AsyncSession, run_id: str) -> bool:
        r = await db.get(TrainingRun, run_id)
        if r is None:
            return False
        await db.delete(r)
        await db.commit()
        return True

    # -- checkpoints -------------------------------------------------------

    async def checkpoints(self, db: AsyncSession, run_id: str) -> Optional[list[dict]]:
        r = await db.get(TrainingRun, run_id)
        if r is None:
            return None
        rows = (await db.execute(
            select(Checkpoint).where(Checkpoint.run_id == run_id).order_by(Checkpoint.step)
        )).scalars().all()
        return [_cp_dict(c) for c in rows]

    async def delete_checkpoint(self, db: AsyncSession, checkpoint_id: str) -> bool:
        c = await db.get(Checkpoint, checkpoint_id)
        if c is None:
            return False
        await db.delete(c)
        await db.commit()
        return True

    async def compare_checkpoints(self, db: AsyncSession, run_id: str,
                                  a: int, b: int) -> Optional[dict]:
        rows = (await db.execute(
            select(Checkpoint).where(Checkpoint.run_id == run_id,
                                     Checkpoint.step.in_([a, b]))
        )).scalars().all()
        by_step = {c.step: c for c in rows}
        if a not in by_step or b not in by_step:
            return None
        ca, cb = by_step[a], by_step[b]
        return {
            "a": _cp_dict(ca), "b": _cp_dict(cb),
            "loss_delta": (cb.loss - ca.loss) if (ca.loss is not None and cb.loss is not None) else None,
            "val_loss_delta": (cb.val_loss - ca.val_loss)
            if (ca.val_loss is not None and cb.val_loss is not None) else None,
        }


training_service = TrainingService()
