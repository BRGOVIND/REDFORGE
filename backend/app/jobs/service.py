"""Execution Platform — the Job System (RedForge V3, Epic 2).

The **only** execution mechanism for long-running work going forward (Constitution
§8). Domain-agnostic: it schedules, runs, tracks, recovers, cancels, and retries a
job of some registered kind — it never contains a job's domain logic (that is the
handler's, §8.2). This single engine replaces the prior architecture's four
independent background mechanisms; existing engines migrate onto it in later epics.

Guarantees, uniform across every kind (Constitution §8.3):
- A failed job ALWAYS persists a reason (message + traceback) — impossible to leave
  ``status=failed, error=null``.
- Cancellation is cooperative and uniform.
- Recovery is one routine over one table (wired in ``main.py``).
- Concurrency is a central, per-kind policy (fixes unbounded concurrent training).

Cross-context reactions are emitted as events on the shared bus (§8.6), never wired
by direct import.
"""
from __future__ import annotations

import asyncio
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.jobs import events as job_events
from app.jobs.domain import Job, JobError, JobProgress, JobResult, JobStatus
from app.jobs.handlers import JobContext, handler_registry
from app.jobs.job_types import get_job_type
from app.jobs.repository import JobRepository, SqlJobRepository
from app.logging_config import get_logger

logger = get_logger("jobs")

# Global cap on concurrently-running jobs (single-process, cooperative asyncio).
_GLOBAL_CONCURRENCY = 8


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    """The Execution Platform. Submit / query / cancel / retry jobs; the scheduler
    and workers are internal. Injectable seams (repository, artifact services,
    auto_worker) keep it offline-testable."""

    def __init__(self, repository: Optional[JobRepository] = None,
                 artifact_registry=None, artifact_query=None, auto_worker: bool = True) -> None:
        self._repo = repository or SqlJobRepository()
        self._auto_worker = auto_worker
        self._artifacts = artifact_registry
        self._artifact_query = artifact_query
        self._pending: deque[str] = deque()
        self._pending_kind: dict[str, str] = {}   # job_id -> kind (await-free per-kind checks)
        self._running: dict[str, asyncio.Task] = {}
        self._running_kind: dict[str, str] = {}   # job_id -> kind (for per-kind counting)
        self._cancelled: set[str] = set()

    def _artifact_services(self):
        """Lazily resolve the real artifact singletons in production (kept lazy to
        avoid import-order coupling); tests inject fakes via the constructor."""
        if self._artifacts is not None:
            return self._artifacts, self._artifact_query
        from app.artifacts import artifact_query, artifact_registry
        return artifact_registry, artifact_query

    # -- submission -----------------------------------------------------------

    async def submit(self, *, type: str, params: Optional[dict] = None,
                     target_ref: Optional[str] = None, project_id: Optional[str] = None,
                     experiment_id: Optional[str] = None,
                     priority: int = 0, max_attempts: Optional[int] = None) -> dict:
        """Create and enqueue a job. Non-blocking — returns immediately with the
        queued job; the scheduler runs it in the background. ``experiment_id``
        associates the job (and any artifacts it publishes) to an Experiment."""
        type_def = get_job_type(type)
        job = Job(
            id=str(uuid4()), type=type, status=JobStatus.QUEUED, params=params or {},
            target_ref=target_ref, project_id=project_id, experiment_id=experiment_id,
            priority=priority, max_attempts=max_attempts or type_def.default_max_attempts,
        )
        await self._repo.add(job)
        self._pending.append(job.id)
        self._pending_kind[job.id] = type
        if self._auto_worker:
            self._dispatch()
        return job.to_dict()

    # -- scheduling (synchronous, race-free in the single event loop) ---------

    def _dispatch(self) -> None:
        """Start as many pending jobs as global + per-kind concurrency allows.
        Synchronous and await-free, so it runs atomically in the event loop — no
        interleaving, no races over the shared queues."""
        if len(self._running) >= _GLOBAL_CONCURRENCY or not self._pending:
            return
        kind_running: dict[str, int] = {}
        for k in self._running_kind.values():
            kind_running[k] = kind_running.get(k, 0) + 1

        skipped: deque[str] = deque()
        while self._pending and len(self._running) < _GLOBAL_CONCURRENCY:
            job_id = self._pending.popleft()
            # We need the kind; cheap peek via a tracked map isn't available, so we
            # start a task that loads + checks. To respect per-kind caps *before*
            # starting, look up the kind lazily via a lightweight pre-check.
            kind = self._pending_kind.get(job_id)
            if kind is None:
                # Unknown kind at dispatch time (e.g. after restart) — start it; the
                # runner will reconcile. This path is rare (normal submit records it).
                self._start(job_id, "unknown", kind_running)
                continue
            limit = get_job_type(kind).concurrency
            if kind_running.get(kind, 0) >= limit:
                skipped.append(job_id)          # at capacity — try again next dispatch
                continue
            kind_running[kind] = kind_running.get(kind, 0) + 1
            self._start(job_id, kind, kind_running)
        # restore skipped (preserving order) to the front for the next dispatch
        while skipped:
            self._pending.appendleft(skipped.pop())

    def _start(self, job_id: str, kind: str, kind_running: dict) -> None:
        self._running_kind[job_id] = kind
        task = asyncio.create_task(self._run_job(job_id))
        self._running[job_id] = task

    @staticmethod
    def _evt(job: Job, **extra) -> dict:
        """Base event payload — always carries id/type/experiment_id so subscribers
        (e.g. the Experiment timeline) build state from the payload alone."""
        return {"id": job.id, "type": job.type, "experiment_id": job.experiment_id, **extra}

    async def _run_job(self, job_id: str) -> None:
        try:
            job = await self._repo.get(job_id)
            if job is None:
                return
            self._running_kind[job_id] = job.type
            if job_id in self._cancelled or job.status == JobStatus.CANCELLED:
                await self._finalize(job, JobStatus.CANCELLED)
                await job_events.emit(job_events.JOB_CANCELLED, self._evt(job))
                return

            job.status = JobStatus.RUNNING
            job.started_at = _utcnow()
            job.attempts += 1
            await self._repo.update(job)
            await job_events.emit(job_events.JOB_STARTED, self._evt(job))

            handler = handler_registry.get(job.type)
            if handler is None:
                job.error = JobError(message=f"no handler registered for job kind '{job.type}'",
                                     kind="no_handler")
                await self._finalize(job, JobStatus.FAILED)
                await job_events.emit(job_events.JOB_FAILED, self._evt(job, error=job.error.message))
                return

            registry, query = self._artifact_services()
            ctx = JobContext(
                job, on_progress=self._make_progress_cb(job_id), on_log=self._make_log_cb(job_id),
                is_cancelled=lambda: job_id in self._cancelled,
                artifact_registry=registry, artifact_query=query,
            )
            try:
                result: JobResult = await handler(job, ctx)
            except Exception as exc:  # noqa: BLE001 - never crash the worker; always persist a reason
                tb = traceback.format_exc()
                job.error = JobError(message=f"{type(exc).__name__}: {exc}"[:1000],
                                     kind="exception", traceback=tb[-2000:])
                await self._finalize(job, JobStatus.FAILED)
                await job_events.emit(job_events.JOB_FAILED, self._evt(job, error=job.error.message))
                return

            # reload to capture any progress/log writes, then apply the outcome
            job = await self._repo.get(job_id) or job
            if job_id in self._cancelled:
                await self._finalize(job, JobStatus.CANCELLED)
                await job_events.emit(job_events.JOB_CANCELLED, self._evt(job))
                return
            result.artifact_ids = list(dict.fromkeys([*result.artifact_ids, *ctx.produced_artifact_ids]))
            job.result = result
            if result.success:
                await self._finalize(job, JobStatus.COMPLETED)
                await job_events.emit(job_events.JOB_COMPLETED, self._evt(job, artifacts=result.artifact_ids))
            else:
                job.error = JobError(message=result.message or "job reported failure", kind="handler")
                await self._finalize(job, JobStatus.FAILED)
                await job_events.emit(job_events.JOB_FAILED, self._evt(job, error=job.error.message))
        except Exception as exc:  # noqa: BLE001 - defensive: worker must never die
            logger.warning("job worker %s crashed: %s", job_id, exc)
        finally:
            self._running.pop(job_id, None)
            self._running_kind.pop(job_id, None)
            self._pending_kind.pop(job_id, None)
            if self._auto_worker:
                self._dispatch()

    async def _finalize(self, job: Job, status: JobStatus) -> None:
        job.status = status
        job.completed_at = _utcnow()
        if status == JobStatus.COMPLETED:
            job.progress = JobProgress(fraction=1.0, message=job.progress.message or "complete")
        await self._repo.update(job)

    def _make_progress_cb(self, job_id: str):
        async def cb(fraction: float, message: str, step, total) -> None:
            job = await self._repo.get(job_id)
            if job is None:
                return
            frac = max(0.0, min(1.0, fraction))
            job.progress = JobProgress(fraction=frac, step=step, total=total, message=message)
            # ETA engine: keep a small rolling window of (timestamp, fraction) samples so
            # remaining time is estimated from the ACTUAL progress rate (a moving
            # average), never a fake countdown. Reserved metadata key; additive.
            samples = list(job.metadata.get("_eta_samples") or [])
            samples.append([_utcnow().isoformat(), frac])
            job.metadata = {**(job.metadata or {}), "_eta_samples": samples[-12:]}
            await self._repo.update(job)
            await job_events.emit(job_events.JOB_PROGRESS,
                                  {"id": job_id, "fraction": frac, "message": message})
        return cb

    def _make_log_cb(self, job_id: str):
        async def cb(message: str) -> None:
            job = await self._repo.get(job_id)
            if job is None:
                return
            job.logs = [*(job.logs or []), message][-500:]
            await self._repo.update(job)
        return cb

    # -- control --------------------------------------------------------------

    async def cancel(self, job_id: str) -> dict:
        """Cooperative cancel. A queued job is removed and marked cancelled; a
        running job stops at its handler's next cancellation check."""
        self._cancelled.add(job_id)
        if job_id in self._pending:
            self._pending.remove(job_id)
            self._pending_kind.pop(job_id, None)
            job = await self._repo.get(job_id)
            if job is not None and not job.status.is_terminal:
                await self._finalize(job, JobStatus.CANCELLED)
        return {"cancelled": True, "id": job_id}

    async def retry(self, job_id: str) -> Optional[dict]:
        """Re-queue a failed/cancelled job if it has retry budget left."""
        job = await self._repo.get(job_id)
        if job is None:
            return None
        if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.INTERRUPTED):
            return job.to_dict()
        if job.attempts >= job.max_attempts and job.status == JobStatus.FAILED:
            return {**job.to_dict(), "retry_refused": "max attempts reached"}
        self._cancelled.discard(job_id)
        job.status = JobStatus.QUEUED
        job.error = None
        job.completed_at = None
        job.progress = JobProgress()
        await self._repo.update(job)
        self._pending.append(job_id)
        self._pending_kind[job_id] = job.type
        if self._auto_worker:
            self._dispatch()
        return job.to_dict()

    # -- reads ----------------------------------------------------------------

    async def get(self, job_id: str) -> Optional[dict]:
        job = await self._repo.get(job_id)
        return job.to_dict() if job else None

    async def list(self, *, status=None, type=None, project_id=None, limit: int = 200) -> list[dict]:
        return [j.to_dict() for j in await self._repo.list(
            status=status, type=type, project_id=project_id, limit=limit)]

    async def progress(self, job_id: str) -> Optional[dict]:
        job = await self._repo.get(job_id)
        return {"id": job.id, "status": job.status.value, **job.progress.to_dict()} if job else None

    async def logs(self, job_id: str) -> Optional[list[str]]:
        job = await self._repo.get(job_id)
        return job.logs if job else None

    def queue_status(self) -> dict:
        return {"pending": list(self._pending), "running": list(self._running.keys()),
                "queued": len(self._pending), "active": len(self._running)}

    # -- test driver ----------------------------------------------------------

    async def drain(self) -> None:
        """Run all pending jobs to completion (tests use this instead of the
        background scheduler). Respects concurrency; safe re-entry."""
        guard = 0
        while (self._pending or self._running) and guard < 10_000:
            guard += 1
            self._dispatch()
            tasks = list(self._running.values())
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            elif self._pending:
                break  # nothing dispatchable and nothing running — avoid a spin


# Module-level singleton (default SQL repository, auto worker on). Tests build their
# own with auto_worker=False + drain().
job_service = JobService()
