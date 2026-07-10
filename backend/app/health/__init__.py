"""System Health Engine — the single source of truth for RedForge validation.

Consumers (``/api/health``, ``redforge doctor``, the onboarding endpoint, startup
logging, installer verification) all go through :data:`health_service`; no check
logic is duplicated. See :mod:`app.health.checks` for the provider-agnostic checks.
"""
from app.health.models import (
    HealthCheck,
    HealthReport,
    HealthSummary,
    Severity,
    Status,
)
from app.health.service import HealthService, health_service

__all__ = [
    "health_service",
    "HealthService",
    "HealthCheck",
    "HealthReport",
    "HealthSummary",
    "Status",
    "Severity",
]
