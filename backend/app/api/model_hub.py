"""Model Hub API (RedForge V3). Browse the curated catalog and start one-click
downloads (which run as Jobs → visible in the Global Task Manager)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.model_hub import model_hub_service

router = APIRouter(prefix="/api/model-hub", tags=["model-hub"])


class DownloadRequest(BaseModel):
    source: Optional[str] = None       # "huggingface" | "ollama" (defaults to HF)
    project_id: Optional[str] = None


@router.get("")
async def catalog() -> dict:
    """The curated model catalog, grouped by category, with per-model metadata + badges."""
    return model_hub_service.catalog()


@router.get("/{model_id}")
async def get_model(model_id: str) -> dict:
    m = model_hub_service.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="model not found in catalog")
    return m


@router.post("/{model_id}/download")
async def download(model_id: str, req: DownloadRequest) -> dict:
    """Start a one-click download as a Job. Track it in the Task Panel."""
    job = await model_hub_service.download(model_id, source=req.source, project_id=req.project_id)
    if job is None:
        raise HTTPException(status_code=404, detail="model not found in catalog")
    return {"task": job, "message": "Download started — track it in the task panel"}
