"""Foundation Model Platform API (RedForge V3, Epic 1).

Additive router mounted at ``/api/foundation-models``. Exposes the new Foundation
Platform without touching any existing endpoint. Delegates entirely to
:mod:`app.foundation_models`; contains no business logic (the application layer is
a thin adapter — Constitution §4.2).

Route order: literal paths (``/discover``, ``/resolve``, ``/catalog``) are declared
before the parameterized ``/{model_id}`` so they are never shadowed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.foundation_models import discovery_service, foundation_model_service

router = APIRouter(prefix="/api/foundation-models", tags=["foundation-models"])


# ---------------------------------------------------------------------------
# Schemas (application-layer request/response only)
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    hf_repo: str = Field(..., min_length=1, max_length=300)
    revision: Optional[str] = None
    architecture: Optional[str] = None
    parameter_count: Optional[int] = None
    format: str = "safetensors"
    quantization: str = "none"
    source: str = "hf_hub"
    license: Optional[str] = None
    cache_path: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ResolveRequest(BaseModel):
    runtime_ref: str = Field(..., min_length=1, max_length=300)


class CacheRequest(BaseModel):
    cache_path: str = Field(..., min_length=1, max_length=500)


class EnsureRequest(BaseModel):
    base_model: str = Field(..., min_length=1, max_length=300)


# ---------------------------------------------------------------------------
# Literal routes (declared before /{model_id})
# ---------------------------------------------------------------------------

@router.get("/discover")
async def discover() -> list[dict]:
    """Propose foundation-model candidates from the runtime models already
    installed. Read-only; nothing is registered. Offline-honest ([] if unreachable)."""
    return await foundation_model_service.discover()


@router.post("/resolve")
async def resolve(req: ResolveRequest) -> dict:
    """Resolve a runtime model to candidate foundation identities (confidence-scored)."""
    result = await foundation_model_service.resolve(req.runtime_ref)
    return result.to_dict()


@router.post("/discover")
async def discover_and_register() -> dict:
    """Run automatic discovery (Epic 4.5): scan installed runtime models, resolve
    each via ModelResolutionService, and auto-register the confidently-resolved ones
    as Foundation Models. Idempotent — never creates duplicates. Returns a summary."""
    return await discovery_service.run_discovery()


@router.post("/sync")
async def sync_runtime_models() -> dict:
    """Reconcile Foundation Models with the current runtime state (Epic 4.5): register
    newly-installed models, and mark vanished ones unavailable (Foundation identities
    are never deleted). Same idempotent pipeline as discover."""
    return await discovery_service.run_discovery()


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@router.get("")
async def list_models(status: Optional[str] = Query(None),
                      source: Optional[str] = Query(None),
                      limit: int = Query(200, ge=1, le=500)) -> list[dict]:
    return await foundation_model_service.list(status=status, source=source, limit=limit)


@router.post("", status_code=201)
async def register(req: RegisterRequest) -> dict:
    return await foundation_model_service.register(**req.model_dump())


@router.post("/ensure", status_code=201)
async def ensure_for_base_model(req: EnsureRequest) -> dict:
    """Compatibility seam: resolve/register a foundation model for a legacy
    ``base_model`` string. Exists for Training to adopt later; does not modify
    Training. Exposed so the seam is exercisable and testable end-to-end."""
    return await foundation_model_service.ensure_foundation_for_base_model(req.base_model)


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

@router.get("/{model_id}")
async def get_model(model_id: str) -> dict:
    m = await foundation_model_service.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="foundation model not found")
    return m


@router.get("/{model_id}/status")
async def get_status(model_id: str) -> dict:
    m = await foundation_model_service.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="foundation model not found")
    return {"id": m["id"], "status": m["status"], "is_local": m["is_local"],
            "cache_path": m["cache_path"], "checksum": m["checksum"]}


@router.get("/{model_id}/runtimes")
async def get_runtimes(model_id: str) -> list[dict]:
    """Reverse lineage: runtime models derived from this foundation model (honest —
    empty until the Export pipeline records real derivations in a later epic)."""
    return await foundation_model_service.runtimes_for(model_id)


@router.post("/{model_id}/sync")
async def sync_model(model_id: str) -> dict:
    m = await foundation_model_service.sync(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail="foundation model not found")
    return m


@router.post("/{model_id}/cache")
async def cache_model(model_id: str, req: CacheRequest) -> dict:
    m = await foundation_model_service.cache(model_id, req.cache_path)
    if m is None:
        raise HTTPException(status_code=404, detail="foundation model not found")
    return m


@router.delete("/{model_id}")
async def delete_model(model_id: str) -> dict:
    ok = await foundation_model_service.delete(model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="foundation model not found")
    return {"deleted": True, "id": model_id}
