"""Experiment Platform — Event Bus subscriber (RedForge V3, Epic 4).

Auto-populates each experiment's timeline + job references by *observing* platform
events (Constitution §7 timeline, §8.6). It reads only event payloads — which carry
``experiment_id`` — so it needs NO direct dependency on the Job System or the engines
(§14). This is the "engines publish into the Experiment via events" mechanism.

Registered at startup via ``register_experiment_subscribers``. Idempotent and
resilient — a subscriber failure never breaks the publisher (the Event Bus already
swallows subscriber exceptions).
"""
from __future__ import annotations

from typing import Optional

_FRIENDLY = {
    "training": "Training", "export": "Export", "benchmark": "Benchmark",
    "evaluation": "Evaluation", "security_scan": "Security scan",
    "dataset_processing": "Dataset processing", "dataset_import": "Dataset import",
    "model_sync": "Model sync", "model_discovery": "Model discovery",
}


def _label(job_type: Optional[str]) -> str:
    return _FRIENDLY.get(job_type or "", (job_type or "Job").replace("_", " ").title())


def register_experiment_subscribers(service=None, bus=None) -> list:
    """Bind timeline/job-ref subscribers to the Event Bus. Returns unsubscribe
    callables. ``service``/``bus`` are injectable for testing."""
    if service is None:
        from app.experiments.service import experiment_service as service
    if bus is None:
        from app.events import event_bus as bus

    async def on_job_started(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        await service.upsert_job_ref(exp, p["id"], job_type=p.get("type", ""), status="running")
        await service.record_timeline(exp, kind="job.started",
                                      title=f"{_label(p.get('type'))} started", payload={"job_id": p["id"]})

    async def on_job_completed(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        await service.upsert_job_ref(exp, p["id"], job_type=p.get("type", ""), status="completed")
        arts = p.get("artifacts") or []
        await service.record_timeline(exp, kind="job.completed",
                                      title=f"{_label(p.get('type'))} completed",
                                      payload={"job_id": p["id"], "artifacts": arts})

    async def on_job_failed(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        await service.upsert_job_ref(exp, p["id"], job_type=p.get("type", ""), status="failed")
        await service.record_timeline(exp, kind="job.failed",
                                      title=f"{_label(p.get('type'))} failed",
                                      payload={"job_id": p["id"], "error": p.get("error")})

    async def on_job_cancelled(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        await service.upsert_job_ref(exp, p["id"], job_type=p.get("type", ""), status="cancelled")
        await service.record_timeline(exp, kind="job.cancelled",
                                      title=f"{_label(p.get('type'))} cancelled", payload={"job_id": p["id"]})

    async def on_training_completed(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        if p.get("final_loss") is not None:
            await service.record_metric(exp, "final_loss", p["final_loss"])
        if p.get("duration_seconds") is not None:
            await service.record_metric(exp, "training_duration_seconds", p["duration_seconds"])

    async def on_checkpoint(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        await service.record_timeline(exp, kind="checkpoint.created",
                                      title=f"Checkpoint at step {p.get('step')}", payload=p)

    async def on_artifact_published(event):
        p = event.payload
        exp = p.get("experiment_id")
        if not exp:
            return
        await service.record_timeline(exp, kind="artifact.published",
                                      title=f"{p.get('type', 'artifact')} artifact published",
                                      payload={"artifact_id": p.get("id"), "type": p.get("type")})

    unsubs = [
        bus.subscribe("job.started", on_job_started),
        bus.subscribe("job.completed", on_job_completed),
        bus.subscribe("job.failed", on_job_failed),
        bus.subscribe("job.cancelled", on_job_cancelled),
        bus.subscribe("training.completed", on_training_completed),
        bus.subscribe("training.checkpoint_saved", on_checkpoint),
        bus.subscribe("artifact.published", on_artifact_published),
    ]
    return unsubs
