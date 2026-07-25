"""Discovered Runtime Models API (RedForge V3, Epic 4.5).

Additive router at ``/api/runtime-models``. Surfaces the runtime models RedForge
has discovered locally, their runtime availability, and their resolution state —
and lets the operator resolve the ambiguous ones. Thin adapter over the
:class:`DiscoveryService`; no business logic here.

RuntimeModel and FoundationModel are separate identities (Constitution §5.4): this
router is about *runtime availability + resolution*, distinct from the Foundation
registry at ``/api/foundation-models``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.foundation_models import discovery_service

router = APIRouter(prefix="/api/runtime-models", tags=["runtime-models"])


class ResolveRuntimeRequest(BaseModel):
    hf_repo: Optional[str] = None  # explicit identity; omit to adopt the top candidate


@router.get("")
async def list_runtime_models(provider: Optional[str] = Query(None),
                              resolution: Optional[str] = Query(None),
                              available: Optional[bool] = Query(None)) -> list[dict]:
    """List discovered runtime models (filter by provider / resolution / availability)."""
    return await discovery_service.list_tracked(
        provider=provider, resolution=resolution, available=available)


@router.get("/unresolved")
async def list_unresolved() -> list[dict]:
    """Available runtime models that need an operator decision to resolve."""
    return await discovery_service.list_unresolved()


@router.get("/{runtime_model_id}")
async def get_runtime_model(runtime_model_id: str) -> dict:
    m = await discovery_service.get_tracked(runtime_model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="runtime model not found")
    return m


@router.post("/{runtime_model_id}/resolve")
async def resolve_runtime_model(runtime_model_id: str, req: ResolveRuntimeRequest) -> dict:
    """Resolve a runtime model to a Foundation identity — adopting the top candidate,
    or the explicit ``hf_repo`` when the operator knows what it is. Registers the
    Foundation Model and links it."""
    result = await discovery_service.resolve_one(runtime_model_id, hf_repo=req.hf_repo)
    if result is None:
        raise HTTPException(status_code=404, detail="runtime model not found")
    return result
