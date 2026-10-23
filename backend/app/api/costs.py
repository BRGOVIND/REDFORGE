"""Project-scoped, operator-configured prices, budgets, and trace cost reports."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.cost_control import period_start, price_for, project_spend, usage_totals
from app.db.database import get_db
from app.db.models import AnomalyRule, ModelPrice, Project, ProjectBudget
from app.observability_privacy import audit
from app.runtime.manager import available_providers

router = APIRouter(prefix="/api/projects/{project_id}/costs", tags=["costs"])


class PriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)
    effective_at: datetime
    source: str = Field(min_length=3, max_length=300)
    input_usd_per_million: float = Field(ge=0, le=1_000_000)
    output_usd_per_million: float = Field(ge=0, le=1_000_000)
    cached_input_usd_per_million: float | None = Field(default=None, ge=0, le=1_000_000)
    reasoning_usd_per_million: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def valid_time(self):
        if self.effective_at.tzinfo is None:
            raise ValueError("effective_at must include a timezone")
        return self


class BudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: Literal["daily", "monthly"] = "monthly"
    soft_limit_usd: float = Field(gt=0, le=1_000_000)
    hard_limit_usd: float | None = Field(default=None, gt=0, le=1_000_000)

    @model_validator(mode="after")
    def valid_limits(self):
        if self.hard_limit_usd is not None and self.hard_limit_usd < self.soft_limit_usd:
            raise ValueError("hard limit must be at least the soft limit")
        return self


async def _project(db: AsyncSession, project_id: str, request: Request) -> None:
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


def _price_view(row: ModelPrice) -> dict:
    return {"id": row.id, "project_id": row.project_id, "provider": row.provider,
            "model": row.model, "version": row.version, "effective_at": row.effective_at,
            "source": row.source, "rates": row.rates, "created_at": row.created_at}


@router.post("/prices", status_code=201)
async def create_price(project_id: str, body: PriceIn, request: Request,
                       db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if body.provider not in available_providers():
        raise HTTPException(422, "Unknown provider")
    if body.provider in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        raise HTTPException(422, "Local inference has no configured monetary cost")
    last = (await db.execute(select(ModelPrice).where(ModelPrice.project_id == project_id,
        ModelPrice.provider == body.provider, ModelPrice.model == body.model)
        .order_by(ModelPrice.version.desc()).limit(1))).scalar_one_or_none()
    rates = {"input": body.input_usd_per_million, "output": body.output_usd_per_million}
    if body.cached_input_usd_per_million is not None:
        rates["cached_input"] = body.cached_input_usd_per_million
    if body.reasoning_usd_per_million is not None:
        rates["reasoning"] = body.reasoning_usd_per_million
    row = ModelPrice(id=str(uuid4()), project_id=project_id, provider=body.provider,
        model=body.model, version=(last.version + 1 if last else 1),
        effective_at=body.effective_at.astimezone(timezone.utc), source=body.source,
        rates=rates)
    db.add(row)
    audit(db, project_id, "model_price.created", row.id, details={"provider": body.provider,
        "model": body.model, "version": row.version, "source": body.source})
    await db.commit()
    return _price_view(row)


@router.get("/prices")
async def list_prices(project_id: str, request: Request, provider: str | None = None,
                      model: str | None = None, limit: int = Query(50, ge=1, le=100),
                      offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    stmt = select(ModelPrice).where(ModelPrice.project_id == project_id)
    if provider:
        stmt = stmt.where(ModelPrice.provider == provider)
    if model:
        stmt = stmt.where(ModelPrice.model == model)
    rows = (await db.execute(stmt.order_by(ModelPrice.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return [_price_view(row) for row in rows]


@router.put("/budget")
async def set_budget(project_id: str, body: BudgetIn, request: Request,
                     db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await db.get(ProjectBudget, project_id)
    if row is None:
        row = ProjectBudget(project_id=project_id)
        db.add(row)
    row.period = body.period
    row.soft_limit_usd = body.soft_limit_usd
    row.hard_limit_usd = body.hard_limit_usd
    rule = (await db.execute(select(AnomalyRule).where(AnomalyRule.project_id == project_id,
        AnomalyRule.metric == "project_spend_usd", AnomalyRule.name == "Project spend budget")
        .limit(1))).scalar_one_or_none()
    if rule is None:
        rule = AnomalyRule(id=str(uuid4()), project_id=project_id, name="Project spend budget",
            metric="project_spend_usd", threshold=body.soft_limit_usd,
            min_samples=1, observed_minutes=1440, baseline_minutes=60,
            interval_seconds=300, cooldown_seconds=1800, severity="warning", enabled=True)
        db.add(rule)
    else:
        rule.threshold = body.soft_limit_usd
        rule.enabled = True
    audit(db, project_id, "cost_budget.changed", project_id,
          details={"period": body.period, "soft": body.soft_limit_usd, "hard": body.hard_limit_usd})
    await db.commit()
    return {"period": row.period, "soft_limit_usd": row.soft_limit_usd,
            "hard_limit_usd": row.hard_limit_usd,
            "hard_limit_behavior": "billable routed and comparison calls blocked; SDK calls cannot be preempted"}


@router.get("/budget")
async def get_budget(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await db.get(ProjectBudget, project_id)
    if row is None:
        return {"configured": False}
    now = datetime.now(timezone.utc)
    spent = await project_spend(db, project_id, period_start(row.period, now), now)
    return {"configured": True, "period": row.period,
        "soft_limit_usd": row.soft_limit_usd, "hard_limit_usd": row.hard_limit_usd,
        "observed_usd": spent, "soft_exceeded": spent >= row.soft_limit_usd,
        "hard_exceeded": row.hard_limit_usd is not None and spent >= row.hard_limit_usd,
        "unpriced_usage_excluded": True,
        "hard_limit_behavior": "billable routed and comparison calls blocked; SDK calls cannot be preempted"}


@router.get("/usage")
async def usage(project_id: str, request: Request, start: datetime | None = None,
                end: datetime | None = None,
                group_by: Literal["provider", "model", "service", "environment", "route", "tenant", "day"] = "provider",
                provider: str | None = None, model: str | None = None, service: str | None = None,
                environment: str | None = None, route: str | None = None, tenant_id: str | None = None,
                format: Literal["json", "csv"] = "json", limit: int = Query(50, ge=1, le=100),
                offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    now = datetime.now(timezone.utc)
    end = end or now
    start = start or (end - timedelta(days=30))
    if start.tzinfo is None or end.tzinfo is None or start >= end or end - start > timedelta(days=93):
        raise HTTPException(422, "Use timezone-aware dates and a range of at most 93 days")
    rows = await usage_totals(db, project_id, start, end, group_by=group_by,
        provider=provider, model=model, service=service, environment=environment,
        route=route, tenant_id=tenant_id, limit=limit, offset=offset)
    if format == "csv":
        buffer = io.StringIO()
        columns = ["dimension", "calls", "cost_usd", "input_tokens", "output_tokens", "avg_latency_ms", "unpriced_calls"]
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "dimension": "'" + row["dimension"] if row["dimension"].startswith(("=", "+", "-", "@")) else row["dimension"]})
        audit(db, project_id, "cost_usage.exported", details={"group_by": group_by, "format": "csv"})
        await db.commit()
        return Response(buffer.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=redforge-cost-usage.csv"})
    return {"project_id": project_id, "start": start, "end": end, "group_by": group_by,
            "rows": rows, "pricing_note": "Only successful priced calls count toward USD totals; unpriced calls shown separately."}
