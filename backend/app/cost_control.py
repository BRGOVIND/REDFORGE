"""Explicit operator pricing and bounded, SQL-side usage accounting.

No network pricing feeds and no guessed local-inference dollar value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select

from app.db.models import ModelPrice, TraceEvent


async def price_for(db, project_id: str, provider: str, model: str, at: datetime):
    return (await db.execute(select(ModelPrice).where(
        ModelPrice.project_id == project_id, ModelPrice.provider == provider,
        ModelPrice.model == model, ModelPrice.effective_at <= at,
    ).order_by(ModelPrice.effective_at.desc(), ModelPrice.version.desc()).limit(1))).scalar_one_or_none()


def calculated_cost(event: dict, price: ModelPrice) -> float | None:
    """Only categories with explicit rates can be priced. Counts are not guessed."""
    input_count, output_count = event.get("input_tokens"), event.get("output_tokens")
    if input_count is None or output_count is None:
        return None
    cached = event.get("cached_input_tokens") or 0
    reasoning = event.get("reasoning_tokens") or 0
    if cached > input_count or reasoning > output_count:
        return None
    rates = price.rates or {}
    counts = {
        "input": input_count - cached,
        "output": output_count - reasoning if "reasoning" in rates else output_count,
        "cached_input": cached,
        "reasoning": reasoning if "reasoning" in rates else 0,
    }
    if any(count and key not in rates for key, count in counts.items()):
        return None
    return round(sum(count * float(rates.get(key, 0)) / 1_000_000 for key, count in counts.items()), 10)


async def apply_price(db, event: dict) -> None:
    """Mutate a privacy-filtered event before persistence, never overwrite provider cost."""
    if event.get("cost_usd") is not None or event.get("status") != "success":
        return
    provider, model = event.get("provider"), event.get("model")
    if not provider or not model or provider in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        return
    at = event.get("started_at") or event["received_at"]
    price = await price_for(db, event["project_id"], provider, model, at)
    if price is None:
        return
    cost = calculated_cost(event, price)
    if cost is not None:
        event["cost_usd"] = cost
        event["cost_source"] = "configured" if event.get("usage_source") == "provider" else "estimated"
        event["pricing_record_id"] = price.id
        event["cost_calculated_at"] = datetime.now(timezone.utc)


def period_start(period: str, now: datetime) -> datetime:
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def usage_totals(db, project_id: str, start: datetime, end: datetime,
                       *, group_by: str = "provider", provider: str | None = None,
                       model: str | None = None, service: str | None = None,
                       environment: str | None = None, route: str | None = None,
                       tenant_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """One indexed date range; select one successful event per logical request.

    A missing request_id uses event_id, so retries of the same event never add cost.
    Multiple successful spans sharing a request_id count once per provider/model.
    """
    dimension = {
        "provider": TraceEvent.provider, "model": TraceEvent.model,
        "service": TraceEvent.service, "environment": TraceEvent.environment,
        "route": TraceEvent.route, "tenant": TraceEvent.tenant_id,
        "day": func.date(TraceEvent.received_at),
    }[group_by]
    predicates = [TraceEvent.project_id == project_id, TraceEvent.received_at >= start,
                  TraceEvent.received_at < end, TraceEvent.status == "success"]
    for column, value in ((TraceEvent.provider, provider), (TraceEvent.model, model),
                          (TraceEvent.service, service), (TraceEvent.environment, environment),
                          (TraceEvent.route, route), (TraceEvent.tenant_id, tenant_id)):
        if value is not None:
            predicates.append(column == value)
    # SQLite supports window functions; rank within the bounded, indexed range.
    ranked = select(
        TraceEvent.id.label("id"), dimension.label("dimension"),
        TraceEvent.cost_usd.label("cost"), TraceEvent.input_tokens.label("input_tokens"),
        TraceEvent.output_tokens.label("output_tokens"),
        TraceEvent.duration_ms.label("duration_ms"),
        func.row_number().over(partition_by=(
            func.coalesce(TraceEvent.logical_call_key, TraceEvent.request_id, TraceEvent.event_id),
            TraceEvent.provider, TraceEvent.model),
            order_by=TraceEvent.id.desc()).label("rank"),
    ).where(and_(*predicates)).subquery()
    stmt = select(
        ranked.c.dimension,
        func.count().label("calls"), func.sum(ranked.c.cost).label("cost_usd"),
        func.sum(ranked.c.input_tokens).label("input_tokens"),
        func.sum(ranked.c.output_tokens).label("output_tokens"),
        func.avg(ranked.c.duration_ms).label("avg_latency_ms"),
        func.sum(func.iif(ranked.c.cost.is_(None), 1, 0)).label("unpriced_calls"),
    ).where(ranked.c.rank == 1).group_by(ranked.c.dimension).order_by(ranked.c.dimension).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()
    return [{"dimension": row.dimension or "(unspecified)", "calls": row.calls,
             "cost_usd": round(row.cost_usd, 8) if row.cost_usd is not None else None,
             "input_tokens": row.input_tokens, "output_tokens": row.output_tokens,
             "avg_latency_ms": round(row.avg_latency_ms, 2) if row.avg_latency_ms is not None else None,
             "unpriced_calls": row.unpriced_calls} for row in rows]


async def project_spend(db, project_id: str, start: datetime, end: datetime) -> float:
    rows = await usage_totals(db, project_id, start, end, group_by="provider", limit=1000)
    return round(sum(row["cost_usd"] or 0 for row in rows), 8)
