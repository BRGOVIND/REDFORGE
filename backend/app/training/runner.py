"""Training run orchestrator.

Drives a provider's async event stream for one run: writes live progress to the
in-memory store (for SSE + snapshots), persists checkpoints and the final metrics
to the DB, and honours pause/cancel. Runs as a background task with its OWN db
session (never the request's). Isolated — no runtime/security coupling.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.db.database import AsyncSessionLocal
from app.db.models import Checkpoint, TrainingRun
from app.logging_config import get_logger
from app.training import manager
from app.training.providers.base import TrainingConfig
from app.training.store import progress_store

logger = get_logger("training")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def run_training(run_id: str, backend: str, config: TrainingConfig,
                       session_factory=None, checkpoint_hook=None) -> None:
    """Execute one training run end-to-end. Safe to launch as a fire-and-forget
    task; all errors are captured into the run's status. ``session_factory`` is
    injectable so tests can drive it against an in-memory DB. ``checkpoint_hook``
    (optional, async) is called with each checkpoint dict — used by Continuous
    Security to schedule an evaluation without blocking training."""
    factory = session_factory or AsyncSessionLocal
    state = progress_store.start(run_id)
    provider = manager.get_provider(backend)
    start = time.time()

    async with factory() as db:
        run = await db.get(TrainingRun, run_id)
        if run is not None:
            run.status = "running"
            run.started_at = _utcnow()
            await db.commit()

    def _cancel() -> bool:
        return state.cancelled

    final_status = "completed"
    last_event: dict = {}
    try:
        async for event in provider.run(config, _cancel):
            # Cooperative pause: hold here without consuming the provider.
            while state.paused and not state.cancelled:
                await asyncio.sleep(0.2)
            ev = event.to_dict()
            last_event = ev
            progress_store.update(run_id, ev)

            if ev.get("checkpoint"):
                await _persist_checkpoint(run_id, ev["checkpoint"], factory)
                # Continuous Security: schedule an evaluation for this checkpoint.
                # Non-blocking and never fatal — a failed schedule must not stop
                # training.
                if checkpoint_hook is not None:
                    try:
                        await checkpoint_hook(ev["checkpoint"])
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("checkpoint hook failed for %s: %s", run_id, exc)
            if ev["status"] in ("completed", "failed", "cancelled"):
                final_status = ev["status"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("training run %s failed: %s", run_id, exc)
        final_status = "failed"
        last_event = {"status": "failed", "message": str(exc)}
        progress_store.update(run_id, last_event)

    # Persist the final record.
    async with factory() as db:
        run = await db.get(TrainingRun, run_id)
        if run is not None:
            run.status = final_status
            run.completed_at = _utcnow()
            run.duration_seconds = round(time.time() - start, 2)
            run.metrics = {
                "final_loss": last_event.get("loss"),
                "final_val_loss": last_event.get("val_loss"),
                "steps": last_event.get("step"),
                "total_steps": last_event.get("total_steps"),
                "epochs": last_event.get("epoch"),
            }
            await db.commit()


async def _persist_checkpoint(run_id: str, cp: dict, factory=None) -> None:
    async with (factory or AsyncSessionLocal)() as db:
        db.add(Checkpoint(
            id=str(uuid4()), run_id=run_id, step=cp.get("step", 0),
            epoch=cp.get("epoch", 0.0), loss=cp.get("loss"), val_loss=cp.get("val_loss"),
            path=cp.get("path", ""), is_best=int(cp.get("is_best", 0)),
            note=cp.get("note", ""),
        ))
        await db.commit()
