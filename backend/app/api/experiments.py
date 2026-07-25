"""Experiment Platform API (RedForge V3, Epic 4).

Additive router at ``/api/experiments``. Thin adapter over :mod:`app.experiments`.
Literal routes (``/compare``) precede ``/{experiment_id}``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.experiments import experiment_service

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class CreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    configuration: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    project_id: Optional[str] = None


class UpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None


class CloneRequest(BaseModel):
    name: Optional[str] = None
    include_notes: bool = False


class NoteRequest(BaseModel):
    body: str = Field(..., min_length=1)


# -- literal routes ---------------------------------------------------------

@router.get("/compare")
async def compare(ids: str = Query(..., description="comma-separated experiment ids")) -> dict:
    id_list = [i for i in ids.split(",") if i]
    if not id_list:
        raise HTTPException(status_code=400, detail="no ids provided")
    return await experiment_service.compare(id_list)


@router.get("")
async def list_experiments(project_id: Optional[str] = Query(None),
                           status: Optional[str] = Query(None)) -> list[dict]:
    return await experiment_service.list(project_id=project_id, status=status)


@router.post("", status_code=201)
async def create(req: CreateRequest) -> dict:
    return await experiment_service.create(
        name=req.name, description=req.description, configuration=req.configuration,
        tags=req.tags, project_id=req.project_id)


# -- item -------------------------------------------------------------------

@router.get("/{experiment_id}")
async def get_experiment(experiment_id: str) -> dict:
    e = await experiment_service.get(experiment_id)
    if e is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return e


@router.patch("/{experiment_id}")
async def update(experiment_id: str, req: UpdateRequest) -> dict:
    e = await experiment_service.update(experiment_id, **req.model_dump(exclude_none=True))
    if e is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return e


@router.delete("/{experiment_id}")
async def delete(experiment_id: str) -> dict:
    ok = await experiment_service.delete(experiment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"deleted": True, "id": experiment_id}


@router.post("/{experiment_id}/clone", status_code=201)
async def clone(experiment_id: str, req: CloneRequest) -> dict:
    e = await experiment_service.clone(experiment_id, include_notes=req.include_notes, name=req.name)
    if e is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return e


@router.post("/{experiment_id}/snapshot")
async def snapshot(experiment_id: str) -> dict:
    s = await experiment_service.snapshot(experiment_id)
    if s is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return s


@router.get("/{experiment_id}/timeline")
async def timeline(experiment_id: str) -> list[dict]:
    return await experiment_service.timeline(experiment_id)


@router.get("/{experiment_id}/artifacts")
async def artifacts(experiment_id: str) -> list[dict]:
    return await experiment_service.artifacts(experiment_id)


@router.get("/{experiment_id}/jobs")
async def jobs(experiment_id: str) -> list[dict]:
    return await experiment_service.jobs(experiment_id)


@router.get("/{experiment_id}/notes")
async def notes(experiment_id: str) -> list[dict]:
    return await experiment_service.notes(experiment_id)


@router.post("/{experiment_id}/notes", status_code=201)
async def add_note(experiment_id: str, req: NoteRequest) -> dict:
    n = await experiment_service.add_note(experiment_id, req.body)
    if n is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return n
