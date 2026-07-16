"""Runtime Registry API (RedForge V2, Phase 2.5).

List / register / resolve / unregister runnable checkpoints. Additive; delegates
to :mod:`app.runtime_registry`. Registered models are usable by the Playground and
Security Center through the existing Runtime Manager (their ``runtime_model`` is
passed to ``get_runtime().generate`` exactly like any model name).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.runtime_registry import runtime_registry

router = APIRouter(prefix="/api/registry", tags=["runtime-registry"])


class RegisterRequest(BaseModel):
    run_id: str
    step: int
    base_model: str = Field(..., min_length=1)
    provider: Optional[str] = None      # None → active runtime provider
    checkpoint_id: Optional[str] = None
    project_id: Optional[str] = None
    adapter_path: Optional[str] = None
    label: Optional[str] = None


@router.get("")
async def list_registered(
    db: AsyncSession = Depends(get_db),
    run_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
) -> list[dict]:
    return await runtime_registry.list(db, run_id=run_id, project_id=project_id)


@router.post("", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    return await runtime_registry.register_checkpoint(
        db, run_id=req.run_id, step=req.step, base_model=req.base_model,
        provider=(req.provider or settings.RUNTIME_PROVIDER).lower(),
        checkpoint_id=req.checkpoint_id, project_id=req.project_id,
        adapter_path=req.adapter_path, label=req.label,
    )


@router.get("/{registry_id}")
async def get_registered(registry_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    m = await runtime_registry.get(db, registry_id)
    if m is None:
        raise HTTPException(status_code=404, detail="registered model not found")
    return m


@router.delete("/{registry_id}")
async def unregister(registry_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not await runtime_registry.unregister(db, registry_id):
        raise HTTPException(status_code=404, detail="registered model not found")
    return {"unregistered": True, "id": registry_id}
