"""Evaluation Workbench services.

Two cooperating services, both local-only and additive:

* :class:`EvaluationWorkbenchService` — CRUD for Collections → Prompt Sets →
  Prompts (with version history). Summaries are composed at read time.
* :class:`EvaluationSessionService` — executes a session's prompt sets against
  the selected models through the SAME async single-worker queue architecture as
  Benchmark Center (deque + lock + auto_worker + drain + cancel), so the UI never
  blocks. Execution reuses the Runtime Manager (never a second execution path),
  the pluggable similarity providers, and the regression analyzer.

Both accept injectable seams (``session_factory``, ``generate_fn``, ``run_fn``)
so the whole subsystem is offline-testable without a real provider.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (
    EvaluationCollection, EvaluationResult, Prompt, PromptSet, WorkbenchSession,
)
from app.evaluation.regression import regression_analyzer
from app.evaluation.similarity import get_similarity
from app.evaluation.versioning import prompt_version_service, snapshot_of
from app.logging_config import get_logger

logger = get_logger("evaluation-workbench")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def collection_dict(c: EvaluationCollection, *, set_count: Optional[int] = None) -> dict:
    d = {
        "id": c.id, "project_id": c.project_id, "name": c.name, "category": c.category,
        "description": c.description or "", "tags": c.tags or [], "notes": c.notes or "",
        "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at),
    }
    if set_count is not None:
        d["prompt_set_count"] = set_count
    return d


def prompt_set_dict(s: PromptSet, *, prompt_count: Optional[int] = None) -> dict:
    d = {
        "id": s.id, "collection_id": s.collection_id, "project_id": s.project_id,
        "title": s.title, "description": s.description or "", "category": s.category,
        "tags": s.tags or [], "notes": s.notes or "", "priority": s.priority,
        "owner": s.owner or "", "created_at": _iso(s.created_at), "updated_at": _iso(s.updated_at),
    }
    if prompt_count is not None:
        d["prompt_count"] = prompt_count
    return d


def prompt_dict(p: Prompt) -> dict:
    return {
        "id": p.id, "prompt_set_id": p.prompt_set_id, "title": p.title or "",
        "prompt": p.prompt, "system_prompt": p.system_prompt or "", "context": p.context or "",
        "expected_behavior": p.expected_behavior or "", "expected_output": p.expected_output or "",
        "golden_response": p.golden_response or "", "acceptance_criteria": p.acceptance_criteria or {},
        "tags": p.tags or [], "priority": p.priority, "difficulty": p.difficulty,
        "notes": p.notes or "", "enabled": bool(p.enabled), "current_version": p.current_version,
        "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at),
    }


def result_dict(r: EvaluationResult) -> dict:
    return {
        "id": r.id, "session_id": r.session_id, "prompt_id": r.prompt_id,
        "prompt_set_id": r.prompt_set_id, "prompt_version": r.prompt_version,
        "prompt_title": r.prompt_title or "", "target_model": r.target_model,
        "registry_id": r.registry_id, "provider": r.provider, "runtime": r.runtime,
        "label": r.label or r.target_model, "response": r.response or "",
        "metrics": r.metrics or {}, "similarity_score": r.similarity_score,
        "baseline_type": r.baseline_type, "verdict": r.verdict,
        "regressions": r.regressions or [], "warnings": r.warnings or [],
        "error": r.error, "created_at": _iso(r.created_at),
    }


def session_dict(s: WorkbenchSession) -> dict:
    return {
        "id": s.id, "project_id": s.project_id, "run_id": s.run_id, "name": s.name or "",
        "models": s.models or [], "prompt_set_ids": s.prompt_set_ids or [],
        "similarity": s.similarity, "status": s.status, "config": s.config or {},
        "summary": s.summary or {}, "total_tasks": s.total_tasks,
        "completed_tasks": s.completed_tasks, "duration_seconds": s.duration_seconds,
        "error": s.error, "created_at": _iso(s.created_at), "completed_at": _iso(s.completed_at),
    }


# ---------------------------------------------------------------------------
# CRUD service
# ---------------------------------------------------------------------------

class EvaluationWorkbenchService:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    # -- collections -------------------------------------------------------

    async def create_collection(self, *, project_id=None, name: str, category="custom",
                                description="", tags=None, notes="") -> dict:
        c = EvaluationCollection(id=str(uuid4()), project_id=project_id, name=name,
                                 category=category, description=description,
                                 tags=tags or [], notes=notes)
        async with self._factory()() as db:
            db.add(c)
            await db.commit()
            await db.refresh(c)
            return collection_dict(c, set_count=0)

    async def list_collections(self, *, project_id=None) -> list[dict]:
        stmt = select(EvaluationCollection).order_by(EvaluationCollection.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(EvaluationCollection.project_id == project_id)
        async with self._factory()() as db:
            rows = (await db.execute(stmt)).scalars().all()
            out = []
            for c in rows:
                n = (await db.execute(
                    select(PromptSet.id).where(PromptSet.collection_id == c.id))).scalars().all()
                out.append(collection_dict(c, set_count=len(n)))
            return out

    async def get_collection(self, cid: str) -> Optional[dict]:
        async with self._factory()() as db:
            c = await db.get(EvaluationCollection, cid)
            if c is None:
                return None
            sets = (await db.execute(
                select(PromptSet).where(PromptSet.collection_id == cid)
                .order_by(PromptSet.created_at))).scalars().all()
            d = collection_dict(c, set_count=len(sets))
            d["prompt_sets"] = [prompt_set_dict(s) for s in sets]
            return d

    async def update_collection(self, cid: str, **fields) -> Optional[dict]:
        async with self._factory()() as db:
            c = await db.get(EvaluationCollection, cid)
            if c is None:
                return None
            for k in ("name", "category", "description", "tags", "notes"):
                if k in fields and fields[k] is not None:
                    setattr(c, k, fields[k])
            await db.commit()
            await db.refresh(c)
            return collection_dict(c)

    async def delete_collection(self, cid: str) -> bool:
        async with self._factory()() as db:
            c = await db.get(EvaluationCollection, cid)
            if c is None:
                return False
            await db.delete(c)
            await db.commit()
            return True

    # -- prompt sets -------------------------------------------------------

    async def create_prompt_set(self, *, collection_id: str, title: str, description="",
                                category="custom", tags=None, notes="", priority="normal",
                                owner="", project_id=None) -> Optional[dict]:
        async with self._factory()() as db:
            col = await db.get(EvaluationCollection, collection_id)
            if col is None:
                return None
            s = PromptSet(id=str(uuid4()), collection_id=collection_id,
                          project_id=project_id or col.project_id, title=title,
                          description=description, category=category or col.category,
                          tags=tags or [], notes=notes, priority=priority, owner=owner)
            db.add(s)
            await db.commit()
            await db.refresh(s)
            return prompt_set_dict(s, prompt_count=0)

    async def list_prompt_sets(self, *, collection_id=None, project_id=None) -> list[dict]:
        stmt = select(PromptSet).order_by(PromptSet.created_at.desc())
        if collection_id is not None:
            stmt = stmt.where(PromptSet.collection_id == collection_id)
        if project_id is not None:
            stmt = stmt.where(PromptSet.project_id == project_id)
        async with self._factory()() as db:
            rows = (await db.execute(stmt)).scalars().all()
            out = []
            for s in rows:
                n = (await db.execute(
                    select(Prompt.id).where(Prompt.prompt_set_id == s.id))).scalars().all()
                out.append(prompt_set_dict(s, prompt_count=len(n)))
            return out

    async def get_prompt_set(self, sid: str) -> Optional[dict]:
        async with self._factory()() as db:
            s = await db.get(PromptSet, sid)
            if s is None:
                return None
            prompts = (await db.execute(
                select(Prompt).where(Prompt.prompt_set_id == sid)
                .order_by(Prompt.created_at))).scalars().all()
            d = prompt_set_dict(s, prompt_count=len(prompts))
            d["prompts"] = [prompt_dict(p) for p in prompts]
            return d

    async def update_prompt_set(self, sid: str, **fields) -> Optional[dict]:
        async with self._factory()() as db:
            s = await db.get(PromptSet, sid)
            if s is None:
                return None
            for k in ("title", "description", "category", "tags", "notes", "priority", "owner"):
                if k in fields and fields[k] is not None:
                    setattr(s, k, fields[k])
            await db.commit()
            await db.refresh(s)
            return prompt_set_dict(s)

    async def delete_prompt_set(self, sid: str) -> bool:
        async with self._factory()() as db:
            s = await db.get(PromptSet, sid)
            if s is None:
                return False
            await db.delete(s)
            await db.commit()
            return True

    # -- prompts -----------------------------------------------------------

    async def create_prompt(self, *, prompt_set_id: str, prompt: str, title="",
                            system_prompt="", context="", expected_behavior="",
                            expected_output="", golden_response="", acceptance_criteria=None,
                            tags=None, priority="normal", difficulty="normal", notes="") -> Optional[dict]:
        async with self._factory()() as db:
            ps = await db.get(PromptSet, prompt_set_id)
            if ps is None:
                return None
            p = Prompt(
                id=str(uuid4()), prompt_set_id=prompt_set_id, title=title, prompt=prompt,
                system_prompt=system_prompt, context=context, expected_behavior=expected_behavior,
                expected_output=expected_output, golden_response=golden_response,
                acceptance_criteria=acceptance_criteria or {}, tags=tags or [],
                priority=priority, difficulty=difficulty, notes=notes,
                enabled=1, current_version=1,
            )
            db.add(p)
            await prompt_version_service.snapshot(db, p, note="created")
            await db.commit()
            await db.refresh(p)
            return prompt_dict(p)

    async def get_prompt(self, pid: str) -> Optional[dict]:
        async with self._factory()() as db:
            p = await db.get(Prompt, pid)
            return prompt_dict(p) if p else None

    async def update_prompt(self, pid: str, *, version_note: str = "", **fields) -> Optional[dict]:
        """Update prompt fields. If any *content* field changed, bump the version and
        snapshot — so regression reports can attribute a difference to the prompt."""
        content_fields = ("prompt", "system_prompt", "context", "expected_behavior",
                          "expected_output", "golden_response", "acceptance_criteria")
        async with self._factory()() as db:
            p = await db.get(Prompt, pid)
            if p is None:
                return None
            before = snapshot_of(p)
            for k in ("title", "prompt", "system_prompt", "context", "expected_behavior",
                      "expected_output", "golden_response", "acceptance_criteria", "tags",
                      "priority", "difficulty", "notes"):
                if k in fields and fields[k] is not None:
                    setattr(p, k, fields[k])
            if "enabled" in fields and fields["enabled"] is not None:
                p.enabled = 1 if fields["enabled"] else 0
            content_changed = any(before.get(k) != getattr(p, k) for k in content_fields)
            if content_changed:
                p.current_version += 1
                await prompt_version_service.snapshot(db, p, note=version_note or "edited")
            await db.commit()
            await db.refresh(p)
            return prompt_dict(p)

    async def delete_prompt(self, pid: str) -> bool:
        async with self._factory()() as db:
            p = await db.get(Prompt, pid)
            if p is None:
                return False
            await db.delete(p)
            await db.commit()
            return True

    async def prompt_versions(self, pid: str) -> list[dict]:
        async with self._factory()() as db:
            return await prompt_version_service.list(db, pid)

    async def compare_prompt_versions(self, pid: str, a: int, b: int) -> Optional[dict]:
        async with self._factory()() as db:
            return await prompt_version_service.compare(db, pid, a, b)


evaluation_workbench = EvaluationWorkbenchService()


# ---------------------------------------------------------------------------
# Execution service (async queue — mirrors Benchmark Center)
# ---------------------------------------------------------------------------

# generate_fn(model, prompt, system, options) -> dict(response, latency_ms, ttft_ms,
#   prompt_tokens, completion_tokens, total_tokens)
GenerateFn = Callable[..., Awaitable[dict]]


async def _runtime_generate_rich(model: str, prompt: str, *, system: Optional[str] = None,
                                 options: Optional[dict] = None) -> dict:
    """Reuse the Runtime Manager (the single execution path) and surface metrics."""
    from app.runtime.manager import get_runtime

    opts = dict(options or {})
    if system:
        opts.setdefault("system", system)
    started = time.monotonic()
    res = await get_runtime().generate(model, prompt, options=opts)
    latency = getattr(res, "latency_ms", None)
    if latency is None:
        latency = round((time.monotonic() - started) * 1000, 2)
    completion_tokens = getattr(res, "eval_count", None)
    prompt_tokens = getattr(res, "prompt_eval_count", None)
    total = None
    if prompt_tokens is not None or completion_tokens is not None:
        total = (prompt_tokens or 0) + (completion_tokens or 0)
    return {
        "response": getattr(res, "response", "") or getattr(res, "text", "") or "",
        "latency_ms": latency,
        "ttft_ms": getattr(res, "first_token_latency_ms", None),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
    }


def _min_similarity(acceptance: dict, config: dict) -> float:
    for src in (acceptance, config):
        v = (src or {}).get("min_similarity")
        if isinstance(v, (int, float)):
            return float(v)
    return 60.0


def _verdict(*, baseline_type: Optional[str], similarity: Optional[float],
             regressions: list[dict], acceptance: dict, config: dict,
             error: bool) -> str:
    if error:
        return "error"
    sev = {r.get("severity") for r in regressions}
    has_blocking = bool({"critical", "high"} & sev)
    if baseline_type in ("golden", "expected") and similarity is not None:
        if has_blocking or similarity < _min_similarity(acceptance, config):
            return "fail"
        if sev:  # only medium/low regressions
            return "warn"
        return "pass"
    # No baseline text — judge purely on acceptance criteria / regressions.
    if has_blocking:
        return "fail"
    if acceptance.get("must_include") or acceptance.get("must_exclude"):
        return "warn" if sev else "pass"
    return "warn" if sev else "none"


def compose_summary(results: list[dict], models: list[dict]) -> dict:
    """Compose a session's scores from its results (read-time, stores nothing)."""
    graded = [r for r in results if r["verdict"] in ("pass", "fail", "warn")]
    total = len(graded)
    passes = sum(1 for r in graded if r["verdict"] == "pass")
    fails = sum(1 for r in graded if r["verdict"] == "fail")
    warns = sum(1 for r in graded if r["verdict"] == "warn")
    regressed = sum(1 for r in results if r.get("regressions"))
    sims = [r["similarity_score"] for r in results if r.get("similarity_score") is not None]

    pass_rate = round(100 * passes / total, 1) if total else None
    fail_rate = round(100 * fails / total, 1) if total else None
    warn_rate = round(100 * warns / total, 1) if total else None
    regression_score = round(100 * (1 - regressed / len(results)), 1) if results else None
    quality_score = round(sum(sims) / len(sims), 1) if sims else None

    # Consistency: per-prompt agreement of verdicts across models (only meaningful
    # with >1 model). 100 = every model agreed on every prompt.
    by_prompt: dict[str, list[str]] = {}
    for r in graded:
        by_prompt.setdefault(r.get("prompt_id") or r["id"], []).append(r["verdict"])
    agreements = []
    for verdicts in by_prompt.values():
        if len(verdicts) > 1:
            top = max(set(verdicts), key=verdicts.count)
            agreements.append(verdicts.count(top) / len(verdicts))
    consistency_score = round(100 * sum(agreements) / len(agreements), 1) if agreements else None

    # Per-model breakdown → best performing model + closest-to-baseline.
    per_model = []
    for m in models:
        key = m.get("registry_id") or m.get("target_model")
        rs = [r for r in results
              if (r.get("registry_id") or r["target_model"]) == key]
        g = [r for r in rs if r["verdict"] in ("pass", "fail", "warn")]
        msims = [r["similarity_score"] for r in rs if r.get("similarity_score") is not None]
        per_model.append({
            "label": m.get("label") or m.get("target_model"),
            "target_model": m.get("target_model"), "registry_id": m.get("registry_id"),
            "pass_rate": round(100 * sum(1 for r in g if r["verdict"] == "pass") / len(g), 1) if g else None,
            "fails": sum(1 for r in rs if r["verdict"] == "fail"),
            "regressions": sum(1 for r in rs if r.get("regressions")),
            "mean_similarity": round(sum(msims) / len(msims), 1) if msims else None,
            "results": len(rs),
        })

    def rank(m):
        return (m["pass_rate"] if m["pass_rate"] is not None else -1,
                m["mean_similarity"] if m["mean_similarity"] is not None else -1)
    ranked = [m for m in per_model if m["results"]]
    best_model = max(ranked, key=rank) if ranked else None
    closest = max((m for m in ranked if m["mean_similarity"] is not None),
                  key=lambda m: m["mean_similarity"], default=None)

    breakdown: dict[str, int] = {}
    for r in results:
        for reg in r.get("regressions") or []:
            breakdown[reg["type"]] = breakdown.get(reg["type"], 0) + 1

    parts = [x for x in (pass_rate, quality_score, regression_score, consistency_score)
             if x is not None]
    overall = round(sum(parts) / len(parts), 1) if parts else None

    return {
        "pass_rate": pass_rate, "fail_rate": fail_rate, "warn_rate": warn_rate,
        "regression_score": regression_score, "consistency_score": consistency_score,
        "quality_score": quality_score, "overall_score": overall,
        "total_results": len(results), "graded_results": total,
        "regression_breakdown": breakdown, "models": per_model,
        "best_model": best_model, "closest_to_baseline": closest,
    }


class EvaluationSessionService:
    def __init__(self, run_fn=None, generate_fn: Optional[GenerateFn] = None,
                 session_factory=None, auto_worker: bool = True) -> None:
        self._run_fn = run_fn
        self._generate_fn = generate_fn or _runtime_generate_rich
        self._session_factory = session_factory
        self._auto_worker = auto_worker
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

    # -- scheduling --------------------------------------------------------

    async def schedule(self, *, models: list[dict], prompt_set_ids: list[str],
                       project_id=None, run_id=None, name="", similarity="text",
                       config=None) -> dict:
        """Create a pending session and enqueue it. Non-blocking."""
        async with self._factory()() as db:
            prompts = (await db.execute(
                select(Prompt).where(
                    Prompt.prompt_set_id.in_(prompt_set_ids), Prompt.enabled == 1)
            )).scalars().all() if prompt_set_ids else []
            total = len(models) * len(prompts)
            s = WorkbenchSession(
                id=str(uuid4()), project_id=project_id, run_id=run_id, name=name,
                models=models, prompt_set_ids=prompt_set_ids, similarity=similarity,
                status="pending", config=config or {}, summary={}, total_tasks=total,
                completed_tasks=0,
            )
            db.add(s)
            await db.commit()
            sid = s.id
        self._queue.append(sid)
        self._ensure_worker()
        return {"id": sid, "status": "pending", "total_tasks": total,
                "models": len(models), "prompt_sets": len(prompt_set_ids)}

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

    async def _load_prompts(self, db, prompt_set_ids: list[str]) -> list[Prompt]:
        if not prompt_set_ids:
            return []
        return list((await db.execute(
            select(Prompt).where(
                Prompt.prompt_set_id.in_(prompt_set_ids), Prompt.enabled == 1)
            .order_by(Prompt.created_at))).scalars().all())

    async def _prev_result(self, db, session_id: str, prompt_id: str, model_key: str,
                           target_model: str) -> Optional[EvaluationResult]:
        """Most recent result for this prompt+model from an EARLIER session — used
        to detect model drift (safety/performance regression) across runs."""
        rows = (await db.execute(
            select(EvaluationResult).where(
                EvaluationResult.prompt_id == prompt_id,
                EvaluationResult.target_model == target_model,
                EvaluationResult.session_id != session_id,
            ).order_by(EvaluationResult.created_at.desc()).limit(1)
        )).scalars().all()
        return rows[0] if rows else None

    async def _run_job(self, session_id: str) -> None:
        self._current = session_id
        start = time.monotonic()
        try:
            async with self._factory()() as db:
                s = await db.get(WorkbenchSession, session_id)
                if s is None:
                    return
                if session_id in self._cancelled or s.status == "cancelled":
                    s.status = "cancelled"
                    await db.commit()
                    return
                s.status = "running"
                await db.commit()
                models = list(s.models or [])
                config = dict(s.config or {})
                sim_key = s.similarity
                prompt_set_ids = list(s.prompt_set_ids or [])
                prompts = await self._load_prompts(db, prompt_set_ids)

            if self._run_fn is not None:
                # Full override (tests): produce raw result dicts.
                raw_results = await self._run_fn(models, prompts, config)
            else:
                raw_results = await self._execute(session_id, models, prompts, sim_key, config)

            async with self._factory()() as db:
                s = await db.get(WorkbenchSession, session_id)
                if s is None:
                    return
                for rr in raw_results:
                    db.add(EvaluationResult(id=str(uuid4()), session_id=session_id, **rr))
                s.summary = compose_summary([_result_view(r) for r in raw_results], models)
                s.completed_tasks = len(raw_results)
                s.total_tasks = max(s.total_tasks, len(raw_results))
                s.status = "cancelled" if session_id in self._cancelled else "completed"
                s.duration_seconds = round(time.monotonic() - start, 3)
                s.completed_at = _utcnow()
                await db.commit()
        except Exception as exc:  # noqa: BLE001 - a failed session must never crash the app
            import traceback
            tb = traceback.format_exc()
            logger.warning("evaluation session %s failed: %s\n%s", session_id, exc, tb)
            try:
                async with self._factory()() as db:
                    s = await db.get(WorkbenchSession, session_id)
                    if s is not None:
                        s.status = "failed"
                        s.error = (f"{type(exc).__name__}: {exc}" or "evaluation failed")[:500]
                        s.summary = {**(s.summary or {}), "traceback": tb[-1500:]}
                        s.completed_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._current = None

    async def _execute(self, session_id: str, models: list[dict], prompts: list[Prompt],
                       sim_key: str, config: dict) -> list[dict]:
        """Run every (model × prompt), scoring similarity/verdict/regressions."""
        provider = get_similarity(sim_key)
        options = config.get("options") or {}
        out: list[dict] = []
        for m in models:
            target = m.get("target_model")
            if not target:
                continue
            for p in prompts:
                baseline = p.golden_response or p.expected_output or ""
                baseline_type = ("golden" if p.golden_response
                                 else "expected" if p.expected_output else None)
                acceptance = p.acceptance_criteria or {}
                rr = {
                    "prompt_id": p.id, "prompt_set_id": p.prompt_set_id,
                    "prompt_version": p.current_version, "prompt_title": p.title or "",
                    "target_model": target, "registry_id": m.get("registry_id"),
                    "provider": m.get("provider"), "runtime": m.get("runtime"),
                    "label": m.get("label") or target,
                    "response": "", "metrics": {}, "similarity_score": None,
                    "baseline_type": baseline_type or "none", "verdict": "none",
                    "regressions": [], "warnings": [], "error": None,
                }
                try:
                    gen = await self._generate_fn(
                        target, p.prompt, system=p.system_prompt or None, options=options)
                    if isinstance(gen, str):
                        gen = {"response": gen}
                    response = gen.get("response", "") or ""
                    rr["response"] = response
                    rr["metrics"] = {
                        "latency_ms": gen.get("latency_ms"),
                        "ttft_ms": gen.get("ttft_ms"),
                        "completion_ms": gen.get("completion_ms") or gen.get("latency_ms"),
                        "prompt_tokens": gen.get("prompt_tokens"),
                        "completion_tokens": gen.get("completion_tokens"),
                        "total_tokens": gen.get("total_tokens"),
                    }
                    similarity = None
                    if baseline:
                        similarity = provider.score(response, baseline).score
                        rr["similarity_score"] = similarity

                    # Previous run of this prompt+model (drift detection).
                    async with self._factory()() as db:
                        prev = await self._prev_result(
                            db, session_id, p.id, m.get("registry_id") or target, target)
                    prev_resp = prev.response if prev else None
                    prev_lat = (prev.metrics or {}).get("latency_ms") if prev else None
                    prompt_changed = bool(prev and (prev.prompt_version != p.current_version))

                    regressions = regression_analyzer.analyze(
                        response, baseline, acceptance=acceptance,
                        expected_behavior=p.expected_behavior or "", similarity=similarity,
                        prev_response=prev_resp, prompt_changed=prompt_changed,
                        prev_latency_ms=prev_lat, curr_latency_ms=rr["metrics"].get("latency_ms"),
                        category=p.acceptance_criteria.get("category", "") if isinstance(p.acceptance_criteria, dict) else "",
                    )
                    rr["regressions"] = regressions
                    rr["verdict"] = _verdict(
                        baseline_type=baseline_type, similarity=similarity,
                        regressions=regressions, acceptance=acceptance, config=config, error=False)
                    if not baseline and not acceptance:
                        rr["warnings"].append("No baseline or acceptance criteria — informational only.")
                except Exception as exc:  # noqa: BLE001 - one prompt failing never aborts the run
                    rr["error"] = str(exc)[:500]
                    rr["verdict"] = "error"
                out.append(rr)
        return out

    async def cancel(self, session_id: str) -> bool:
        self._cancelled.add(session_id)
        if session_id in self._queue:
            self._queue.remove(session_id)
            try:
                async with self._factory()() as db:
                    s = await db.get(WorkbenchSession, session_id)
                    if s is not None and s.status in ("pending", "running"):
                        s.status = "cancelled"
                        s.completed_at = _utcnow()
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
        return True

    # -- reads -------------------------------------------------------------

    async def get(self, session_id: str) -> Optional[dict]:
        async with self._factory()() as db:
            s = await db.get(WorkbenchSession, session_id)
            return session_dict(s) if s else None

    async def history(self, *, project_id=None, run_id=None, limit: int = 100) -> list[dict]:
        stmt = select(WorkbenchSession).order_by(WorkbenchSession.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(WorkbenchSession.project_id == project_id)
        if run_id is not None:
            stmt = stmt.where(WorkbenchSession.run_id == run_id)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [session_dict(s) for s in rows]

    async def results(self, session_id: str, *, verdict=None, regression_type=None) -> list[dict]:
        async with self._factory()() as db:
            rows = (await db.execute(
                select(EvaluationResult).where(EvaluationResult.session_id == session_id)
                .order_by(EvaluationResult.created_at))).scalars().all()
        out = [result_dict(r) for r in rows]
        if verdict:
            out = [r for r in out if r["verdict"] == verdict]
        if regression_type:
            out = [r for r in out if any(x["type"] == regression_type for x in r["regressions"])]
        return out

    async def regressions(self, session_id: str) -> dict:
        """Regression summary for a session, grouped by type with examples."""
        rows = await self.results(session_id)
        by_type: dict[str, list[dict]] = {}
        for r in rows:
            for reg in r["regressions"]:
                by_type.setdefault(reg["type"], []).append({
                    "label": reg["label"], "severity": reg["severity"],
                    "summary": reg["summary"], "attribution": reg["attribution"],
                    "prompt_title": r["prompt_title"], "target_model": r["label"],
                    "result_id": r["id"],
                })
        total = sum(len(v) for v in by_type.values())
        return {
            "session_id": session_id, "total": total,
            "by_type": [{"type": t, "label": v[0]["label"], "count": len(v), "items": v[:20]}
                        for t, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))],
        }

    async def compare_results(self, ids: list[str]) -> dict:
        """Side-by-side comparison payload for the diff viewer."""
        async with self._factory()() as db:
            rows = [await db.get(EvaluationResult, i) for i in ids]
        rows = [r for r in rows if r is not None]
        return {"results": [result_dict(r) for r in rows]}

    def queue_status(self) -> dict:
        return {"pending": list(self._queue), "running": self._current, "queued": len(self._queue)}


def _result_view(rr: dict) -> dict:
    """Adapt a raw result dict (pre-persist) to the shape compose_summary expects."""
    return {"id": rr.get("prompt_id") or "_", "prompt_id": rr.get("prompt_id"),
            "verdict": rr["verdict"], "similarity_score": rr.get("similarity_score"),
            "regressions": rr.get("regressions") or [],
            "registry_id": rr.get("registry_id"), "target_model": rr.get("target_model")}


evaluation_sessions = EvaluationSessionService()
