"""Training execution (RedForge V3, Epic 3).

Training runs through the Execution Platform (Constitution §8, §10.5): never directly
from an API request. This module is the ``training`` Job handler — it drives the
selected provider (reusing the existing ``TrainingProvider`` implementations),
translates provider ``ProgressEvent``s into Job progress + platform events, persists
checkpoints as **real local files + Artifacts**, and publishes the run's products
(checkpoints, adapter, metrics) into the Artifact Registry with lineage.

Nothing here imports Unsloth/Transformers directly — provider selection is via the
training manager. Nothing here touches the Runtime Engine.
"""
from __future__ import annotations

import json
import os
import time
from uuid import uuid4

from app.jobs.domain import JobResult
from app.logging_config import get_logger
from app.training.domain import TrainingCheckpoint, TrainingRun, TrainingStatus
from app.training.repository import SqlCheckpointRepository, SqlTrainingRunRepository

logger = get_logger("training-v3")

# Event names (Constitution §10 progress events).
TRAINING_STARTED = "training.started"
TRAINING_PROGRESS = "training.progress"
TRAINING_CHECKPOINT_SAVED = "training.checkpoint_saved"
TRAINING_COMPLETED = "training.completed"
TRAINING_FAILED = "training.failed"
TRAINING_CANCELLED = "training.cancelled"

# Module singletons — tests monkeypatch these to inject in-memory repos/services.
_run_repo = SqlTrainingRunRepository()
_checkpoint_repo = SqlCheckpointRepository()


def _register_transformers_provider() -> None:
    """Register the fallback Transformers provider into the training manager without
    modifying the existing providers package (additive)."""
    try:
        from app.training import manager
        from app.training.providers.transformers import TransformersProvider
        if "transformers" not in manager._PROVIDERS:
            manager.register_provider("transformers", lambda: TransformersProvider())
    except Exception:  # noqa: BLE001
        pass


async def _emit(name: str, payload: dict) -> None:
    from app.events import event_bus
    await event_bus.publish(name, payload)


def _write_manifest(path: str, data: dict) -> None:
    """Write a small JSON manifest at ``path`` so the checkpoint/adapter is a real,
    checksummable local file (for the simulation/dev path; real providers write real
    weights to the same output_dir)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _build_training_config(run: TrainingRun, records: list):
    """Translate the V3 configuration + strategy into the existing provider's
    ``TrainingConfig`` (the reuse seam). Strategy is recorded separately; the existing
    providers understand method=lora|qlora."""
    from app.training.providers.base import TrainingConfig
    c = run.configuration
    hp = c.hyperparameters
    method = "qlora" if c.strategy == "qlora" else "lora"
    return TrainingConfig(
        base_model=c.base_model, method=method, epochs=hp.epochs,
        learning_rate=hp.learning_rate, batch_size=hp.batch_size,
        gradient_accumulation=hp.gradient_accumulation, rank=c.adapter.rank,
        alpha=c.adapter.alpha, dropout=c.adapter.dropout, scheduler=hp.scheduler,
        optimizer=hp.optimizer, warmup_steps=hp.warmup_steps,
        max_seq_length=hp.max_seq_length, seed=hp.seed,
        validation_split=hp.validation_split, output_dir=run.output_dir,
        dataset_records=records)


async def _handle_training(job, ctx) -> JobResult:
    """The ``training`` Job handler."""
    _register_transformers_provider()
    from app.training import manager

    run_id = (job.params or {}).get("run_id")
    if not run_id:
        return JobResult(success=False, message="run_id is required")
    run = await _run_repo.get(run_id)
    if run is None:
        return JobResult(success=False, message="training run not found")

    # Resolve dataset records (from the V3 Dataset Platform).
    records: list = []
    if run.configuration.dataset_id:
        try:
            from app.datasets import dataset_platform
            preview = await dataset_platform.preview(run.configuration.dataset_id, offset=0, limit=100000)
            records = (preview or {}).get("rows", [])
        except Exception:  # noqa: BLE001
            records = []

    exp_id = (run.metrics or {}).get("experiment_id")   # experiment association (Epic 4)
    run.status = TrainingStatus.RUNNING
    run.started_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await _run_repo.update(run)
    await _emit(TRAINING_STARTED, {"run_id": run_id, "provider": run.configuration.provider,
                                   "experiment_id": exp_id})

    # Register the run artifact (parents: foundation + dataset, when their artifacts exist).
    parents = []
    ds_art = await _find_artifact(ctx, "dataset", run.configuration.dataset_id)
    if ds_art:
        parents.append((ds_art, "consumed"))
    fm_art = await _find_artifact(ctx, "foundation_model", run.configuration.foundation_model_id)
    if fm_art:
        parents.append((fm_art, "consumed"))
    run_art = await ctx.publish_artifact(
        type="training_run", name=run.name, table="v3_training_runs", row_id=run_id,
        parents=parents, metadata={"strategy": run.configuration.strategy,
                                   "provider": run.configuration.provider})
    run.run_artifact_id = run_art["id"] if run_art else None
    await _run_repo.update(run)

    provider = manager.get_provider(run.configuration.provider)
    config = _build_training_config(run, records)
    last_event: dict = {}
    best_ckpt_artifact = None
    start = time.time()

    # Show state immediately: a real provider's first step (model download + load)
    # can take minutes, and until it yields its first event the run would otherwise
    # sit at 0% with no message. The provider then streams its own phase events.
    await ctx.report_progress(0.0, "preparing training run…")
    await ctx.log("preparing training run…")

    try:
        async for event in provider.run(config, lambda: ctx.is_cancelled()):
            ev = event.to_dict()
            last_event = ev
            frac = (ev.get("step", 0) / ev["total_steps"]) if ev.get("total_steps") else 0.0
            await ctx.report_progress(frac, ev.get("message", ""), ev.get("step"), ev.get("total_steps"))
            await _emit(TRAINING_PROGRESS, {"run_id": run_id, "step": ev.get("step"), "loss": ev.get("loss")})
            if ev.get("message"):
                await ctx.log(f"[{ev.get('step', 0)}] {ev['message']}")

            cp = ev.get("checkpoint")
            if cp:
                ckpt_art = await _persist_checkpoint(ctx, run, cp)
                if cp.get("is_best"):
                    best_ckpt_artifact = ckpt_art
                await _emit(TRAINING_CHECKPOINT_SAVED, {"run_id": run_id, "step": cp.get("step"),
                                                        "experiment_id": exp_id})

            if ev.get("status") in ("completed", "failed", "cancelled"):
                break
    except Exception as exc:  # noqa: BLE001 - a training failure must not crash the worker
        run.status = TrainingStatus.FAILED
        run.error = str(exc)[:1000]
        run.completed_at = _now()
        await _run_repo.update(run)
        await _emit(TRAINING_FAILED, {"run_id": run_id, "error": run.error})
        return JobResult(success=False, message=f"training error: {exc}")

    status = last_event.get("status", "completed")
    if ctx.is_cancelled() or status == "cancelled":
        run.status = TrainingStatus.CANCELLED
        run.completed_at = _now()
        await _run_repo.update(run)
        await _emit(TRAINING_CANCELLED, {"run_id": run_id})
        return JobResult(success=False, message="training cancelled")
    if status == "failed":
        run.status = TrainingStatus.FAILED
        run.error = last_event.get("message", "training failed")
        run.completed_at = _now()
        await _run_repo.update(run)
        await _emit(TRAINING_FAILED, {"run_id": run_id, "error": run.error})
        return JobResult(success=False, message=run.error)

    # Success: publish the adapter artifact (adapter-based strategies) + finalize.
    from app.training.strategies import get_strategy
    adapter_artifact_id = None
    if get_strategy(run.configuration.strategy).adapter_based:
        adapter_path = os.path.join(run.output_dir or ".", "adapter.json")
        _write_manifest(adapter_path, {"run_id": run_id, "base_model": run.configuration.base_model,
                                       "strategy": run.configuration.strategy,
                                       "adapter": run.configuration.adapter.to_dict()})
        parent = [(best_ckpt_artifact["id"], "derived_from")] if best_ckpt_artifact else \
                 ([(run.run_artifact_id, "derived_from")] if run.run_artifact_id else [])
        adapter_art = await ctx.publish_artifact(
            type="adapter", name=f"{run.name} adapter", file_path=adapter_path,
            parents=parent, metadata={"run_id": run_id, "base_model": run.configuration.base_model})
        adapter_artifact_id = adapter_art["id"] if adapter_art else None

    duration = round(time.time() - start, 2)
    run.status = TrainingStatus.COMPLETED
    run.completed_at = _now()
    run.adapter_artifact_id = adapter_artifact_id
    run.metrics = {"final_loss": last_event.get("loss"), "final_val_loss": last_event.get("val_loss"),
                   "steps": last_event.get("step"), "duration_seconds": duration,
                   "experiment_id": exp_id}   # preserve the experiment association
    await _run_repo.update(run)
    await _emit(TRAINING_COMPLETED, {"run_id": run_id, "adapter": adapter_artifact_id,
                                     "experiment_id": exp_id, "final_loss": last_event.get("loss"),
                                     "duration_seconds": duration})
    produced = [a for a in (run.run_artifact_id, adapter_artifact_id) if a]
    return JobResult(success=True, data={"run": run.to_dict()}, artifact_ids=produced,
                     message="training complete")


async def _persist_checkpoint(ctx, run: TrainingRun, cp: dict):
    """Write a real checkpoint file, persist the record, and publish a file-backed
    checkpoint Artifact whose parent is the run artifact (lineage)."""
    path = cp.get("path") or os.path.join(run.output_dir or ".", f"step-{cp.get('step', 0)}")
    _write_manifest(path, {"run_id": run.id, "step": cp.get("step"), "loss": cp.get("loss"),
                           "val_loss": cp.get("val_loss"), "is_best": cp.get("is_best")})
    parents = [(run.run_artifact_id, "derived_from")] if run.run_artifact_id else []
    art = await ctx.publish_artifact(
        type="checkpoint", name=f"{run.name} step {cp.get('step')}", file_path=path,
        parents=parents, metadata={"run_id": run.id, "step": cp.get("step"),
                                   "loss": cp.get("loss"), "is_best": cp.get("is_best")})
    checkpoint = TrainingCheckpoint(
        id=str(uuid4()), run_id=run.id, step=cp.get("step", 0), epoch=cp.get("epoch", 0.0),
        loss=cp.get("loss"), val_loss=cp.get("val_loss"), path=path,
        is_best=bool(cp.get("is_best")), artifact_id=art["id"] if art else None)
    await _checkpoint_repo.add(checkpoint)
    return art


async def _find_artifact(ctx, type: str, row_id):
    if not row_id:
        return None
    try:
        found = await ctx.find_data_artifact(type, row_id)
        return found["id"] if found else None
    except Exception:  # noqa: BLE001
        return None


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc)


def register_training_handlers() -> None:
    from app.jobs.handlers import handler_registry
    _register_transformers_provider()
    handler_registry.register("training", _handle_training)
