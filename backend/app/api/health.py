"""System Health API — exposes the centralized HealthService.

``GET /api/health`` returns the full structured report; ``GET /api/health/{id}``
returns a single check. This is the API surface future UI (First Run Wizard,
Runtime Manager health view) consumes. Note: ``/healthz`` (liveness) is separate
and unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.health import HealthCheck, HealthReport
from app.health.service import health_service

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthReport)
async def get_health(
    include_network: bool = Query(False, description="also run the optional internet check"),
) -> HealthReport:
    return await health_service.run(include_network=include_network)


@router.get("/{check_id}", response_model=HealthCheck)
async def get_health_check(check_id: str) -> HealthCheck:
    check = await health_service.get_check(check_id)
    if check is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown health check '{check_id}'. Known: {health_service.check_ids()}",
        )
    return check
