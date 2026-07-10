"""HealthService — the single source of truth for system validation.

Runs a registry of provider-agnostic checks and returns a structured
:class:`HealthReport`. Every consumer (``/api/health``, ``redforge doctor``, the
onboarding endpoint, startup logging) goes through this one service, so there is
one implementation of each check.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from app.health import checks as C
from app.health.checks import HealthContext
from app.health.models import (
    HealthCheck,
    HealthReport,
    Outcome,
    Severity,
    Status,
    aggregate,
)
from app.logging_config import get_logger

logger = get_logger("health")

CheckFn = Callable[[HealthContext], Awaitable[Outcome]]

# (id, human name, severity, fn). Severity is a fixed property of the check
# (importance), independent of the run-time status. Order = display order.
# Provider-agnostic throughout.
_REGISTRY: list[tuple[str, str, str, CheckFn]] = [
    ("os", "Operating System", Severity.INFO, C.check_os),
    ("architecture", "Architecture", Severity.LOW, C.check_architecture),
    ("python_version", "Python", Severity.CRITICAL, C.check_python_version),
    ("runtime_providers", "Runtime Providers", Severity.HIGH, C.check_runtime_providers),
    ("provider_health", "Provider Health", Severity.HIGH, C.check_provider_health),
    ("installed_models", "Installed Models", Severity.MEDIUM, C.check_installed_models),
    ("cpu", "CPU", Severity.INFO, C.check_cpu),
    ("ram", "Available RAM", Severity.MEDIUM, C.check_ram),
    ("disk", "Disk Space", Severity.MEDIUM, C.check_disk),
    ("gpu", "GPU", Severity.LOW, C.check_gpu),
    ("cuda", "CUDA", Severity.LOW, C.check_cuda),
    ("ports", "Ports", Severity.LOW, C.check_ports),
    ("backend_status", "Backend Status", Severity.MEDIUM, C.check_backend_status),
    ("frontend_status", "Frontend Status", Severity.MEDIUM, C.check_frontend_status),
    ("database", "Database", Severity.HIGH, C.check_database),
    ("permissions", "Permissions", Severity.MEDIUM, C.check_permissions),
]

_NETWORK = ("network", "Network", Severity.LOW, C.check_network)


class HealthService:
    def __init__(self) -> None:
        self._by_id = {cid: (name, sev, fn) for cid, name, sev, fn in _REGISTRY}
        self._by_id[_NETWORK[0]] = (_NETWORK[1], _NETWORK[2], _NETWORK[3])

    # -- context (built once per run; shared by all checks) ----------------

    async def _build_context(self, include_network: bool) -> HealthContext:
        from app.resources.resource_monitor import detect_resources
        from app.runtime import manager
        from app.runtime.management import provider_manager

        resources = detect_resources()
        default = provider_manager.default_name()
        try:
            snapshot = await provider_manager.check(default)
        except Exception as exc:  # noqa: BLE001
            snapshot = {"online": False, "error": str(exc)}
        return HealthContext(
            resources=resources,
            provider_default=default,
            provider_snapshot=snapshot,
            providers_available=manager.available_providers(),
            app_port=C.app_port(),
            include_network=include_network,
        )

    async def _run_one(self, cid: str, name: str, severity: str, fn: CheckFn, ctx: HealthContext) -> HealthCheck:
        try:
            outcome = await fn(ctx)
        except Exception as exc:  # noqa: BLE001 - a broken check must never break the report
            outcome = Outcome(
                status=Status.WARNING,
                message=f"check failed to run: {exc}", metadata={"error": str(exc)},
            )
        return HealthCheck(
            id=cid, name=name, status=outcome.status, severity=severity,
            message=outcome.message, suggested_fix=outcome.suggested_fix,
            metadata=outcome.metadata,
        )

    # -- public API --------------------------------------------------------

    async def run(self, *, include_network: bool = False) -> HealthReport:
        ctx = await self._build_context(include_network)
        registry = list(_REGISTRY)
        if include_network:
            registry.append(_NETWORK)

        results = await asyncio.gather(
            *(self._run_one(cid, name, sev, fn, ctx) for cid, name, sev, fn in registry)
        )
        checks = list(results)
        status, ready, summary = aggregate(checks)
        return HealthReport(
            status=status, ready=ready,
            generated_at=datetime.now(timezone.utc).isoformat(),
            summary=summary, checks=checks,
        )

    async def get_check(self, check_id: str) -> Optional[HealthCheck]:
        entry = self._by_id.get(check_id)
        if entry is None:
            return None
        name, severity, fn = entry
        ctx = await self._build_context(include_network=(check_id == _NETWORK[0]))
        return await self._run_one(check_id, name, severity, fn, ctx)

    def check_ids(self) -> list[str]:
        return [cid for cid, _, _, _ in _REGISTRY] + [_NETWORK[0]]


health_service = HealthService()
