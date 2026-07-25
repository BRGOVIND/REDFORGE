"""Artifact Registry API (RedForge V3, Epic 2).

Additive router at ``/api/artifacts``. Thin application-layer adapter over
:mod:`app.artifacts` — no business logic here. Literal routes precede
``/{artifact_id}`` so they are never shadowed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.artifacts import (
    artifact_lineage,
    artifact_query,
    artifact_registry,
    artifact_versions,
    list_artifact_types,
)
from app.artifacts.domain import ArtifactLocation

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class RegisterRequest(BaseModel):
    type: str = Field(..., min_length=1, max_length=60)
    name: str = Field(..., min_length=1, max_length=300)
    producer: str = ""
    project_id: Optional[str] = None
    description: str = ""
    file_path: Optional[str] = None            # file-backed location
    table: Optional[str] = None                # data-backed location
    row_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    parents: list[dict] = Field(default_factory=list)  # [{parent_id, relationship}]
    status: str = "draft"


class TagRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class VersionRequest(BaseModel):
    description: Optional[str] = None
    file_path: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


# -- literal routes ---------------------------------------------------------

@router.get("/types")
async def types() -> list[dict]:
    return list_artifact_types()


@router.get("")
async def search(type: Optional[str] = Query(None), status: Optional[str] = Query(None),
                 project_id: Optional[str] = Query(None), tag: Optional[str] = Query(None),
                 q: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=500)) -> list[dict]:
    return await artifact_query.search(type=type, status=status, project_id=project_id,
                                       tag=tag, query=q, limit=limit)


@router.post("", status_code=201)
async def register(req: RegisterRequest) -> dict:
    location = None
    if req.file_path:
        location = ArtifactLocation.file(req.file_path)
    elif req.table and req.row_id:
        location = ArtifactLocation.data(req.table, req.row_id)
    parents = [(p["parent_id"], p.get("relationship", "derived_from"))
               for p in req.parents if p.get("parent_id")]
    return await artifact_registry.register(
        type=req.type, name=req.name, location=location, producer=req.producer,
        project_id=req.project_id, description=req.description, tags=req.tags,
        metadata=req.metadata, parents=parents, status=req.status)


# -- item -------------------------------------------------------------------

@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str) -> dict:
    a = await artifact_registry.get(artifact_id)
    if a is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return a


@router.get("/{artifact_id}/lineage")
async def lineage(artifact_id: str) -> dict:
    lin = await artifact_lineage.lineage(artifact_id)
    if lin is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return lin


@router.get("/{artifact_id}/parents")
async def parents(artifact_id: str) -> list[dict]:
    return await artifact_lineage.parents(artifact_id)


@router.get("/{artifact_id}/children")
async def children(artifact_id: str) -> list[dict]:
    return await artifact_lineage.children(artifact_id)


@router.get("/{artifact_id}/versions")
async def versions(artifact_id: str) -> list[dict]:
    return await artifact_versions.history(artifact_id)


@router.post("/{artifact_id}/version", status_code=201)
async def create_version(artifact_id: str, req: VersionRequest) -> dict:
    location = ArtifactLocation.file(req.file_path) if req.file_path else None
    v = await artifact_versions.create_version(artifact_id, location=location,
                                               metadata=req.metadata, description=req.description)
    if v is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return v


@router.post("/{artifact_id}/publish")
async def publish(artifact_id: str) -> dict:
    a = await artifact_registry.publish(artifact_id)
    if a is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return a


@router.post("/{artifact_id}/tag")
async def tag(artifact_id: str, req: TagRequest) -> dict:
    a = await artifact_registry.tag(artifact_id, req.tags)
    if a is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return a


@router.post("/{artifact_id}/archive")
async def archive(artifact_id: str) -> dict:
    a = await artifact_registry.archive(artifact_id)
    if a is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return a


@router.post("/{artifact_id}/validate")
async def validate(artifact_id: str) -> dict:
    res = await artifact_registry.validate(artifact_id)
    if res is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return res


@router.delete("/{artifact_id}")
async def delete(artifact_id: str) -> dict:
    ok = await artifact_registry.delete(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found")
    return {"deleted": True, "id": artifact_id}
