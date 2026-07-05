"""Evaluation-engine API: profiles, execution plans, and runtime estimates.

These endpoints are read-only *previews*: they let a UI show the user exactly
what a chosen profile will do, how long it will take, and whether the machine
can handle it — all before a single LLM call is made. Actually starting an
evaluation is handled by the session/scheduler layer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.evaluation_profiles import profile_registry
from app.evaluation_profiles.profile import EvaluationProfile
from app.resources.resource_monitor import assess_plan, detect_resources
from app.runtime.runtime_estimator import (
    EstimationInputs,
    estimate_runtime,
    gather_latency_stats,
)
from app.scheduler.plan_builder import PlanBuildError, build_execution_plan

router = APIRouter(tags=["evaluation-engine"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    profile: str
    models: list[str] = Field(default_factory=list)


class EnginePreview(BaseModel):
    """Everything a UI needs to preview and de-risk a run."""

    profile: str
    models: list[str]
    estimated_time: dict          # {"seconds": ..., "minutes": ...}
    estimated_ram_mb: int
    estimated_gpu_mb: int
    estimated_llm_calls: int
    execution_steps: list[dict]
    warnings: list[str]
    plan: dict
    estimate: dict
    resources: dict


# ---------------------------------------------------------------------------
# Shared assembly
# ---------------------------------------------------------------------------

async def _build_preview(
    profile: EvaluationProfile, models: list[str], db: AsyncSession
) -> EnginePreview:
    try:
        plan = await build_execution_plan(profile, models, db)
    except PlanBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uses_judge = profile.evaluator == "llm_judge"
    latency_models = list(plan.models)
    if uses_judge and profile.judge_model:
        latency_models.append(profile.judge_model)
    latency_by_model = await gather_latency_stats(db, latency_models)

    estimate = estimate_runtime(
        EstimationInputs(
            models=plan.models,
            base_attacks_per_model=plan.base_attacks_per_model,
            mutation_multiplier=profile.mutation_multiplier,
            passes=profile.passes,
            uses_judge=uses_judge,
            judge_model=profile.judge_model,
            adaptive_agent=profile.adaptive_agent,
            generate_report=profile.generate_report,
        ),
        latency_by_model=latency_by_model,
    )

    snapshot = detect_resources()
    estimate_dict = estimate.to_dict()
    warnings = assess_plan(estimate_dict, snapshot)

    return EnginePreview(
        profile=profile.name,
        models=plan.models,
        estimated_time={
            "seconds": estimate_dict["estimated_seconds"],
            "minutes": estimate_dict["estimated_minutes"],
        },
        estimated_ram_mb=estimate.estimated_ram_mb,
        estimated_gpu_mb=estimate.estimated_gpu_mb,
        estimated_llm_calls=estimate.estimated_llm_calls,
        execution_steps=[s.model_dump() for s in plan.steps],
        warnings=warnings,
        plan=plan.model_dump(),
        estimate=estimate_dict,
        resources=snapshot.to_dict(),
    )


def _require_profile(name: str) -> EvaluationProfile:
    profile = profile_registry.get_profile(name)
    if profile is None:
        available = [p.name for p in profile_registry.list_profiles()]
        raise HTTPException(
            status_code=404,
            detail=f"Unknown profile '{name}'. Available: {available}",
        )
    return profile


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/evaluation-profiles", response_model=list[EvaluationProfile])
async def list_evaluation_profiles() -> list[EvaluationProfile]:
    return profile_registry.list_profiles()


@router.get("/api/evaluation-profiles/{name}", response_model=EvaluationProfile)
async def get_evaluation_profile(name: str) -> EvaluationProfile:
    return _require_profile(name)


@router.post("/api/evaluation-plan", response_model=EnginePreview)
async def create_evaluation_plan(
    req: PlanRequest,
    db: AsyncSession = Depends(get_db),
) -> EnginePreview:
    profile = _require_profile(req.profile)
    return await _build_preview(profile, req.models, db)


@router.get("/api/runtime-estimate", response_model=EnginePreview)
async def get_runtime_estimate(
    profile: str,
    models: list[str] = Query(default_factory=list),
    db: AsyncSession = Depends(get_db),
) -> EnginePreview:
    prof = _require_profile(profile)
    return await _build_preview(prof, models, db)
