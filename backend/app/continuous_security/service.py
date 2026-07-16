"""Continuous Security orchestration service.

Schedules a security evaluation per training checkpoint, runs jobs through an
async single-worker queue (non-blocking, cancellable), stores per-checkpoint
results, and exposes the timeline + checkpoint comparison. The evaluation itself
is delegated to the existing Security Center via an injectable ``evaluate_fn``
(default reuses ``SessionManager`` + ``analysis``) — no second engine.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from sqlalchemy import select

from app.db.models import CheckpointSecurity
from app.logging_config import get_logger

logger = get_logger("continuous-security")

# evaluate_fn(target_model, profile) -> {score, categories, findings, session_id?}
EvaluateFn = Callable[[str, str], Awaitable[dict]]

# Attack-profile → evaluation category subset (reuses existing attack categories).
PROFILE_CATEGORIES: dict[str, Optional[list[str]]] = {
    "quick": ["PROMPT_INJECTION", "JAILBREAK"],
    "standard": ["PROMPT_INJECTION", "JAILBREAK", "CONTEXT_MANIPULATION"],
    "full": None,          # None → all categories
    "custom": None,        # caller supplies categories in the run config
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(cs: CheckpointSecurity) -> dict:
    return {
        "id": cs.id,
        "run_id": cs.run_id,
        "checkpoint_id": cs.checkpoint_id,
        "step": cs.step,
        "target_model": cs.target_model,
        "profile": cs.profile,
        "status": cs.status,
        "score": cs.score,
        "categories": cs.categories or [],
        "findings": cs.findings or [],
        "session_id": cs.session_id,
        "runtime_id": cs.runtime_id,
        "provider": cs.provider,
        "error": cs.error,
        "created_at": cs.created_at.isoformat() if cs.created_at else None,
        "completed_at": cs.completed_at.isoformat() if cs.completed_at else None,
    }


class ContinuousSecurityService:
    def __init__(self, evaluate_fn: Optional[EvaluateFn] = None, session_factory=None,
                 auto_worker: bool = True) -> None:
        self._evaluate_fn = evaluate_fn  # None → lazy default (reuses the engine)
        self._session_factory = session_factory  # None → AsyncSessionLocal
        self._auto_worker = auto_worker  # tests disable to drive via drain()
        self._queue: deque[str] = deque()
        self._cancelled: set[str] = set()
        self._current: Optional[str] = None
        self._worker: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()  # serializes processing (worker vs. drain)

    # -- factory helpers ---------------------------------------------------

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    async def _evaluate(self, target_model: str, profile: str) -> dict:
        if self._evaluate_fn is not None:
            return await self._evaluate_fn(target_model, profile)
        return await _default_evaluate(target_model, profile, self._factory())

    # -- scheduling --------------------------------------------------------

    async def schedule(
        self, *, run_id: str, step: int, target_model: str,
        checkpoint_id: Optional[str] = None, profile: str = "quick",
        runtime_id: Optional[str] = None, provider: Optional[str] = None,
    ) -> dict:
        """Create a pending checkpoint-security job and enqueue it. Non-blocking.
        ``runtime_id``/``provider`` link the evaluated model to the Runtime Registry
        (a registered checkpoint, or the base-model fallback)."""
        cs = CheckpointSecurity(
            id=str(uuid4()), run_id=run_id, checkpoint_id=checkpoint_id, step=step,
            target_model=target_model, profile=profile, status="pending",
            runtime_id=runtime_id, provider=provider,
        )
        async with self._factory()() as db:
            db.add(cs)
            await db.commit()
        self._queue.append(cs.id)
        self._ensure_worker()
        return {"id": cs.id, "status": "pending", "step": step}

    def _ensure_worker(self) -> None:
        if not self._auto_worker:
            return
        if self._worker is None or self._worker.done():
            try:
                self._worker = asyncio.create_task(self._process_all())
            except RuntimeError:
                # No running loop (e.g. sync context) — jobs are drained explicitly.
                self._worker = None

    async def _process_all(self) -> None:
        """Drain the queue one job at a time. The lock guarantees the background
        worker and an explicit drain() never process concurrently (no races)."""
        async with self._lock:
            while self._queue:
                await self._run_job(self._queue.popleft())

    async def drain(self) -> None:
        """Process all queued jobs (used by tests / explicit runs). Safe alongside
        the background worker — the lock serializes them."""
        await self._process_all()

    async def _run_job(self, job_id: str) -> None:
        self._current = job_id
        try:
            async with self._factory()() as db:
                cs = await db.get(CheckpointSecurity, job_id)
                if cs is None:
                    return
                if job_id in self._cancelled or cs.status == "cancelled":
                    cs.status = "cancelled"
                    await db.commit()
                    return
                cs.status = "running"
                await db.commit()
                target, profile = cs.target_model, cs.profile

            result = await self._evaluate(target, profile)

            async with self._factory()() as db:
                cs = await db.get(CheckpointSecurity, job_id)
                if cs is None:
                    return
                if job_id in self._cancelled:
                    cs.status = "cancelled"
                else:
                    cs.status = "completed"
                    cs.score = result.get("score")
                    cs.categories = result.get("categories", [])
                    cs.findings = result.get("findings", [])
                    cs.session_id = result.get("session_id")
                cs.completed_at = _utcnow()
                await db.commit()
        except Exception as exc:  # noqa: BLE001 - a failed eval must never crash training
            logger.warning("checkpoint security job %s failed: %s", job_id, exc)
            try:
                async with self._factory()() as db:
                    cs = await db.get(CheckpointSecurity, job_id)
                    if cs is not None:
                        cs.status = "failed"
                        cs.error = str(exc)[:500]
                        cs.completed_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._current = None

    async def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job. A pending job is removed from the
        queue and its DB row marked cancelled; a running job stops after its
        current step (the worker observes the cancelled flag)."""
        self._cancelled.add(job_id)
        was_queued = job_id in self._queue
        if was_queued:
            self._queue.remove(job_id)
        # Persist cancellation for a job that will now never run.
        if was_queued:
            try:
                async with self._factory()() as db:
                    cs = await db.get(CheckpointSecurity, job_id)
                    if cs is not None and cs.status in ("pending", "running"):
                        cs.status = "cancelled"
                        cs.completed_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
        return True

    # -- reads: timeline, comparison, queue --------------------------------

    async def timeline(self, run_id: str) -> list[dict]:
        async with self._factory()() as db:
            rows = (await db.execute(
                select(CheckpointSecurity)
                .where(CheckpointSecurity.run_id == run_id)
                .order_by(CheckpointSecurity.step)
            )).scalars().all()
        return [_to_dict(r) for r in rows]

    async def compare(self, run_id: str, step_a: int, step_b: int) -> Optional[dict]:
        async with self._factory()() as db:
            rows = (await db.execute(
                select(CheckpointSecurity).where(
                    CheckpointSecurity.run_id == run_id,
                    CheckpointSecurity.step.in_([step_a, step_b]),
                    CheckpointSecurity.status == "completed",
                )
            )).scalars().all()
        by_step = {r.step: r for r in rows}
        if step_a not in by_step or step_b not in by_step:
            return None
        a, b = by_step[step_a], by_step[step_b]
        cat_a = {c["category"]: c for c in (a.categories or [])}
        cat_b = {c["category"]: c for c in (b.categories or [])}

        improved, regressed, resolved, new_vuln = [], [], [], []
        for cat in set(cat_a) | set(cat_b):
            sa = cat_a.get(cat, {}).get("score")
            sb = cat_b.get(cat, {}).get("score")
            ra = (cat_a.get(cat, {}).get("risk_level") or "none")
            rb = (cat_b.get(cat, {}).get("risk_level") or "none")
            if sa is not None and sb is not None:
                if sb > sa + 0.5:
                    improved.append(cat)
                elif sb < sa - 0.5:
                    regressed.append(cat)
            # resolved: had risk at A, none at B; new: none at A, risk at B
            if ra != "none" and rb == "none":
                resolved.append(cat)
            elif ra == "none" and rb != "none":
                new_vuln.append(cat)

        return {
            "run_id": run_id,
            "a": {"step": step_a, "score": a.score},
            "b": {"step": step_b, "score": b.score},
            "score_delta": (b.score - a.score) if (a.score is not None and b.score is not None) else None,
            "improved_categories": sorted(improved),
            "regressed_categories": sorted(regressed),
            "resolved_vulnerabilities": sorted(resolved),
            "new_vulnerabilities": sorted(new_vuln),
        }

    def queue_status(self) -> dict:
        return {
            "pending": list(self._queue),
            "running": self._current,
            "queued": len(self._queue),
        }


# ---------------------------------------------------------------------------
# Default evaluator — reuses the existing Security Center engine.
# ---------------------------------------------------------------------------

async def _default_evaluate(target_model: str, profile: str, session_factory) -> dict:
    """Run a real evaluation via the existing engine and return a compact result.

    Reuses ``SessionManager`` (batch run) + ``analysis.security_analyzer`` — no new
    engine. Requires a reachable runtime provider + seeded attacks, exactly like a
    normal evaluation; any failure propagates and the job is recorded as failed.
    """
    from app.sessions.constants import EventType, SessionType
    from app.sessions.session_manager import SessionManager
    from app.analysis.security_analyzer import AttackResult, analyze

    manager = SessionManager(session_factory=session_factory)
    categories = PROFILE_CATEGORIES.get(profile)
    session = await manager.create_session(
        session_type=SessionType.BATCH,
        selected_models=[target_model],
        selected_categories=categories or [],
    )
    await manager.run_session(session.id)

    events = await manager.get_events(session.id, event_type=EventType.VERDICT_GENERATED)
    results: list[AttackResult] = []
    for ev in events:
        meta = ev.event_metadata or {}
        results.append(AttackResult(
            attack_name=meta.get("attack_name", ""),
            category=meta.get("category", ""),
            severity=meta.get("severity", "medium"),
            verdict=meta.get("verdict", "UNCERTAIN"),
            response_excerpt=(meta.get("model_response", "") or "")[:200],
        ))
    analysis = analyze(target_model, results)
    return {
        "score": analysis.overall_security_score,
        "categories": [
            {"category": c.category, "score": c.score, "fail_rate": c.fail_rate,
             "risk_level": c.risk_level}
            for c in analysis.category_scores
        ],
        "findings": [
            {"category": v.category, "attack_name": v.attack_name, "severity": v.severity}
            for v in analysis.top_vulnerabilities[:5]
        ],
        "session_id": session.id,
    }


continuous_security = ContinuousSecurityService()
