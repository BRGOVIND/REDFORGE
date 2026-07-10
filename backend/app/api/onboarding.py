"""Onboarding API — hardware-aware recommendations and model downloads.

Additive and provider-agnostic. Recommendations reuse the resource monitor,
Runtime Manager, and model-size heuristics (see ``app.onboarding.recommender``).
Model downloads reuse the active provider's ``pull_model`` capability; progress
is tracked in memory and polled, matching the rest of the app's poll model.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.logging_config import get_logger
from app.onboarding import build_recommendations
from app.runtime.errors import RuntimeLLMError
from app.runtime.manager import get_runtime

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
logger = get_logger("onboarding")


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

@router.get("/recommendations")
async def recommendations() -> dict:
    """Detected hardware + the recommended runtime and models for this machine."""
    return await build_recommendations()


# ---------------------------------------------------------------------------
# Model download (pull) — in-memory progress tracker + background task
# ---------------------------------------------------------------------------

class PullRequest(BaseModel):
    model: str


class _PullTracker:
    """Tracks in-flight model pulls by name (process-local)."""

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def snapshot(self, model: str) -> Optional[dict]:
        return self._state.get(model)

    def _percent(self, completed: Optional[int], total: Optional[int]) -> Optional[float]:
        if not total:
            return None
        return round(min(100.0, max(0.0, completed / total * 100)), 1)

    async def _run(self, model: str) -> None:
        provider = get_runtime().provider
        try:
            async for chunk in provider.pull_model(model):
                status = chunk.get("status", "")
                completed = chunk.get("completed")
                total = chunk.get("total")
                st = self._state[model]
                st.update(
                    status=status,
                    completed_mb=(completed // (1024 * 1024)) if completed else st.get("completed_mb"),
                    total_mb=(total // (1024 * 1024)) if total else st.get("total_mb"),
                    percent=self._percent(completed, total) if total else st.get("percent"),
                )
                if status == "success" or "success" in status.lower():
                    st.update(done=True, percent=100.0)
            self._state[model].update(done=True)
            if self._state[model].get("percent") is None:
                self._state[model]["percent"] = 100.0
        except RuntimeLLMError as exc:
            self._state[model].update(done=True, error=exc.message)
        except Exception as exc:  # noqa: BLE001
            self._state[model].update(done=True, error=str(exc))

    def start(self, model: str) -> dict:
        existing = self._state.get(model)
        if existing and not existing.get("done"):
            return existing  # already in progress — idempotent
        self._state[model] = {
            "model": model, "status": "starting", "percent": None,
            "completed_mb": None, "total_mb": None, "done": False, "error": None,
        }
        self._tasks[model] = asyncio.create_task(self._run(model))
        return self._state[model]


_pull_tracker = _PullTracker()


@router.post("/models/pull")
async def start_pull(req: PullRequest) -> dict:
    """Begin downloading a model with the active provider (if it supports pull)."""
    provider = get_runtime().provider
    if not getattr(provider, "supports_pull", False):
        raise HTTPException(
            status_code=400,
            detail=f"The active provider '{getattr(provider, 'name', '?')}' cannot download models.",
        )
    if not req.model.strip():
        raise HTTPException(status_code=422, detail="model is required")
    logger.info("onboarding pull requested: %s", req.model)
    return _pull_tracker.start(req.model.strip())


@router.get("/models/pull")
async def pull_status(model: str) -> dict:
    """Poll the progress of a model download."""
    snap = _pull_tracker.snapshot(model)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"No pull in progress for '{model}'")
    return snap
