"""Export Engine API (RedForge V3, Epic 3).

Additive router at ``/api/export``. Thin adapter over :mod:`app.export`. Export runs
as a Job — never inline.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.export import export_service, list_export_providers

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportRequest(BaseModel):
    source_artifact_id: str = Field(..., min_length=1)
    target: str = "gguf"                    # gguf | ollama
    base_model: str = ""
    quantization: str = "q4_k_m"
    model_name: Optional[str] = None
    project_id: Optional[str] = None
    experiment_id: Optional[str] = None


@router.get("/providers")
async def providers() -> list[dict]:
    return list_export_providers()


@router.get("/history")
async def history(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    return await export_service.history(limit=limit)


@router.post("", status_code=202)
async def submit_export(req: ExportRequest) -> dict:
    """Submit an export (merge → GGUF → optional Ollama import) as a Job."""
    return await export_service.submit(
        source_artifact_id=req.source_artifact_id, target=req.target, base_model=req.base_model,
        quantization=req.quantization, model_name=req.model_name, project_id=req.project_id,
        experiment_id=req.experiment_id)
