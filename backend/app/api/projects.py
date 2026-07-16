"""AI Studio — Projects API (RedForge V2, Phase 1).

Local workspace management: create / open / rename / delete / duplicate / recent.
Additive router; nothing in v1.2 depends on it. Delegates to
:mod:`app.projects.service` (pure persistence) — no runtime/provider logic here.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.projects import project_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    models: list[str] = []
    settings: dict[str, Any] = {}


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    models: Optional[list[str]] = None
    settings: Optional[dict[str, Any]] = None
    last_scan: Optional[dict[str, Any]] = None


class Project(BaseModel):
    id: str
    name: str
    description: str
    models: list[str]
    datasets: list[Any]
    settings: dict[str, Any]
    last_scan: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    opened_at: Optional[str] = None


@router.get("", response_model=list[Project])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    limit: Optional[int] = Query(None, ge=1, le=200, description="cap results (Recent Projects)"),
) -> list[Project]:
    return [Project(**p) for p in await project_service.list(db, limit=limit)]


@router.post("", response_model=Project, status_code=201)
async def create_project(req: ProjectCreate, db: AsyncSession = Depends(get_db)) -> Project:
    return Project(**await project_service.create(
        db, name=req.name, description=req.description,
        models=req.models, settings=req.settings,
    ))


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)) -> Project:
    p = await project_service.get(db, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Project(**p)


@router.patch("/{project_id}", response_model=Project)
async def update_project(project_id: str, req: ProjectUpdate, db: AsyncSession = Depends(get_db)) -> Project:
    p = await project_service.update(db, project_id, **req.model_dump(exclude_unset=True))
    if p is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Project(**p)


@router.post("/{project_id}/open", response_model=Project)
async def open_project(project_id: str, db: AsyncSession = Depends(get_db)) -> Project:
    """Bump ``opened_at`` so the project surfaces at the top of Recent Projects."""
    p = await project_service.touch(db, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Project(**p)


@router.post("/{project_id}/duplicate", response_model=Project, status_code=201)
async def duplicate_project(project_id: str, db: AsyncSession = Depends(get_db)) -> Project:
    p = await project_service.duplicate(db, project_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return Project(**p)


class DeleteResponse(BaseModel):
    deleted: bool
    id: str


@router.delete("/{project_id}", response_model=DeleteResponse)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)) -> DeleteResponse:
    if not await project_service.delete(db, project_id):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return DeleteResponse(deleted=True, id=project_id)
