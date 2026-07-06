"""Runtime status/metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
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
