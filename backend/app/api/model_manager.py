"""Model Manager API — browse and manage models across all providers.

Additive, provider-agnostic endpoints layered on top of the existing runtime.
The catalog returns *basic* metadata (cheap, one list call per provider);
*extended* metadata is loaded only via the per-model detail endpoint. Nothing
here duplicates model discovery or runtime logic — it delegates to
:mod:`app.runtime.model_catalog`, which reuses ``RuntimeClient`` and providers.

Existing ``GET /api/models`` and ``POST /api/models/{model}/ping`` are untouched.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.runtime.errors import RuntimeLLMError
from app.runtime.model_catalog import UnsupportedCapability, model_catalog

router = APIRouter(prefix="/api/models", tags=["model-manager"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class Capabilities(BaseModel):
    supports_delete: bool
    supports_metadata: bool
    supports_context_length: bool
    supports_streaming: bool
    supports_embeddings: bool
    supports_pull: bool = False


class BasicModel(BaseModel):
    name: str
    provider: str
    provider_label: str
    size: Optional[int] = None
    quantization: Optional[str] = None
    family: Optional[str] = None
    modified_at: Optional[str] = None
    digest: Optional[str] = None
    status: str
    capabilities: Capabilities


class ProviderGroup(BaseModel):
    provider: str
    label: str
    online: bool
    healthy: bool
    can_delete: bool
    capabilities: Capabilities
    error: Optional[str] = None
    model_count: int
    models: list[BasicModel]


class ModelCatalogResponse(BaseModel):
    providers: list[ProviderGroup]
    total: int
    default: str


class ModelDetail(BasicModel):
    # Extended (on-demand) metadata — all optional / provider-dependent.
    context_length: Optional[int] = None
    parameter_count: Optional[str] = None
    architecture: Optional[str] = None
    template: Optional[str] = None
    license: Optional[str] = None
    families: Optional[list[str]] = None
    tokenizer: Optional[str] = None
    modelfile: Optional[str] = None
    stop_tokens: list[str] = []
    provider_metadata: dict[str, Any] = {}


class DeleteResponse(BaseModel):
    deleted: bool
    provider: str
    name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/catalog", response_model=ModelCatalogResponse)
async def get_catalog() -> ModelCatalogResponse:
    """All installed models, grouped by provider, with basic metadata + health."""
    return ModelCatalogResponse(**await model_catalog.catalog())


@router.get("/detail", response_model=ModelDetail)
async def get_model_detail(
    provider: str = Query(..., description="provider key, e.g. 'ollama'"),
    name: str = Query(..., description="model name (may contain ':' or '/')"),
) -> ModelDetail:
    """Full (basic + extended) metadata for one model. Loaded on demand."""
    try:
        detail = await model_catalog.detail(provider, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'")
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found on '{provider}'")
    return ModelDetail(**detail)


@router.delete("/instance", response_model=DeleteResponse)
async def delete_model(
    provider: str = Query(...),
    name: str = Query(...),
) -> DeleteResponse:
    """Delete an installed model, if the provider supports deletion."""
    try:
        await model_catalog.delete(provider, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'")
    except UnsupportedCapability as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeLLMError as exc:
        status = exc.http_status if exc.http_status in (404, 503, 504) else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc
    return DeleteResponse(deleted=True, provider=provider.lower(), name=name)
