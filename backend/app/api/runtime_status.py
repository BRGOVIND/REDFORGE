"""Runtime status/metrics + read-only runtime logs endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import settings
from app.logging_config import get_recent_logs
from app.runtime.manager import get_runtime
from app.runtime.metrics import metrics

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@router.get("/status")
async def runtime_status() -> dict:
    runtime = get_runtime()
    return {
        "provider": runtime.provider.name,
        "concurrency_per_model": settings.RUNTIME_CONCURRENCY,
        "metrics": metrics.snapshot(),
    }


@router.get("/logs")
async def runtime_logs(limit: int = Query(200, ge=1, le=1000)) -> dict:
    """Recent captured log lines (read-only), oldest → newest."""
    return {"lines": get_recent_logs(limit)}
