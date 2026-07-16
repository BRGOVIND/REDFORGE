"""Benchmark Center orchestration service.

Schedules one benchmark job per model, runs jobs through an async single-worker
queue (non-blocking, cancellable) that mirrors Continuous Security, stores results
per model, and exposes history / leaderboard / trends / comparison. The suites
themselves are pluggable (:mod:`app.benchmarks.registry`) and reuse existing
engines — the default runner is swappable via an injectable ``run_fn`` so the
whole thing is offline-testable.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from sqlalchemy import select

from app.benchmarks.registry import get_suite, valid_suites
from app.benchmarks.suites.base import SuiteContext
from app.db.models import BenchmarkResult
from app.logging_config import get_logger

logger = get_logger("benchmark-center")

# run_fn(target_model, suites, config) -> {"scores": {..}, "metrics": {..}, "overall_score": float|None}
RunFn = Callable[[str, list, dict], Awaitable[dict]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(b: BenchmarkResult) -> dict:
    return {
        "id": b.id,
        "project_id": b.project_id,
        "run_id": b.run_id,
        "registry_id": b.registry_id,
        "target_model": b.target_model,
        "provider": b.provider,
        "runtime": b.runtime,
        "label": b.label,
        "suites": b.suites or [],
        "status": b.status,
        "overall_score": b.overall_score,
        "scores": b.scores or {},
        "metrics": b.metrics or {},
        "duration_seconds": b.duration_seconds,
        "config": b.config or {},
        "error": b.error,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
    }


class BenchmarkService:
    def __init__(self, run_fn: Optional[RunFn] = None, session_factory=None,
                 auto_worker: bool = True) -> None:
        self._run_fn = run_fn                      # None → real suite runner
        self._session_factory = session_factory    # None → AsyncSessionLocal
        self._auto_worker = auto_worker            # tests disable → drive via drain()
        self._queue: deque[str] = deque()
        self._cancelled: set[str] = set()
        self._current: Optional[str] = None
        self._worker: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    async def _run(self, target_model: str, suites: list, config: dict) -> dict:
        if self._run_fn is not None:
            return await self._run_fn(target_model, suites, config)
        return await _default_run(target_model, suites, config)

    # -- scheduling --------------------------------------------------------

    async def schedule(
        self, *, target_model: str, suites: Optional[list] = None,
        project_id: Optional[str] = None, run_id: Optional[str] = None,
        registry_id: Optional[str] = None, provider: Optional[str] = None,
        runtime: Optional[str] = None, label: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> dict:
        """Create a pending benchmark job for one model and enqueue it. Non-blocking."""
        suite_keys = valid_suites(suites or [])
        b = BenchmarkResult(
            id=str(uuid4()), project_id=project_id, run_id=run_id, registry_id=registry_id,
            target_model=target_model, provider=provider, runtime=runtime,
            label=label or target_model, suites=suite_keys, status="pending",
            scores={}, metrics={}, config=config or {},
        )
        async with self._factory()() as db:
            db.add(b)
            await db.commit()
        self._queue.append(b.id)
        self._ensure_worker()
        return {"id": b.id, "status": "pending", "target_model": target_model, "suites": suite_keys}

    async def schedule_many(self, models: list[dict], *, suites=None, project_id=None,
                            config=None) -> list[dict]:
        """Schedule several models at once. Each ``models`` item may set
        target_model, registry_id, provider, runtime, run_id, label."""
        out = []
        for m in models:
            out.append(await self.schedule(
                target_model=m["target_model"], suites=suites, project_id=project_id,
                run_id=m.get("run_id"), registry_id=m.get("registry_id"),
                provider=m.get("provider"), runtime=m.get("runtime"),
                label=m.get("label"), config=config,
            ))
        return out

    def _ensure_worker(self) -> None:
        if not self._auto_worker:
            return
        if self._worker is None or self._worker.done():
            try:
                self._worker = asyncio.create_task(self._process_all())
            except RuntimeError:
                self._worker = None

    async def _process_all(self) -> None:
        async with self._lock:
            while self._queue:
                await self._run_job(self._queue.popleft())

    async def drain(self) -> None:
        await self._process_all()

    async def _run_job(self, job_id: str) -> None:
        self._current = job_id
        try:
            async with self._factory()() as db:
                b = await db.get(BenchmarkResult, job_id)
                if b is None:
                    return
                if job_id in self._cancelled or b.status == "cancelled":
                    b.status = "cancelled"
                    await db.commit()
                    return
                b.status = "running"
                await db.commit()
                target, suites, config = b.target_model, list(b.suites or []), dict(b.config or {})

            start = time.monotonic()
            result = await self._run(target, suites, config)
            duration = round(time.monotonic() - start, 3)

            async with self._factory()() as db:
                b = await db.get(BenchmarkResult, job_id)
                if b is None:
                    return
                if job_id in self._cancelled:
                    b.status = "cancelled"
                else:
                    b.status = "completed"
                    b.scores = result.get("scores", {})
                    b.metrics = result.get("metrics", {})
                    b.overall_score = result.get("overall_score")
                    b.duration_seconds = duration
                b.completed_at = _utcnow()
                await db.commit()
        except Exception as exc:  # noqa: BLE001 - a failed benchmark must never crash the app
            logger.warning("benchmark job %s failed: %s", job_id, exc)
            try:
                async with self._factory()() as db:
                    b = await db.get(BenchmarkResult, job_id)
                    if b is not None:
                        b.status = "failed"
                        b.error = str(exc)[:500]
                        b.completed_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._current = None

    async def cancel(self, job_id: str) -> bool:
        self._cancelled.add(job_id)
        was_queued = job_id in self._queue
        if was_queued:
            self._queue.remove(job_id)
            try:
                async with self._factory()() as db:
                    b = await db.get(BenchmarkResult, job_id)
                    if b is not None and b.status in ("pending", "running"):
                        b.status = "cancelled"
                        b.completed_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
        return True

    # -- reads -------------------------------------------------------------

    async def get(self, job_id: str) -> Optional[dict]:
        async with self._factory()() as db:
            b = await db.get(BenchmarkResult, job_id)
        return _to_dict(b) if b else None

    async def history(self, *, project_id=None, run_id=None, model=None,
                      limit: int = 200) -> list[dict]:
        stmt = select(BenchmarkResult).order_by(BenchmarkResult.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(BenchmarkResult.project_id == project_id)
        if run_id is not None:
            stmt = stmt.where(BenchmarkResult.run_id == run_id)
        if model is not None:
            stmt = stmt.where(BenchmarkResult.target_model == model)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
        return [_to_dict(r) for r in rows]

    async def leaderboard(self, *, project_id=None, suite: Optional[str] = None,
                          limit: int = 50) -> list[dict]:
        """Ranked completed results. When ``suite`` is given, rank by that suite's
        score; otherwise by overall score. One entry per model (its best result)."""
        stmt = select(BenchmarkResult).where(BenchmarkResult.status == "completed")
        if project_id is not None:
            stmt = stmt.where(BenchmarkResult.project_id == project_id)
        async with self._factory()() as db:
            rows = (await db.execute(stmt)).scalars().all()

        def score_of(r: BenchmarkResult) -> Optional[float]:
            if suite:
                return (r.scores or {}).get(suite)
            return r.overall_score

        best: dict[str, BenchmarkResult] = {}
        for r in rows:
            s = score_of(r)
            if s is None:
                continue
            cur = best.get(r.target_model)
            if cur is None or (score_of(cur) or -1) < s:
                best[r.target_model] = r
        ranked = sorted(best.values(), key=lambda r: score_of(r) or -1, reverse=True)[:limit]
        return [{**_to_dict(r), "rank_score": score_of(r)} for r in ranked]

    async def trends(self, *, project_id: str, suite: Optional[str] = None) -> dict:
        """Per-model score over time (drives project performance-trend graphs)."""
        rows = await self.history(project_id=project_id, limit=500)
        series: dict[str, list[dict]] = {}
        for r in reversed(rows):   # oldest → newest
            if r["status"] != "completed":
                continue
            score = (r["scores"] or {}).get(suite) if suite else r["overall_score"]
            if score is None:
                continue
            series.setdefault(r["target_model"], []).append(
                {"at": r["created_at"], "score": score, "id": r["id"]}
            )
        return {"suite": suite, "series": series}

    async def compare(self, ids: list[str]) -> dict:
        """Comparison payload for the table + radar chart: each model's per-suite
        scores plus the union of suites."""
        async with self._factory()() as db:
            rows = [await db.get(BenchmarkResult, i) for i in ids]
        rows = [r for r in rows if r is not None]
        suites: list[str] = []
        for r in rows:
            for k in (r.scores or {}):
                if k not in suites:
                    suites.append(k)
        return {
            "suites": suites,
            "models": [{
                "id": r.id, "label": r.label or r.target_model, "target_model": r.target_model,
                "registry_id": r.registry_id, "overall_score": r.overall_score,
                "scores": r.scores or {}, "metrics": r.metrics or {},
            } for r in rows],
        }

    def queue_status(self) -> dict:
        return {"pending": list(self._queue), "running": self._current, "queued": len(self._queue)}


# ---------------------------------------------------------------------------
# Default runner — executes real suites via the Runtime Manager + existing engine.
# ---------------------------------------------------------------------------

async def _runtime_generate(model: str, prompt: str, *, options: Optional[dict] = None) -> str:
    """Adapt the Runtime Manager to the suite ``generate_fn`` contract (→ text)."""
    from app.runtime.manager import get_runtime
    result = await get_runtime().generate(model, prompt, options=options)
    return getattr(result, "response", "") or getattr(result, "text", "") or ""


async def _default_run(target_model: str, suites: list, config: dict) -> dict:
    """Run each requested suite for one model and aggregate. Individual suite
    failures are captured per-suite and never abort the others."""
    try:
        from app.resources import detect_resources
        resources = detect_resources().to_dict()
    except Exception:  # noqa: BLE001
        resources = {}

    ctx = SuiteContext(
        model=target_model, generate_fn=_runtime_generate,
        provider=config.get("provider"), config=config, resources=resources,
    )

    scores: dict = {}
    metrics: dict = {}
    for key in suites:
        suite = get_suite(key)
        if suite is None:
            continue
        try:
            res = await suite.run(ctx)
            scores[key] = res.score
            metrics[key] = {**res.metrics, "simulated": res.simulated, "note": res.note}
        except Exception as exc:  # noqa: BLE001
            logger.warning("suite %s failed for %s: %s", key, target_model, exc)
            metrics[key] = {"error": str(exc)[:300]}
            scores[key] = None

    real = [v for v in scores.values() if v is not None]
    overall = round(sum(real) / len(real), 2) if real else None
    return {"scores": scores, "metrics": metrics, "overall_score": overall}


benchmark_center = BenchmarkService()
