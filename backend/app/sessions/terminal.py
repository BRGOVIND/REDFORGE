"""Derive human-readable terminal lines from real evaluation events.

This is the single source of truth for terminal output. It never invents logs —
each line is a rendering of an actual persisted :class:`EvaluationEvent`. The
frontend terminal simply displays what this produces.

Levels map to terminal colors: info→gray, success→green, warning→yellow,
failure→red, system→blue.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.db.models import EvaluationEvent
from app.sessions.constants import EventType


class TerminalLine(BaseModel):
    id: int              # source event id — doubles as the stream cursor
    ts: Optional[str]    # ISO timestamp
    level: str           # info | success | warning | failure | system
    text: str


def _title(s: Optional[str]) -> str:
    return (s or "").replace("_", " ").title()


def _meta(event: EvaluationEvent) -> dict:
    return event.event_metadata or {}


def event_to_line(event: EvaluationEvent, total_tasks: int = 0) -> Optional[TerminalLine]:
    """Render one event as a terminal line, or ``None`` if it is not worth showing."""
    et = event.event_type
    md = _meta(event)
    ts = event.timestamp.isoformat() if event.timestamp else None

    def line(level: str, text: str) -> TerminalLine:
        return TerminalLine(id=event.id, ts=ts, level=level, text=text)

    if et == EventType.SESSION_CREATED:
        profile = md.get("profile")
        return line("system", f'Loading profile "{profile}"' if profile else "Session created")

    if et == EventType.MODEL_PROFILED:
        models = md.get("models") or []
        detail = ", ".join(models) if models else "model"
        return line("system", f"Detected model — {detail}")

    if et == EventType.PLAN_GENERATED:
        n = md.get("total_attacks")
        return line("system", f"Planning evaluation… ready ({n} attacks)" if n else "Planning evaluation… ready")

    if et == EventType.MODEL_STARTED:
        return line("system", f"Model {event.model_name} engaged")

    if et == EventType.ATTACK_STARTED:
        order = md.get("order")
        counter = f" — attack {order + 1}/{total_tasks}" if order is not None and total_tasks else ""
        return line("info", f"Running {_title(event.category)}{counter}")

    if et == EventType.RESPONSE_RECEIVED:
        lat = event.latency_ms
        return line("info", f"Response received{f' · {lat} ms' if lat else ''}")

    if et == EventType.VERDICT_GENERATED:
        verdict = (event.verdict or "").upper()
        reason = md.get("reason")
        lat = event.latency_ms
        suffix = f" — {reason}" if reason else ""
        lat_s = f" ({lat} ms)" if lat else ""
        if verdict == "PASS":
            return line("success", f"Verdict PASS{suffix}{lat_s}")
        if verdict == "FAIL":
            return line("failure", f"Verdict FAIL — unsafe{f' · {reason}' if reason else ''}{lat_s}")
        if verdict == "ERROR":
            return line("failure", f"Error{suffix}")
        return line("warning", f"Verdict UNCERTAIN{suffix}{lat_s}")

    if et == EventType.MUTATION_APPLIED:
        strat = md.get("strategy")
        return line("warning", f"Retrying with mutation ({strat})…" if strat else "Retrying with mutation…")

    if et == EventType.ATTACK_RETRIED:
        attempt = md.get("attempt")
        strat = md.get("strategy")
        return line("warning", f"Retry {attempt} ({strat})" if strat else f"Retry {attempt}")

    if et == EventType.HEARTBEAT:
        return line("info", str(md.get("text") or "still running…"))

    if et == EventType.ANALYSIS_COMPLETED:
        return line("system", "Analyzing results… complete")

    if et == EventType.REPORT_GENERATED:
        score = md.get("overall_security_score")
        return line("system", f"Report generated — security score {round(score)}" if score is not None else "Report generated")

    if et == EventType.SESSION_COMPLETED:
        return line("success", "Session completed")

    if et == EventType.SESSION_FAILED:
        return line("failure", f"Session failed — {md.get('error', 'unknown error')}")

    return None


def events_to_lines(events: list[EvaluationEvent], total_tasks: int = 0) -> list[TerminalLine]:
    lines: list[TerminalLine] = []
    for ev in events:
        rendered = event_to_line(ev, total_tasks)
        if rendered is not None:
            lines.append(rendered)
    return lines
