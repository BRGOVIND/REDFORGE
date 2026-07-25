"""Dataset Platform API (RedForge V3, Epic 3).

Additive router at ``/api/dataset-platform`` (distinct from the legacy
``/api/datasets``). Thin adapter over :mod:`app.datasets`. Literal routes precede
``/{dataset_id}``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.datasets import dataset_platform

router = APIRouter(prefix="/api/dataset-platform", tags=["dataset-platform"])


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    records: list = Field(default_factory=list)
    format: str = "jsonl"
    kind: str = "records"
    project_id: Optional[str] = None
    description: str = ""


class ProcessRequest(BaseModel):
    operation: str = "validate"          # validate | split
    train: float = 0.8
    val: float = 0.1
    test: float = 0.1
    seed: int = 42


@router.get("/formats")
async def formats() -> list[str]:
    from app.datasets_lab import parsers
    return parsers.SUPPORTED_FORMATS


@router.get("")
async def list_datasets(project_id: Optional[str] = Query(None)) -> list[dict]:
    return await dataset_platform.list(project_id=project_id)


@router.post("", status_code=201)
async def register(req: RegisterRequest) -> dict:
    if not req.records:
        raise HTTPException(status_code=422, detail="records must not be empty")
    return await dataset_platform.register(
        name=req.name, records=req.records, fmt=req.format, kind=req.kind,
        project_id=req.project_id, description=req.description)


@router.post("/import", status_code=201)
async def import_dataset(file: UploadFile = File(...), name: Optional[str] = Form(None),
                         project_id: Optional[str] = Form(None)) -> dict:
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    try:
        return await dataset_platform.import_bytes(
            name=name or file.filename or "dataset", data=data,
            filename=file.filename or "", project_id=project_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"could not parse file: {exc}")


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str) -> dict:
    d = await dataset_platform.get(dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return d


@router.get("/{dataset_id}/versions")
async def versions(dataset_id: str) -> list[dict]:
    return await dataset_platform.versions(dataset_id)


@router.get("/{dataset_id}/preview")
async def preview(dataset_id: str, offset: int = Query(0, ge=0),
                  limit: int = Query(50, ge=1, le=500)) -> dict:
    p = await dataset_platform.preview(dataset_id, offset=offset, limit=limit)
    if p is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return p


@router.get("/{dataset_id}/statistics")
async def statistics(dataset_id: str) -> dict:
    s = await dataset_platform.statistics(dataset_id)
    if s is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return s


@router.get("/{dataset_id}/validate")
async def validate(dataset_id: str) -> dict:
    v = await dataset_platform.validate(dataset_id)
    if v is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return v


@router.post("/{dataset_id}/process", status_code=202)
async def process(dataset_id: str, req: ProcessRequest) -> dict:
    """Run dataset processing (validate/split) as a Job (Constitution §12, §8)."""
    from app.jobs import job_service
    d = await dataset_platform.get(dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return await job_service.submit(
        type="dataset_processing", target_ref=dataset_id, project_id=d.get("project_id"),
        params={"dataset_id": dataset_id, "operation": req.operation,
                "train": req.train, "val": req.val, "test": req.test, "seed": req.seed})


@router.delete("/{dataset_id}")
async def delete(dataset_id: str) -> dict:
    ok = await dataset_platform.delete(dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="dataset not found")
    return {"deleted": True, "id": dataset_id}
