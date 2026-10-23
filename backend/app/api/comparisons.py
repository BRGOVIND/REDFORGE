"""Immutable, project-scoped comparison plans backed by Evaluation Workbench."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.db.database import get_db
from app.db.models import ComparisonPlan, Project, ProjectBudget, Prompt, PromptSet, PromptVersion
from app.evaluation import evaluation_sessions
from app.optimization import BOUNDED_OPTIONS, estimated_call_cost, is_remote
from app.observability_privacy import audit
from app.runtime.manager import available_providers

router = APIRouter(prefix="/api/projects/{project_id}/comparisons", tags=["comparisons"])


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    prompt_set_id: str
    candidates: list[Candidate] = Field(min_length=2, max_length=4)
    temperature: float = Field(default=0, ge=0, le=2)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    max_output_tokens: int = Field(default=512, ge=1, le=2048)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    concurrency_limit: int = Field(default=2, ge=1, le=4)
    similarity: Literal["exact", "text"] = "text"
    approve_remote: bool = False
    max_estimated_cost_usd: float | None = Field(default=None, gt=0, le=1000)

    @model_validator(mode="after")
    def distinct(self):
        pairs = {(c.provider, c.model) for c in self.candidates}
        if len(pairs) != len(self.candidates):
            raise ValueError("Candidate provider/model pairs must be distinct")
        return self


class StartIn(BaseModel):
    confirm_remote: bool = False


async def _project(db: AsyncSession, project_id: str, request: Request):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


async def _plan(db, project_id, plan_id):
    row = (await db.execute(select(ComparisonPlan).where(ComparisonPlan.id == plan_id,
        ComparisonPlan.project_id == project_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Project comparison plan not found")
    return row


def _view(row, session=None):
    return {"id": row.id, "project_id": row.project_id, "snapshot": row.snapshot,
        "session_id": row.session_id, "status": session["status"] if session else ("created" if not row.session_id else "unknown"),
        "progress": {"completed": session["completed_tasks"], "total": session["total_tasks"]} if session else None,
        "created_at": row.created_at}


@router.post("", status_code=201)
async def create_plan(project_id: str, body: PlanIn, request: Request,
                      db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    candidates = [c.model_dump() for c in body.candidates]
    if any(c["provider"] not in available_providers() for c in candidates):
        raise HTTPException(422, "Unknown provider")
    if any(c["provider"] not in BOUNDED_OPTIONS for c in candidates):
        raise HTTPException(422, "Provider does not support bounded max-output sampling")
    remote = [c for c in candidates if is_remote(c["provider"])]
    if remote and (not body.approve_remote or body.max_estimated_cost_usd is None):
        raise HTTPException(422, "Remote comparisons require explicit approval and an estimated cost limit")
    dataset = (await db.execute(select(PromptSet).where(PromptSet.id == body.prompt_set_id,
        PromptSet.project_id == project_id))).scalar_one_or_none()
    if dataset is None:
        raise HTTPException(404, "Project prompt set not found")
    prompts = (await db.execute(select(Prompt).where(Prompt.prompt_set_id == dataset.id,
        Prompt.enabled == 1).order_by(Prompt.id).limit(17))).scalars().all()
    if not prompts or len(prompts) > 16 or len(prompts) * len(candidates) > 48:
        raise HTTPException(422, "Comparison requires 1 to 16 enabled prompts and at most 48 calls")
    frozen = {}
    max_input_bytes = 0
    for prompt in prompts:
        version = prompt.active_version or prompt.current_version
        published = (await db.execute(select(PromptVersion).where(PromptVersion.prompt_id == prompt.id,
            PromptVersion.version == version))).scalar_one_or_none()
        if published is None:
            raise HTTPException(422, f"Prompt {prompt.id} has no published version")
        content = published.snapshot or {}
        max_input_bytes = max(max_input_bytes, len((content.get("prompt") or "").encode("utf-8")) +
                              len((content.get("system_prompt") or "").encode("utf-8")))
        if max_input_bytes > 4096:
            raise HTTPException(422, "Prompt input exceeds comparison limit")
        frozen[prompt.id] = {"version": version, "content_hash": published.content_hash}
    estimated_total = 0.0
    pricing = []
    for candidate in remote:
        estimate, price_id = await estimated_call_cost(db, project_id, candidate["provider"],
            candidate["model"], max_input_bytes, body.max_output_tokens)
        if estimate is None:
            raise HTTPException(422, f"No current configured price for {candidate['provider']}/{candidate['model']}")
        estimated_total += estimate * len(prompts)
        pricing.append({"candidate": candidate, "pricing_record_id": price_id, "per_call_estimate_usd": estimate})
    if remote and estimated_total > body.max_estimated_cost_usd:
        raise HTTPException(422, "Configured price estimate exceeds the approved limit")
    snapshot = {**body.model_dump(), "candidates": candidates,
        "dataset": {"prompt_set_id": dataset.id, "prompts": frozen},
        "provider_versions": "unavailable until provider metadata is captured",
        "remote_estimate_usd": round(estimated_total, 8) if remote else None,
        "pricing_evidence": pricing, "remote_estimate_is_not_hard_cap": bool(remote)}
    row = ComparisonPlan(id=str(uuid4()), project_id=project_id, snapshot=snapshot)
    db.add(row)
    audit(db, project_id, "comparison_plan.created", row.id,
          details={"candidate_count": len(candidates), "call_count": len(prompts) * len(candidates),
                   "remote": bool(remote)})
    await db.commit()
    return _view(row)


@router.get("")
async def list_plans(project_id: str, request: Request, limit: int = Query(25, ge=1, le=100),
                     offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    rows = (await db.execute(select(ComparisonPlan).where(ComparisonPlan.project_id == project_id)
        .order_by(ComparisonPlan.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return [_view(row, await evaluation_sessions.get(row.session_id) if row.session_id else None) for row in rows]


@router.get("/{plan_id}")
async def get_plan(project_id: str, plan_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _plan(db, project_id, plan_id)
    return _view(row, await evaluation_sessions.get(row.session_id) if row.session_id else None)


@router.post("/{plan_id}/start")
async def start_plan(project_id: str, plan_id: str, body: StartIn, request: Request,
                     db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _plan(db, project_id, plan_id)
    if row.session_id:
        raise HTTPException(409, "Plan already started; create a new immutable plan for another run")
    snap = row.snapshot
    remote = any(is_remote(c["provider"]) for c in snap["candidates"])
    if remote and not body.confirm_remote:
        raise HTTPException(409, "Confirm this billable remote run explicitly")
    budget = await db.get(ProjectBudget, project_id)
    if remote and budget and budget.hard_limit_usd is not None:
        raise HTTPException(409, "Hard budget enabled: cannot safely reserve provider spend; remote run blocked")
    config = {"comparison_plan_id": row.id, "prompt_versions": {
        pid: item["version"] for pid, item in snap["dataset"]["prompts"].items()},
        "options": {"temperature": snap["temperature"], "max_tokens": snap["max_output_tokens"],
                    **({"seed": snap["seed"]} if snap["seed"] is not None else {})},
        "timeout_seconds": snap["timeout_seconds"],
        "concurrency_limit": snap["concurrency_limit"], "project_id": project_id}
    try:
        result = await evaluation_sessions.schedule(models=[{"target_model": c["model"],
            "provider": c["provider"], "runtime": c["provider"],
            "label": f"{c['provider']}/{c['model']}"} for c in snap["candidates"]],
            prompt_set_ids=[snap["dataset"]["prompt_set_id"]], project_id=project_id,
            name=snap["name"], similarity=snap["similarity"], config=config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    row.session_id = result["id"]
    audit(db, project_id, "comparison_plan.started", row.id,
          details={"session_id": row.session_id, "remote": remote})
    await db.commit()
    return {"plan_id": row.id, **result}


@router.post("/{plan_id}/cancel")
async def cancel_plan(project_id: str, plan_id: str, request: Request,
                      db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _plan(db, project_id, plan_id)
    if not row.session_id:
        raise HTTPException(409, "Plan has not started")
    await evaluation_sessions.cancel(row.session_id)
    audit(db, project_id, "comparison_plan.cancelled", row.id)
    await db.commit()
    return {"id": row.id, "cancelled": True}


@router.get("/{plan_id}/results")
async def results(project_id: str, plan_id: str, request: Request,
                  format: Literal["json", "csv"] = "json", db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _plan(db, project_id, plan_id)
    if not row.session_id:
        return {"results": [], "status": "created"}
    session = await evaluation_sessions.get(row.session_id)
    data = await evaluation_sessions.results(row.session_id)
    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["provider", "model", "prompt_id", "prompt_version", "verdict", "similarity_score", "latency_ms", "input_tokens", "output_tokens", "error"])
        for item in data[:48]:
            def safe(value):
                value = str(value if value is not None else "")
                return "'" + value if value.startswith(("=", "+", "-", "@")) else value
            metrics = item["metrics"] or {}
            writer.writerow([safe(x) for x in (item["provider"], item["target_model"], item["prompt_id"],
                item["prompt_version"], item["verdict"], item["similarity_score"], metrics.get("latency_ms"),
                metrics.get("prompt_tokens"), metrics.get("completion_tokens"), item["error"])])
        audit(db, project_id, "comparison_plan.exported", row.id, details={"format": "csv"})
        await db.commit()
        return Response(out.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=redforge-comparison.csv"})
    return {"plan_id": row.id, "status": session["status"] if session else "unknown", "results": data,
            "methodology": "Per-prompt exact/text similarity is comparable only where the same frozen baseline and scorer were used. Missing metrics are null."}
