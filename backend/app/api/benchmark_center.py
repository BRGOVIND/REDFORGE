"""Benchmark Center API (RedForge V2 Phase 3).

Schedule / read objective benchmarks across base models, checkpoints (Runtime
Registry), and whole projects. Additive; delegates to :mod:`app.benchmarks`.
Distinct from the legacy ``/api/benchmarks`` (attack-suite) router — this one is
mounted at ``/api/benchmark-center``.

Route order matters: every literal path (``/suites``, ``/leaderboard`` …) is
declared before the parameterized ``/{result_id}`` so it is never shadowed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.benchmarks import benchmark_center, list_suites
from app.config import settings
from app.db.database import get_db
from app.runtime_registry import runtime_registry

router = APIRouter(prefix="/api/benchmark-center", tags=["benchmark-center"])


class BenchmarkRequest(BaseModel):
    models: list[str] = Field(default_factory=list)         # raw model names
    registry_ids: list[str] = Field(default_factory=list)   # registered checkpoints/final models
    project_id: Optional[str] = None                        # benchmark a whole project
    suites: Optional[list[str]] = None                       # None/empty → defaults
    config: dict = Field(default_factory=dict)


async def _resolve_targets(db: AsyncSession, req: BenchmarkRequest) -> list[dict]:
    """Expand the request into concrete benchmark targets (one per model)."""
    provider = settings.RUNTIME_PROVIDER.lower()
    targets: list[dict] = []
    seen: set[str] = set()

    def add(target_model: str, **extra):
        key = f"{extra.get('registry_id') or ''}|{target_model}"
        if key in seen or not target_model:
            return
        seen.add(key)
        targets.append({"target_model": target_model, **extra})

    for name in req.models:
        add(name, provider=provider, runtime=provider, label=name)

    for rid in req.registry_ids:
        m = await runtime_registry.get(db, rid)
        if m is not None:
            add(m["runtime_model"], registry_id=m["id"], run_id=m.get("run_id"),
                provider=m.get("provider") or provider, runtime=m.get("provider") or provider,
                label=m.get("label"))

    # Whole-project: every registered checkpoint + the project's declared models.
    if req.project_id and not req.models and not req.registry_ids:
        for m in await runtime_registry.list(db, project_id=req.project_id):
            add(m["runtime_model"], registry_id=m["id"], run_id=m.get("run_id"),
                provider=m.get("provider") or provider, runtime=m.get("provider") or provider,
                label=m.get("label"))
        from app.db.models import Project
        proj = await db.get(Project, req.project_id)
        if proj is not None:
            for name in (proj.models or []):
                add(name, provider=provider, runtime=provider, label=name)

    return targets


# -- literal routes (declared before /{result_id}) -------------------------

@router.get("/suites")
async def suites() -> list[dict]:
    return list_suites()


@router.get("/queue")
async def queue() -> dict:
    return benchmark_center.queue_status()


@router.get("/leaderboard")
async def leaderboard(
    project_id: Optional[str] = Query(None),
    suite: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    return await benchmark_center.leaderboard(project_id=project_id, suite=suite, limit=limit)


@router.get("/trends")
async def trends(
    project_id: str = Query(...),
    suite: Optional[str] = Query(None),
) -> dict:
    return await benchmark_center.trends(project_id=project_id, suite=suite)


@router.get("/compare")
async def compare(ids: str = Query(..., description="comma-separated result ids")) -> dict:
    id_list = [i for i in ids.split(",") if i]
    if not id_list:
        raise HTTPException(status_code=400, detail="no ids provided")
    return await benchmark_center.compare(id_list)


# -- collection ------------------------------------------------------------

@router.get("")
async def history(
    project_id: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> list[dict]:
    return await benchmark_center.history(
        project_id=project_id, run_id=run_id, model=model, limit=limit)


@router.post("", status_code=201)
async def schedule(req: BenchmarkRequest, db: AsyncSession = Depends(get_db)) -> dict:
    targets = await _resolve_targets(db, req)
    if not targets:
        raise HTTPException(status_code=400, detail="no benchmark targets resolved")
    scheduled = await benchmark_center.schedule_many(
        targets, suites=req.suites, project_id=req.project_id, config=req.config)
    return {"scheduled": scheduled, "count": len(scheduled)}


# -- item ------------------------------------------------------------------

@router.get("/{result_id}")
async def get_result(result_id: str) -> dict:
    r = await benchmark_center.get(result_id)
    if r is None:
        raise HTTPException(status_code=404, detail="benchmark result not found")
    return r


@router.delete("/{result_id}")
async def cancel_result(result_id: str) -> dict:
    await benchmark_center.cancel(result_id)
    return {"cancelled": True, "id": result_id}
