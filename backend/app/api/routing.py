"""Explicit, opt-in routing policies. No background or automatic switching."""
from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.cost_control import calculated_cost, price_for
from app.db.database import get_db
from app.db.models import Project, ProjectBudget, RoutingPolicy, RoutingState, TraceEvent
from app.observability_privacy import _scrub, audit, filter_event, get_policy
from app.optimization import BOUNDED_OPTIONS, estimated_call_cost, is_remote, recent_candidate_metrics
from app.runtime.manager import available_providers, get_runtime_for

router = APIRouter(prefix="/api/projects/{project_id}/routing", tags=["routing"])


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    mode: Literal["fixed", "fallback", "threshold"]
    candidates: list[Target] = Field(min_length=1, max_length=3)
    max_attempts: int = Field(default=1, ge=1, le=3)
    total_timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_output_tokens: int = Field(default=512, ge=1, le=2048)
    max_estimated_cost_usd: float | None = Field(default=None, gt=0, le=100)
    remote_enabled: bool = False
    max_observed_latency_ms: float | None = Field(default=None, gt=0, le=120000)
    max_observed_cost_usd: float | None = Field(default=None, ge=0, le=100)
    min_samples: int = Field(default=5, ge=5, le=1000)

    @model_validator(mode="after")
    def valid_policy(self):
        if len({(c.provider, c.model) for c in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate candidate")
        if self.mode == "fixed" and (len(self.candidates) != 1 or self.max_attempts != 1):
            raise ValueError("Fixed routing requires one candidate and one attempt")
        if self.max_attempts > len(self.candidates):
            raise ValueError("max_attempts exceeds candidates")
        if self.mode == "threshold" and self.max_observed_latency_ms is None and self.max_observed_cost_usd is None:
            raise ValueError("Threshold mode requires a measured latency or cost threshold")
        return self


class ExecuteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=4096)
    allow_remote: bool = False
    confirm_sensitive_remote: bool = False


async def _project(db, project_id, request):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


async def _policy(db, project_id, policy_id):
    row = (await db.execute(select(RoutingPolicy).where(RoutingPolicy.project_id == project_id,
        RoutingPolicy.id == policy_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Project routing policy not found")
    return row


def _view(row):
    return {"id": row.id, "project_id": row.project_id, "name": row.name,
            "version": row.version, "definition": row.definition, "created_at": row.created_at}


@router.post("/policies", status_code=201)
async def create_policy(project_id: str, body: PolicyIn, request: Request,
                        db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if any(c.provider not in available_providers() for c in body.candidates):
        raise HTTPException(422, "Unknown provider")
    if any(c.provider not in BOUNDED_OPTIONS for c in body.candidates):
        raise HTTPException(422, "Provider does not support bounded max-output sampling")
    if any(is_remote(c.provider) for c in body.candidates) and (
        not body.remote_enabled or body.max_estimated_cost_usd is None):
        raise HTTPException(422, "Remote routing requires explicit enablement and an estimated per-call cost limit")
    previous = (await db.execute(select(RoutingPolicy).where(RoutingPolicy.project_id == project_id,
        RoutingPolicy.name == body.name).order_by(RoutingPolicy.version.desc()).limit(1))).scalar_one_or_none()
    row = RoutingPolicy(id=str(uuid4()), project_id=project_id, name=body.name,
        version=previous.version + 1 if previous else 1, definition=body.model_dump())
    db.add(row)
    audit(db, project_id, "routing_policy.created", row.id,
          details={"version": row.version, "mode": body.mode, "remote_enabled": body.remote_enabled})
    await db.commit()
    return _view(row)


@router.get("/policies")
async def policies(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    rows = (await db.execute(select(RoutingPolicy).where(RoutingPolicy.project_id == project_id)
        .order_by(RoutingPolicy.created_at.desc()).limit(100))).scalars().all()
    state = await db.get(RoutingState, project_id)
    return {"active_policy_id": state.active_policy_id if state else None,
            "items": [_view(row) for row in rows]}


@router.put("/active/{policy_id}")
async def activate(project_id: str, policy_id: str, request: Request,
                   db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    await _policy(db, project_id, policy_id)
    state = await db.get(RoutingState, project_id)
    if state is None:
        state = RoutingState(project_id=project_id)
        db.add(state)
    state.active_policy_id = policy_id
    audit(db, project_id, "routing_policy.activated", policy_id)
    await db.commit()
    return {"active_policy_id": policy_id}


@router.delete("/active")
async def disable(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    state = await db.get(RoutingState, project_id)
    if state:
        state.active_policy_id = None
    audit(db, project_id, "routing_policy.disabled")
    await db.commit()
    return {"active_policy_id": None}


@router.post("/execute")
async def execute(project_id: str, body: ExecuteIn, request: Request,
                  db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    state = await db.get(RoutingState, project_id)
    if state is None or not state.active_policy_id:
        raise HTTPException(409, "Routing is disabled")
    policy = await _policy(db, project_id, state.active_policy_id)
    definition = PolicyIn.model_validate(policy.definition)
    selected = list(definition.candidates)
    evidence = []
    if definition.mode == "threshold":
        selected = []
        for candidate in definition.candidates:
            metric = await recent_candidate_metrics(db, project_id, candidate.provider, candidate.model)
            passed = metric["sample_count"] >= definition.min_samples
            if definition.max_observed_latency_ms is not None:
                passed = passed and metric["avg_latency_ms"] is not None and metric["avg_latency_ms"] <= definition.max_observed_latency_ms
            if definition.max_observed_cost_usd is not None:
                passed = passed and metric["avg_cost_usd"] is not None and metric["avg_cost_usd"] <= definition.max_observed_cost_usd
            evidence.append({"provider": candidate.provider, "model": candidate.model,
                             "metrics": metric, "eligible": passed})
            if passed:
                selected.append(candidate)
        if not selected:
            raise HTTPException(409, "No candidate has enough recent measured evidence within the configured thresholds")
    selected = selected[:definition.max_attempts]
    if any(is_remote(c.provider) for c in selected):
        if not (definition.remote_enabled and body.allow_remote and body.confirm_sensitive_remote):
            raise HTTPException(409, "Explicit per-call remote and sensitive-input confirmation required")
        budget = await db.get(ProjectBudget, project_id)
        if budget and budget.hard_limit_usd is not None:
            raise HTTPException(409, "Hard budget enabled: remote call blocked because provider spend cannot be reserved reliably")
        for candidate in selected:
            if not is_remote(candidate.provider):
                continue
            estimate, _ = await estimated_call_cost(db, project_id, candidate.provider,
                candidate.model, len(body.prompt.encode("utf-8")), definition.max_output_tokens)
            if estimate is None or estimate > definition.max_estimated_cost_usd:
                raise HTTPException(409, "Missing price or estimated call cost exceeds policy limit")
    attempts = []
    selected_result = None
    original_error = None
    started = time.monotonic()
    request_id = str(uuid4())
    privacy = await get_policy(db, project_id)
    for candidate in selected:
        remaining = definition.total_timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            attempts.append({"provider": candidate.provider, "model": candidate.model,
                             "status": "error", "error": "Total timeout exceeded"})
            break
        attempt_started = datetime.now(timezone.utc)
        tick = time.monotonic()
        try:
            runtime = get_runtime_for(candidate.provider)
            async with asyncio.timeout(remaining):
                result = await runtime.generate(candidate.model, body.prompt,
                    timeout=remaining, retries=0, options={"max_tokens": definition.max_output_tokens})
            elapsed = round((time.monotonic() - tick) * 1000, 2)
            tokens = {"input_tokens": result.prompt_eval_count, "output_tokens": result.eval_count,
                      "cached_input_tokens": result.cached_input_tokens,
                      "reasoning_tokens": result.reasoning_tokens}
            price = await price_for(db, project_id, candidate.provider, candidate.model, attempt_started) if is_remote(candidate.provider) else None
            cost = calculated_cost(tokens, price) if price else None
            attempt = {"provider": candidate.provider, "model": candidate.model,
                       "status": "success", "latency_ms": elapsed, **tokens,
                       "started_at": attempt_started,
                       "cost_usd": cost, "cost_source": "configured" if cost is not None else None,
                       "pricing_record_id": price.id if price else None}
            attempts.append(attempt)
            selected_result = result
            break
        except Exception as exc:  # one failed candidate must not mask the original failure
            error = str(_scrub(f"{type(exc).__name__}: {exc}", 300))
            if original_error is None:
                original_error = error
            attempts.append({"provider": candidate.provider, "model": candidate.model,
                             "status": "error", "error": error,
                             "started_at": attempt_started,
                             "latency_ms": round((time.monotonic() - tick) * 1000, 2)})
    for attempt in attempts:
        event = {"event_id": str(uuid4()), "project_id": project_id, "received_at": datetime.now(timezone.utc),
            "started_at": attempt.get("started_at"), "provider": attempt["provider"],
            "model": attempt["model"], "operation": "routed.generate", "status": attempt["status"],
            "duration_ms": attempt.get("latency_ms"), "request_id": request_id,
            "route": policy.name, "input_tokens": attempt.get("input_tokens"),
            "output_tokens": attempt.get("output_tokens"),
            "cached_input_tokens": attempt.get("cached_input_tokens"),
            "reasoning_tokens": attempt.get("reasoning_tokens"),
            "usage_source": "provider" if attempt.get("input_tokens") is not None else None,
            "cost_usd": attempt.get("cost_usd"), "cost_source": attempt.get("cost_source"),
            "pricing_record_id": attempt.get("pricing_record_id"),
            "cost_calculated_at": datetime.now(timezone.utc) if attempt.get("cost_usd") is not None else None,
            "error_category": "route_attempt" if attempt["status"] == "error" else None,
            "error_detail": attempt.get("error"), "attributes": {},
            "input_text": None, "output_text": None}
        filtered = filter_event(event, privacy)
        if filtered is not None:
            filtered["logical_call_key"] = hashlib.sha256(f"{project_id}\0{request_id}".encode()).hexdigest()
            db.add(TraceEvent(**filtered))
    audit(db, project_id, "routing_policy.executed", policy.id,
          details={"request_id": request_id, "attempts": len(attempts),
                   "selected": attempts[-1]["provider"] if selected_result else None})
    await db.commit()
    if selected_result is None:
        return {"status": "failed", "policy_id": policy.id, "policy_version": policy.version,
                "original_error": original_error, "attempts": attempts, "evidence": evidence,
                "output": None}
    return {"status": "success", "policy_id": policy.id, "policy_version": policy.version,
            "provider": attempts[-1]["provider"], "model": attempts[-1]["model"],
            "output": selected_result.text, "attempts": attempts, "evidence": evidence,
            "original_error": original_error}
