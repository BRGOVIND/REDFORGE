"""Hardware Compatibility API (RedForge V3).

Exposes the Hardware Compatibility Engine so the UI can (a) show the detected training
device and (b) pre-check a training configuration BEFORE launch — turning a mid-load
CUDA OOM into an up-front, actionable answer with safe defaults and model
recommendations. Additive, provider-agnostic.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.hardware import hardware_service

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


class CheckRequest(BaseModel):
    base_model: str = Field(..., min_length=1)
    strategy: str = Field("qlora")
    hyperparameters: Optional[dict] = None
    provider: Optional[str] = None


@router.get("")
async def hardware() -> dict:
    """The detected training device (GPU name, VRAM total/free, backend)."""
    return {"gpu": hardware_service.snapshot()}


@router.post("/check")
async def check(req: CheckRequest) -> dict:
    """Assess whether a (model, strategy, hyperparameters) run fits the detected GPU.
    Returns the verdict (fits / tight / insufficient), a broken-down memory estimate,
    safe defaults, and — when it will not fit — recommended smaller models."""
    return hardware_service.check(
        base_model=req.base_model, strategy=req.strategy,
        hyperparameters=req.hyperparameters, provider=req.provider)
