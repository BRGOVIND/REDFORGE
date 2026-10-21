"""Loopback-only, project-scoped anomaly rules and alert history."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.anomaly_monitor import evaluate_rule
from app.api.traces import _local
from app.db.database import get_db
from app.db.models import AnomalyAlert, AnomalyRule, Project
from app.observability_privacy import audit

router = APIRouter(prefix="/api/projects/{project_id}", tags=["anomalies"])
Metric = Literal["latency_p50", "latency_p95", "latency_p99", "error_rate", "timeout_rate",
                 "tokens_per_call", "cost_per_call_usd", "provider_availability", "eval_pass_rate"]


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    metric: Metric
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    service: str | None = Field(default=None, max_length=120)
    environment: str | None = Field(default=None, max_length=80)
    threshold: float = Field(ge=0, le=1_000_000_000)
    baseline_multiplier: float | None = Field(default=None, gt=1, le=100)
    observed_minutes: int = Field(default=15, ge=1, le=1440)
    baseline_minutes: int = Field(default=60, ge=1, le=10080)
    min_samples: int = Field(default=20, ge=1, le=5000)
    interval_seconds: int = Field(default=300, ge=60, le=86400)
    cooldown_seconds: int = Field(default=1800, ge=60, le=604800)
    severity: Literal["info", "warning", "critical"] = "warning"
    enabled: bool = True

    @model_validator(mode="after")
    def valid_direction(self):
        if self.metric in {"error_rate", "timeout_rate", "eval_pass_rate", "provider_availability"} and self.threshold > 100:
            raise ValueError("Rate or availability threshold must be 0..100")
        if self.metric == "provider_availability" and self.baseline_multiplier is not None:
            raise ValueError("Provider availability uses live Health Engine status, not a baseline")
        if self.metric == "provider_availability" and self.min_samples != 1:
            raise ValueError("Provider availability is one explicit Health Engine probe; set min_samples=1")
        if self.metric == "provider_availability" and (self.model or self.service or self.environment):
            raise ValueError("Provider health supports only a provider filter")
        if self.metric == "eval_pass_rate" and (self.service or self.environment):
            raise ValueError("Evaluation results do not carry service or environment fields")
        return self


class AlertStateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["acknowledged", "resolved", "suppressed"]
    confirm_incident: bool = False


async def _project(db: AsyncSession, project_id: str, request: Request) -> None:
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


def _rule_dict(r: AnomalyRule) -> dict:
    return {k: getattr(r, k) for k in ("id", "project_id", "name", "metric", "provider", "model",
        "service", "environment", "threshold", "baseline_multiplier", "observed_minutes",
        "baseline_minutes", "min_samples", "interval_seconds", "cooldown_seconds", "severity",
        "enabled", "next_check_at", "created_at", "updated_at")}


def _alert_dict(a: AnomalyAlert) -> dict:
    return {k: getattr(a, k) for k in ("id", "project_id", "rule_id", "state", "classification",
        "severity", "metric", "baseline", "observed", "sample_count", "window_start", "window_end",
        "evidence", "occurrences", "created_at", "last_seen_at", "resolved_at")}


@router.get("/anomaly-rules")
async def rules(project_id: str, request: Request, offset: int = Query(0, ge=0),
                limit: int = Query(50, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    stmt = select(AnomalyRule).where(AnomalyRule.project_id == project_id)
    total = await db.scalar(select(func.count()).select_from(AnomalyRule).where(AnomalyRule.project_id == project_id))
    rows = (await db.execute(stmt.order_by(AnomalyRule.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    return {"items": [_rule_dict(r) for r in rows], "total": total, "offset": offset, "limit": limit}


@router.post("/anomaly-rules", status_code=201)
async def create_rule(project_id: str, body: RuleIn, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    r = AnomalyRule(id=str(uuid4()), project_id=project_id, **body.model_dump())
    db.add(r)
    audit(db, project_id, "anomaly_rule_created", r.id, details={"metric": r.metric})
    await db.commit()
    await db.refresh(r)
    return _rule_dict(r)


@router.put("/anomaly-rules/{rule_id}")
async def update_rule(project_id: str, rule_id: str, body: RuleIn, request: Request,
                      db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    r = (await db.execute(select(AnomalyRule).where(AnomalyRule.project_id == project_id,
                                               AnomalyRule.id == rule_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Rule not found")
    for key, val in body.model_dump().items():
        setattr(r, key, val)
    r.next_check_at = None
    audit(db, project_id, "anomaly_rule_updated", r.id)
    await db.commit()
    return _rule_dict(r)


@router.post("/anomaly-rules/{rule_id}/dry-run")
async def dry_run(project_id: str, rule_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    r = (await db.execute(select(AnomalyRule).where(AnomalyRule.project_id == project_id,
                                               AnomalyRule.id == rule_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "Rule not found")
    return await evaluate_rule(db, r, allow_health_probe=False)


@router.post("/anomaly-rules/scan")
async def scan(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    # Manual scan remains bounded; do not evaluate other projects from this route.
    rules = (await db.execute(select(AnomalyRule).where(AnomalyRule.project_id == project_id,
        AnomalyRule.enabled.is_(True)).order_by(AnomalyRule.id).limit(20))).scalars().all()
    return {"items": [{"rule_id": r.id, **(await evaluate_rule(db, r, allow_health_probe=False))} for r in rules]}


@router.get("/alerts")
async def alerts(project_id: str, request: Request, state: str | None = None,
                 offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                 db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if state and state not in {"open", "acknowledged", "resolved", "suppressed"}:
        raise HTTPException(422, "Invalid alert state")
    condition = [AnomalyAlert.project_id == project_id]
    if state:
        condition.append(AnomalyAlert.state == state)
    total = await db.scalar(select(func.count()).select_from(AnomalyAlert).where(*condition))
    rows = (await db.execute(select(AnomalyAlert).where(*condition)
        .order_by(AnomalyAlert.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    return {"items": [_alert_dict(a) for a in rows], "total": total, "offset": offset, "limit": limit}


@router.post("/alerts/{alert_id}/state")
async def set_state(project_id: str, alert_id: str, body: AlertStateIn, request: Request,
                    db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    a = (await db.execute(select(AnomalyAlert).where(AnomalyAlert.project_id == project_id,
                                                 AnomalyAlert.id == alert_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Alert not found")
    if a.state == "resolved" and body.state != "resolved":
        raise HTTPException(409, "Resolved alerts cannot be reopened; a new anomaly creates a new alert")
    a.state = body.state
    if body.confirm_incident:
        a.classification = "incident"
    if body.state == "resolved":
        a.resolved_at = datetime.now(timezone.utc)
    audit(db, project_id, "anomaly_alert_state", a.id, details={"state": a.state, "classification": a.classification})
    await db.commit()
    return _alert_dict(a)
