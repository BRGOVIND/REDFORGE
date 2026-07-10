"""Types for the System Health Engine.

Every check produces a :class:`HealthCheck` with a fixed, structured shape — never
a plain string — so any consumer (CLI, API, future UI) renders the same data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field


class Status:
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


class Severity:
    CRITICAL = "critical"  # blocks running RedForge at all
    HIGH = "high"          # blocks evaluations
    MEDIUM = "medium"      # degrades experience
    LOW = "low"            # informational / optional
    INFO = "info"          # pure information, never a problem


# Severities that make an ``error`` status count against readiness.
_BLOCKING = {Severity.CRITICAL, Severity.HIGH}


@dataclass
class Outcome:
    """A check's result. ``severity`` is a fixed property of the check itself
    (assigned by the service from the registry), so it is not set here."""

    status: str
    message: str
    suggested_fix: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def healthy(message: str, **metadata: Any) -> Outcome:
    return Outcome(Status.HEALTHY, message, None, dict(metadata))


def warning(message: str, fix: Optional[str] = None, **metadata: Any) -> Outcome:
    return Outcome(Status.WARNING, message, fix, dict(metadata))


def error(message: str, fix: Optional[str] = None, **metadata: Any) -> Outcome:
    return Outcome(Status.ERROR, message, fix, dict(metadata))


class HealthCheck(BaseModel):
    id: str
    name: str
    status: str            # healthy | warning | error
    severity: str          # critical | high | medium | low | info
    message: str
    suggested_fix: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthSummary(BaseModel):
    total: int
    healthy: int
    warning: int
    error: int


class HealthReport(BaseModel):
    status: str            # aggregate: healthy | warning | error
    ready: bool            # no blocking (critical/high) errors
    generated_at: str
    summary: HealthSummary
    checks: list[HealthCheck]


def aggregate(checks: list[HealthCheck]) -> tuple[str, bool, HealthSummary]:
    counts = {Status.HEALTHY: 0, Status.WARNING: 0, Status.ERROR: 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    if counts[Status.ERROR]:
        status = Status.ERROR
    elif counts[Status.WARNING]:
        status = Status.WARNING
    else:
        status = Status.HEALTHY
    ready = not any(
        c.status == Status.ERROR and c.severity in _BLOCKING for c in checks
    )
    summary = HealthSummary(
        total=len(checks),
        healthy=counts[Status.HEALTHY],
        warning=counts[Status.WARNING],
        error=counts[Status.ERROR],
    )
    return status, ready, summary
