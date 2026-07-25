"""Job System API (RedForge V3, Epic 2).

Additive router at ``/api/jobs``. Thin adapter over :mod:`app.jobs`. Literal routes
precede ``/{job_id}``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.jobs import job_service, list_job_types

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class SubmitRequest(BaseModel):
    type: str = Field(..., min_length=1, max_length=60)
    params: dict = Field(default_factory=dict)
    target_ref: Optional[str] = None
    project_id: Optional[str] = None
    priority: int = 0
    max_attempts: Optional[int] = None


# -- literal routes ---------------------------------------------------------

@router.get("/types")
async def types() -> list[dict]:
    return list_job_types()


@router.get("/queue")
async def queue() -> dict:
    return job_service.queue_status()


@router.get("")
async def list_jobs(status: Optional[str] = Query(None), type: Optional[str] = Query(None),
                    project_id: Optional[str] = Query(None),
                    limit: int = Query(200, ge=1, le=500)) -> list[dict]:
    return await job_service.list(status=status, type=type, project_id=project_id, limit=limit)


@router.post("", status_code=201)
async def submit(req: SubmitRequest) -> dict:
    return await job_service.submit(
        type=req.type, params=req.params, target_ref=req.target_ref,
        project_id=req.project_id, priority=req.priority, max_attempts=req.max_attempts)


# -- item -------------------------------------------------------------------

@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    j = await job_service.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@router.get("/{job_id}/progress")
async def progress(job_id: str) -> dict:
    p = await job_service.progress(job_id)
    if p is None:
        raise HTTPException(status_code=404, detail="job not found")
    return p


@router.get("/{job_id}/logs")
async def logs(job_id: str) -> dict:
    lg = await job_service.logs(job_id)
    if lg is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"id": job_id, "logs": lg}


@router.post("/{job_id}/cancel")
async def cancel(job_id: str) -> dict:
    return await job_service.cancel(job_id)


@router.post("/{job_id}/retry")
async def retry(job_id: str) -> dict:
    j = await job_service.retry(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="job not found")
    return j
