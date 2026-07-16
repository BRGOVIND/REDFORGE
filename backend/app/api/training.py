"""Training Lab API (RedForge V2, Phase 2.2).

Local LoRA/QLoRA training as first-class runs. Additive router under
``/api/training``; isolated from runtime/security. Training executes through the
swappable Training Manager provider (simulation by default; Unsloth when the GPU
+ ML stack exist) — never a hardcoded backend.

Live progress is exposed two ways: an SSE stream (``/stream``) and a JSON
snapshot (``/progress``) for robust polling. Nothing is ever uploaded.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.continuous_security import continuous_security
from app.datasets_lab import dataset_service
from app.db.database import get_db
from app.runtime_registry import runtime_registry
from app.training import manager, training_service
from app.training.providers.base import TrainingConfig
from app.training.runner import run_training
from app.training.store import progress_store

router = APIRouter(prefix="/api/training", tags=["training"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TrainingParams(BaseModel):
    epochs: int = Field(3, ge=1, le=100)
    learning_rate: float = Field(2e-4, gt=0, le=1)
    batch_size: int = Field(2, ge=1, le=256)
    gradient_accumulation: int = Field(4, ge=1, le=256)
    rank: int = Field(16, ge=1, le=512)
    alpha: int = Field(32, ge=1, le=1024)
    dropout: float = Field(0.05, ge=0, le=0.9)
    scheduler: str = "cosine"
    optimizer: str = "adamw_8bit"
    warmup_steps: int = Field(10, ge=0, le=10000)
    max_seq_length: int = Field(2048, ge=8, le=131072)
    seed: int = 42
    validation_split: float = Field(0.1, ge=0, le=0.9)
    output_dir: str = ""


class LaunchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    base_model: str = Field(..., min_length=1)
    dataset_id: Optional[str] = None
    method: str = Field("lora", pattern="^(lora|qlora)$")
    backend: Optional[str] = None          # None → default (simulation)
    params: TrainingParams = TrainingParams()
    project_id: Optional[str] = None
    # Continuous Security: auto-evaluate each checkpoint with this attack profile.
    continuous_security: bool = False
    security_profile: str = Field("quick", pattern="^(quick|standard|full|custom)$")


class NotesRequest(BaseModel):
    notes: str


# ---------------------------------------------------------------------------
# Backends / metadata
# ---------------------------------------------------------------------------

@router.get("/backends")
async def backends() -> dict:
    # Default is auto-detected: real Unsloth when the GPU + ML stack exist,
    # otherwise the dependency-free simulation.
    return {"backends": manager.available_backends(), "default": manager.default_backend()}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@router.get("")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=200),
) -> list[dict]:
    return await training_service.list(db, project_id=project_id, limit=limit)


@router.post("/launch", status_code=202)
async def launch(req: LaunchRequest, db: AsyncSession = Depends(get_db)) -> dict:
    backend = (req.backend or manager.default_backend()).lower()

    # Load dataset records (local) if a dataset is attached.
    records: list[Any] = []
    if req.dataset_id:
        records = await dataset_service._current_records(db, req.dataset_id) or []

    config_public = {
        "method": req.method, **req.params.model_dump(),
        "continuous_security": req.continuous_security,
        "security_profile": req.security_profile,
    }
    run = await training_service.create(
        db, name=req.name, base_model=req.base_model, dataset_id=req.dataset_id,
        method=req.method, backend=backend, config=config_public,
        output_dir=req.params.output_dir, project_id=req.project_id,
    )

    cfg = TrainingConfig(
        base_model=req.base_model, method=req.method, dataset_records=records,
        **req.params.model_dump(),
    )

    # Continuous Security hook — register the checkpoint in the Runtime Registry,
    # then evaluate the *resolved runnable model* via the existing Security Center.
    # The registry falls back to the base model until real adapters can be hosted,
    # but the checkpoint identity + runtime linkage are recorded either way.
    # Non-blocking; never fatal to training.
    hook = None
    if req.continuous_security:
        run_id, base, prof = run["id"], req.base_model, req.security_profile
        eval_provider = settings.RUNTIME_PROVIDER.lower()

        async def hook(cp: dict) -> None:  # noqa: ANN001
            from app.db.database import AsyncSessionLocal
            step = cp.get("step", 0)
            registry_id, target = None, base
            try:
                async with AsyncSessionLocal() as db2:
                    reg = await runtime_registry.register_checkpoint(
                        db2, run_id=run_id, step=step, base_model=base,
                        provider=eval_provider, project_id=req.project_id,
                        label=f"Checkpoint (step {step})",
                    )
                    registry_id = reg["id"]
                    target = reg["runtime_model"]
            except Exception:  # noqa: BLE001 - registry failure must not stop training
                registry_id, target = None, base
            await continuous_security.schedule(
                run_id=run_id, step=step, target_model=target,
                checkpoint_id=None, profile=prof,
                runtime_id=registry_id, provider=eval_provider,
            )

    # Fire-and-forget background run (own DB session inside the runner).
    asyncio.create_task(run_training(run["id"], backend, cfg, checkpoint_hook=hook))
    return {"run": run, "backend": backend, "streaming": True,
            "continuous_security": req.continuous_security}


@router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    r = await training_service.get(db, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return r


@router.patch("/{run_id}/notes")
async def set_notes(run_id: str, req: NotesRequest, db: AsyncSession = Depends(get_db)) -> dict:
    r = await training_service.update_notes(db, run_id, req.notes)
    if r is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return r


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    progress_store.cancel(run_id)
    await training_service.set_status(db, run_id, "cancelled")
    return {"cancelled": True, "id": run_id}


@router.post("/{run_id}/pause")
async def pause_run(run_id: str, paused: bool = Query(True)) -> dict:
    ok = progress_store.pause(run_id, paused)
    if not ok:
        raise HTTPException(status_code=404, detail="run not active")
    return {"paused": paused, "id": run_id}


@router.delete("/{run_id}")
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not await training_service.delete(db, run_id):
        raise HTTPException(status_code=404, detail="training run not found")
    progress_store.discard(run_id)
    return {"deleted": True, "id": run_id}


# ---------------------------------------------------------------------------
# Live progress: snapshot (poll) + SSE (stream)
# ---------------------------------------------------------------------------

@router.get("/{run_id}/progress")
async def progress(run_id: str) -> dict:
    st = progress_store.get(run_id)
    if st is None:
        return {"run_id": run_id, "status": "idle", "latest": {}, "history": [], "logs": [], "paused": False}
    return st.snapshot()


@router.get("/{run_id}/stream")
async def stream(run_id: str) -> StreamingResponse:
    """Server-Sent Events stream of live progress until the run finishes."""

    async def gen():
        terminal = {"completed", "failed", "cancelled"}
        while True:
            st = progress_store.get(run_id)
            if st is None:
                yield f"data: {json.dumps({'status': 'idle'})}\n\n"
                return
            yield f"data: {json.dumps(st.snapshot(history_tail=1))}\n\n"
            if st.status in terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

@router.get("/{run_id}/checkpoints")
async def list_checkpoints(run_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    cps = await training_service.checkpoints(db, run_id)
    if cps is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return cps


@router.get("/{run_id}/checkpoints/compare")
async def compare_checkpoints(
    run_id: str, a: int = Query(...), b: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = await training_service.compare_checkpoints(db, run_id, a, b)
    if r is None:
        raise HTTPException(status_code=404, detail="checkpoints not found")
    return r


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint(checkpoint_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not await training_service.delete_checkpoint(db, checkpoint_id):
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return {"deleted": True, "id": checkpoint_id}


# ---------------------------------------------------------------------------
# Continuous Security — per-checkpoint evaluation timeline + comparison
# ---------------------------------------------------------------------------

@router.get("/{run_id}/security")
async def security_timeline(run_id: str) -> dict:
    """The security timeline: one evaluation result per checkpoint, ordered by step."""
    return {"run_id": run_id, "timeline": await continuous_security.timeline(run_id)}


@router.get("/{run_id}/report")
async def training_report(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Composed engineering report — reuses existing data, stores nothing new.

    Stitches training summary, dataset summary, security timeline, checkpoint
    comparison, recommendations (predicted vs actual + accuracy), registered
    models, final config, and an executive summary into one payload.
    """
    from sqlalchemy import select

    from app.db.models import (
        BenchmarkResult, CheckpointSecurity, Dataset, Recommendation, RegisteredModel, TrainingRun,
    )

    run = await db.get(TrainingRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="training run not found")

    # Dataset summary.
    dataset = None
    if run.dataset_id:
        d = await db.get(Dataset, run.dataset_id)
        if d is not None:
            meta = d.dataset_metadata or {}
            dataset = {"id": d.id, "name": d.name, "record_count": d.record_count,
                       "quality_score": meta.get("quality_score")}

    # Security timeline + comparison (first vs last completed).
    sec = (await db.execute(
        select(CheckpointSecurity)
        .where(CheckpointSecurity.run_id == run_id, CheckpointSecurity.status == "completed")
        .order_by(CheckpointSecurity.step)
    )).scalars().all()
    timeline = [{"step": s.step, "score": s.score, "runtime_id": s.runtime_id,
                 "provider": s.provider, "categories": s.categories or []} for s in sec]
    scored = [s for s in sec if s.score is not None]
    comparison = None
    if len(scored) >= 2:
        comparison = {
            "first": {"step": scored[0].step, "score": scored[0].score},
            "last": {"step": scored[-1].step, "score": scored[-1].score},
            "delta": round(scored[-1].score - scored[0].score, 2),
        }

    # Recommendations (predicted vs actual).
    recs = (await db.execute(
        select(Recommendation).where(Recommendation.run_id == run_id)
    )).scalars().all()
    recommendations = [{
        "id": r.id, "status": r.status,
        "predicted": (r.payload or {}).get("prediction", {}).get("expected_security_gain"),
        "outcome": r.outcome,
        "hyperparameters": (r.payload or {}).get("hyperparameters"),
    } for r in recs]
    accepted = [r for r in recommendations if r["status"] in ("accepted", "applied")]
    rejected = [r for r in recommendations if r["status"] == "rejected"]

    # Registered (runnable) models.
    registered = (await db.execute(
        select(RegisteredModel).where(RegisteredModel.run_id == run_id,
                                      RegisteredModel.status == "registered")
    )).scalars().all()
    final_models = [{"id": m.id, "label": m.label, "runtime_model": m.runtime_model,
                     "fallback": bool(m.fallback)} for m in registered]

    # Benchmark results for this run's models (Phase 3) — reuse existing data, no
    # separate report. Latest completed result per model, with per-suite scores.
    bench_rows = (await db.execute(
        select(BenchmarkResult)
        .where(BenchmarkResult.run_id == run_id, BenchmarkResult.status == "completed")
        .order_by(BenchmarkResult.created_at.desc())
    )).scalars().all()
    seen_models: set[str] = set()
    benchmarks = []
    for b in bench_rows:
        if b.target_model in seen_models:
            continue
        seen_models.add(b.target_model)
        benchmarks.append({
            "id": b.id, "label": b.label or b.target_model, "target_model": b.target_model,
            "registry_id": b.registry_id, "overall_score": b.overall_score,
            "scores": b.scores or {}, "suites": b.suites or [],
        })
    best_benchmark = max(
        (b for b in benchmarks if b["overall_score"] is not None),
        key=lambda b: b["overall_score"], default=None,
    )

    exec_summary = (
        f"{run.name}: {run.method.upper()} on {run.base_model} ({run.backend}), status {run.status}. "
        + (f"Security {comparison['first']['score']} → {comparison['last']['score']} "
           f"({comparison['delta']:+.0f} over {len(scored)} checkpoints). "
           if comparison else "No security timeline recorded. ")
        + f"{len(accepted)} recommendation(s) accepted, {len(rejected)} rejected."
    )
    remaining = []
    if scored:
        for c in (scored[-1].categories or []):
            if (c.get("risk_level") or "none") not in ("none",):
                remaining.append(c.get("category"))

    return {
        "run_id": run_id,
        "executive_summary": exec_summary,
        "training_summary": {
            "name": run.name, "base_model": run.base_model, "method": run.method,
            "backend": run.backend, "status": run.status, "metrics": run.metrics or {},
            "duration_seconds": run.duration_seconds,
        },
        "final_configuration": run.config or {},
        "dataset_summary": dataset,
        "security_timeline": timeline,
        "checkpoint_comparison": comparison,
        "recommendations": recommendations,
        "accepted_recommendations": accepted,
        "rejected_recommendations": rejected,
        "final_models": final_models,
        "benchmarks": benchmarks,
        "best_benchmark": best_benchmark,
        "remaining_risks": sorted(set(remaining)),
    }


@router.get("/{run_id}/security/compare")
async def security_compare(run_id: str, a: int = Query(...), b: int = Query(...)) -> dict:
    r = await continuous_security.compare(run_id, a, b)
    if r is None:
        raise HTTPException(status_code=404, detail="checkpoint security results not found")
    return r


@router.get("/security/queue")
async def security_queue() -> dict:
    """Continuous-security evaluation queue status (pending / running)."""
    return continuous_security.queue_status()


@router.post("/security/{job_id}/cancel")
async def security_cancel(job_id: str) -> dict:
    await continuous_security.cancel(job_id)
    return {"cancelled": True, "id": job_id}
