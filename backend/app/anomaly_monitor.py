"""Bounded, explainable local alert evaluation. No trace bodies leave the database."""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import case, func, select

from app.db.models import AnomalyAlert, AnomalyRule, EvaluationResult, TraceEvent, WorkbenchSession

MAX_WINDOW_ROWS = 5000
MAX_RULES_PER_TICK = 20


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    at = (len(ordered) - 1) * p
    lo = math.floor(at)
    return ordered[lo] + (ordered[math.ceil(at)] - ordered[lo]) * (at - lo)


def _value(metric: str, rows: list[tuple]) -> tuple[float | None, int]:
    if metric.startswith("latency_p"):
        values = [float(r[0]) for r in rows if r[0] is not None]
        return (_percentile(values, {"latency_p50": .5, "latency_p95": .95,
                                     "latency_p99": .99}[metric]), len(values)) if values else (None, 0)
    if metric == "error_rate":
        return (100 * sum(r[1] == "error" for r in rows) / len(rows), len(rows)) if rows else (None, 0)
    if metric == "timeout_rate":
        return (100 * sum(bool(r[5]) for r in rows) / len(rows), len(rows)) if rows else (None, 0)
    if metric in {"tokens_per_call", "cost_per_call_usd"}:
        idx = 3 if metric == "tokens_per_call" else 4
        values = [float(r[idx]) for r in rows if r[idx] is not None]
        return (sum(values) / len(values), len(values)) if values else (None, 0)
    if metric == "eval_pass_rate":
        graded = [r[1] for r in rows if r[1] in {"pass", "fail", "warn"}]
        return (100 * sum(x == "pass" for x in graded) / len(graded), len(graded)) if graded else (None, 0)
    return None, 0


async def _window(db, rule: AnomalyRule, start: datetime, end: datetime) -> tuple[float | None, int, bool]:
    if rule.metric == "eval_pass_rate":
        stmt = (select(EvaluationResult.id, EvaluationResult.verdict)
                .join(WorkbenchSession, WorkbenchSession.id == EvaluationResult.session_id)
                .where(WorkbenchSession.project_id == rule.project_id,
                       EvaluationResult.created_at >= start, EvaluationResult.created_at < end))
        if rule.model:
            stmt = stmt.where(EvaluationResult.target_model == rule.model)
        if rule.provider:
            stmt = stmt.where(EvaluationResult.provider == rule.provider)
        rows = (await db.execute(stmt.limit(MAX_WINDOW_ROWS + 1))).all()
    else:
        token_total = case((TraceEvent.input_tokens.is_(None) & TraceEvent.output_tokens.is_(None), None),
                           else_=func.coalesce(TraceEvent.input_tokens, 0) + func.coalesce(TraceEvent.output_tokens, 0))
        stmt = select(TraceEvent.duration_ms, TraceEvent.status, TraceEvent.error_category,
                      token_total, TraceEvent.cost_usd,
                      TraceEvent.timed_out).where(
                          TraceEvent.project_id == rule.project_id,
                          TraceEvent.received_at >= start, TraceEvent.received_at < end)
        for field in ("provider", "model", "service", "environment"):
            val = getattr(rule, field)
            if val:
                stmt = stmt.where(getattr(TraceEvent, field) == val)
        rows = (await db.execute(stmt.limit(MAX_WINDOW_ROWS + 1))).all()
    if len(rows) > MAX_WINDOW_ROWS:
        return None, len(rows), True
    value, count = _value(rule.metric, rows)
    return value, count, False


async def evaluate_rule(db, rule: AnomalyRule, *, at: datetime | None = None,
                        allow_health_probe: bool = True) -> dict:
    at = at or now_utc()
    start = at - timedelta(minutes=rule.observed_minutes)
    base_start = base_end = None
    if rule.metric == "provider_availability":
        if not allow_health_probe:
            return {"status": "insufficient_data", "reason": "provider probe disabled in dry run"}
        # Health Engine is the source of truth; a missing check is unknown, not down.
        from app.health.service import health_service
        try:
            check = await asyncio.wait_for(health_service.get_check("provider_health"), timeout=8)
        except Exception:
            check = None
        if not check or check.status == "warning":
            return {"status": "insufficient_data", "reason": "provider health unknown"}
        if rule.provider and rule.provider != check.metadata.get("provider"):
            return {"status": "insufficient_data", "reason": "health check covers a different provider"}
        observed, count, baseline = (0.0 if check.status == "error" else 100.0), 1, None
        triggered = observed < rule.threshold
    else:
        observed, count, capped = await _window(db, rule, start, at)
        if capped or count < rule.min_samples or observed is None:
            return {"status": "insufficient_data", "samples": count,
                    "reason": "window cap" if capped else "minimum samples not met"}
        baseline = None
        if rule.baseline_multiplier is not None:
            base_end = start
            base_start = base_end - timedelta(minutes=rule.baseline_minutes)
            baseline, base_count, capped = await _window(db, rule, base_start, base_end)
            if capped or base_count < rule.min_samples or baseline is None:
                return {"status": "insufficient_data", "samples": count,
                        "reason": "baseline cold or insufficient"}
        # Lower pass rate is bad; all other signals increase when unhealthy.
        if rule.metric == "eval_pass_rate":
            triggered = observed < rule.threshold and (baseline is None or observed <= baseline / rule.baseline_multiplier)
        else:
            triggered = observed > rule.threshold and (baseline is None or observed >= baseline * rule.baseline_multiplier)
    scope = {k: getattr(rule, k) for k in ("provider", "model", "service", "environment")}
    if rule.metric == "provider_availability":
        scope["provider"] = check.metadata.get("provider")
    return {"status": "anomaly" if triggered else "normal", "metric": rule.metric,
            "baseline": round(baseline, 4) if baseline is not None else None,
            "observed": round(observed, 4), "samples": count,
            "threshold": rule.threshold, "baseline_multiplier": rule.baseline_multiplier,
            "baseline_window_start": base_start, "baseline_window_end": base_end,
            "window_start": start, "window_end": at,
            "scope": scope}


async def scan_due(db, *, at: datetime | None = None, limit: int = MAX_RULES_PER_TICK) -> dict:
    at = at or now_utc()
    capacity = min(limit, MAX_RULES_PER_TICK)
    rules = list((await db.execute(select(AnomalyRule).where(
        AnomalyRule.enabled.is_(True), AnomalyRule.next_check_at.is_(None)
    ).limit(capacity))).scalars().all())
    if len(rules) < capacity:
        due = (await db.execute(select(AnomalyRule).where(
            AnomalyRule.enabled.is_(True), AnomalyRule.next_check_at <= at
        ).order_by(AnomalyRule.next_check_at).limit(capacity - len(rules)))).scalars().all()
        rules.extend(due)
    created = 0
    for rule in rules:
        rule.next_check_at = at + timedelta(seconds=rule.interval_seconds)
        try:
            result = await evaluate_rule(db, rule, at=at)
            if result["status"] != "anomaly":
                continue
            existing = (await db.execute(select(AnomalyAlert).where(
                AnomalyAlert.rule_id == rule.id,
                AnomalyAlert.state.in_(("open", "acknowledged", "suppressed"))
            ).order_by(AnomalyAlert.created_at.desc()).limit(1))).scalar_one_or_none()
            if existing:
                # One live alert per rule. Suppression and cooldown never create duplicates.
                last_seen = existing.last_seen_at
                if last_seen and last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                if last_seen and at - last_seen < timedelta(seconds=rule.cooldown_seconds):
                    continue
                existing.last_seen_at = at
                existing.observed = result["observed"]
                existing.baseline = result["baseline"]
                existing.sample_count = result["samples"]
                existing.window_start = result["window_start"]
                existing.window_end = result["window_end"]
                existing.occurrences += 1
                existing.evidence = {"samples": result["samples"], "scope": result["scope"],
                    "threshold": result["threshold"], "baseline_multiplier": result["baseline_multiplier"],
                    "baseline_window_start": result["baseline_window_start"].isoformat() if result["baseline_window_start"] else None,
                    "baseline_window_end": result["baseline_window_end"].isoformat() if result["baseline_window_end"] else None}
                continue
            db.add(AnomalyAlert(id=str(uuid4()), project_id=rule.project_id, rule_id=rule.id,
                metric=rule.metric, severity=rule.severity, observed=result["observed"],
                baseline=result["baseline"], sample_count=result["samples"],
                window_start=result["window_start"], window_end=result["window_end"],
                evidence={"samples": result["samples"], "scope": result["scope"],
                    "threshold": result["threshold"], "baseline_multiplier": result["baseline_multiplier"],
                    "baseline_window_start": result["baseline_window_start"].isoformat() if result["baseline_window_start"] else None,
                    "baseline_window_end": result["baseline_window_end"].isoformat() if result["baseline_window_end"] else None},
                created_at=at, last_seen_at=at))
            created += 1
        except Exception:
            # Broken rule cannot affect model serving or block other rules.
            continue
    await db.commit()
    return {"checked": len(rules), "created": created}
