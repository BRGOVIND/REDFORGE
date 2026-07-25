"""Job handlers + execution context (RedForge V3, Epic 2).

The Execution Platform is domain-agnostic: it knows how to run *a job*, not what a
job *means*. Each job kind registers a **handler** — an async callable that does the
work, reports progress, checks cancellation, and (optionally) publishes artifacts.
Handlers are registered into a flat registry (the provider pattern); a new job kind
is a new registered handler, never a change to the scheduler (Constitution §8.2).

Epic 2 ships a few real handlers to prove the platform end-to-end WITHOUT touching
the big engines (which migrate to Jobs in later epics):
- ``model_discovery`` / ``model_sync`` — call the Epic-1 Foundation service (read),
  and ``model_sync`` idempotently ensures the foundation model's Artifact exists,
  demonstrating the full Job → progress → result → **publish artifact** pipeline.
- ``diagnostics`` — a trivial, cancellation-and-progress-exercising handler.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from app.jobs.domain import Job, JobResult
from app.logging_config import get_logger

logger = get_logger("jobs")

# handler(job, ctx) -> JobResult
JobHandler = Callable[["Job", "JobContext"], Awaitable[JobResult]]


class JobContext:
    """What a handler is given: progress reporting, logging, cooperative
    cancellation, and artifact publishing. All side effects a handler needs go
    through here, so handlers stay decoupled from the execution machinery and are
    unit-testable with a fake context."""

    def __init__(self, job: Job, *, on_progress=None, on_log=None, is_cancelled=None,
                 artifact_registry=None, artifact_query=None) -> None:
        self.job = job
        self._on_progress = on_progress
        self._on_log = on_log
        self._is_cancelled = is_cancelled or (lambda: False)
        self._artifacts = artifact_registry
        self._artifact_query = artifact_query
        self.produced_artifact_ids: list[str] = []

    async def report_progress(self, fraction: float, message: str = "",
                              step: Optional[int] = None, total: Optional[int] = None) -> None:
        if self._on_progress is not None:
            await self._on_progress(fraction, message, step, total)

    async def log(self, message: str) -> None:
        if self._on_log is not None:
            await self._on_log(message)

    def is_cancelled(self) -> bool:
        return bool(self._is_cancelled())

    async def publish_artifact(self, **kwargs) -> Optional[dict]:
        """Register + publish an artifact produced by this job, recording its id on
        the result. Honest no-op if no registry was wired (never raises)."""
        if self._artifacts is None:
            return None
        kwargs.setdefault("producer", f"job:{self.job.id}")
        # Auto-associate produced artifacts with the job's Experiment (if any).
        if getattr(self.job, "experiment_id", None) and not kwargs.get("experiment_id"):
            kwargs["experiment_id"] = self.job.experiment_id
        artifact = await self._artifacts.register(**kwargs)
        published = await self._artifacts.publish(artifact["id"])
        aid = (published or artifact)["id"]
        self.produced_artifact_ids.append(aid)
        return published or artifact

    async def get_artifact(self, artifact_id: str) -> Optional[dict]:
        """Read an artifact by id (for handlers that consume an input artifact —
        e.g. Export reading a checkpoint/adapter). Honest no-op without a registry."""
        if self._artifacts is None:
            return None
        return await self._artifacts.get(artifact_id)

    async def find_data_artifact(self, type: str, row_id: str) -> Optional[dict]:
        """Idempotency helper: find an existing data-backed artifact of ``type``
        referencing ``row_id`` (so repeated jobs don't create duplicate artifacts)."""
        if self._artifact_query is None:
            return None
        candidates = await self._artifact_query.search(type=type, limit=500)
        for a in candidates:
            if (a.get("location") or {}).get("row_id") == row_id:
                return a
        return None


class JobHandlerRegistry:
    """Flat registry of kind → handler. First-party handlers register at import;
    later epics/plugins register more the same way."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    def get(self, kind: str) -> Optional[JobHandler]:
        return self._handlers.get(kind)

    def kinds(self) -> list[str]:
        return sorted(self._handlers)


handler_registry = JobHandlerRegistry()


# ---------------------------------------------------------------------------
# Built-in handlers (Epic 2)
# ---------------------------------------------------------------------------

async def _handle_model_discovery(job: Job, ctx: JobContext) -> JobResult:
    """Discover foundation-model candidates from installed runtime models (Epic 1)."""
    from app.foundation_models import foundation_model_service
    await ctx.report_progress(0.1, "scanning installed runtime models")
    candidates = await foundation_model_service.discover()
    await ctx.report_progress(1.0, f"found {len(candidates)} candidate(s)")
    return JobResult(success=True, data={"candidates": candidates},
                     message=f"discovered {len(candidates)} runtime model(s)")


async def _handle_model_sync(job: Job, ctx: JobContext) -> JobResult:
    """Sync a foundation model (Epic 1) AND ensure its Artifact exists — the full
    Job → publish-artifact pipeline over real data. Idempotent: reuses the existing
    artifact if one already references this foundation-model row."""
    from app.foundation_models import foundation_model_service
    model_id = (job.params or {}).get("model_id")
    if not model_id:
        return JobResult(success=False, message="model_id is required")

    await ctx.report_progress(0.2, "syncing foundation model")
    synced = await foundation_model_service.sync(model_id)
    if synced is None:
        return JobResult(success=False, message="foundation model not found")

    if ctx.is_cancelled():
        return JobResult(success=False, message="cancelled before artifact publish")

    await ctx.report_progress(0.6, "ensuring artifact")
    existing = await ctx.find_data_artifact("foundation_model", model_id)
    if existing is None:
        await ctx.publish_artifact(
            type="foundation_model", name=synced["hf_repo"],
            table="foundation_models", row_id=model_id,
            metadata={"hf_repo": synced["hf_repo"], "status": synced["status"]})
    await ctx.report_progress(1.0, "synced")
    return JobResult(success=True, data={"foundation_model": synced},
                     message=f"synced {synced['hf_repo']}")


async def _handle_diagnostics(job: Job, ctx: JobContext) -> JobResult:
    """A trivial handler that exercises progress + cancellation (used for health
    checks and as the reference minimal handler)."""
    steps = int((job.params or {}).get("steps", 3))
    for i in range(1, steps + 1):
        if ctx.is_cancelled():
            return JobResult(success=False, message="cancelled")
        await ctx.report_progress(i / steps, f"step {i}/{steps}", step=i, total=steps)
    return JobResult(success=True, data={"ok": True, "steps": steps}, message="diagnostics complete")


def _register_builtins() -> None:
    handler_registry.register("model_discovery", _handle_model_discovery)
    handler_registry.register("model_sync", _handle_model_sync)
    handler_registry.register("diagnostics", _handle_diagnostics)


_register_builtins()
