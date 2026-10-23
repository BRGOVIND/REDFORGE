"""Provider-neutral safety checks and evidence selection for opt-in optimization."""
from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.cost_control import price_for
from app.db.models import TraceEvent
from app.runtime.manager import build_provider

LOCAL_NAMES = {"ollama", "lmstudio", "llamacpp", "vllm"}
BOUNDED_OPTIONS = LOCAL_NAMES | {"openai", "groq", "openrouter"}


def is_loopback_provider(name: str) -> bool:
    if name not in LOCAL_NAMES:
        return False
    parsed = urlsplit(getattr(build_provider(name), "base_url", ""))
    if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def is_remote(name: str) -> bool:
    return not is_loopback_provider(name)


async def estimated_call_cost(db, project_id: str, provider: str, model: str,
                              input_bytes: int, max_tokens: int) -> tuple[float | None, str | None]:
    if not is_remote(provider):
        return None, None  # local resource use is not a dollar estimate
    price = await price_for(db, project_id, provider, model, datetime.now(timezone.utc))
    if price is None:
        return None, None
    rates = price.rates or {}
    if "input" not in rates or "output" not in rates:
        return None, price.id
    # A planning estimate, never a billable hard upper bound. Provider-added
    # system text, hidden reasoning tokens and cache policies may change usage.
    estimated = ((input_bytes + 64) * rates["input"] + max_tokens * rates["output"]) / 1_000_000
    return round(estimated, 8), price.id


async def recent_candidate_metrics(db, project_id: str, provider: str, model: str,
                                   *, minutes: int = 1440) -> dict:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    row = (await db.execute(select(
        func.count(TraceEvent.id), func.avg(TraceEvent.duration_ms),
        func.avg(TraceEvent.cost_usd), func.count(TraceEvent.cost_usd),
    ).where(TraceEvent.project_id == project_id, TraceEvent.provider == provider,
            TraceEvent.model == model, TraceEvent.status == "success",
            TraceEvent.received_at >= start, TraceEvent.received_at < end))).one()
    return {"sample_count": row[0], "avg_latency_ms": row[1],
            "avg_cost_usd": row[2] if row[3] == row[0] and row[0] else None,
            "window_start": start, "window_end": end}
