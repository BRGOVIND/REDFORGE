"""Runtime Manager API — inspect and manage the multi-provider runtime.

Read/refresh/select over the provider registry. All model traffic still flows
through :class:`~app.runtime.client.RuntimeClient`; these endpoints only expose
status and let the operator pick the default provider. Nothing here duplicates
runtime logic — it delegates to :mod:`app.runtime.management`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.runtime.management import provider_manager

router = APIRouter(prefix="/api/providers", tags=["providers"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HealthSnapshot(BaseModel):
    name: str
    online: bool
    healthy: bool
    version: Optional[str] = None
    model_count: Optional[int] = None
    models: list[str] = []
    base_url: Optional[str] = None
    latency_ms: Optional[float] = None
    checked_at: Optional[str] = None
    error: Optional[str] = None


class ProviderInfo(BaseModel):
    name: str
    label: str
    is_default: bool
    base_url: Optional[str] = None
    requires_api_key: bool
    api_key_env: Optional[str] = None
    api_key_present: bool
    health: Optional[HealthSnapshot] = None


class ProvidersResponse(BaseModel):
    default: str
    providers: list[ProviderInfo]


class SetDefaultRequest(BaseModel):
    name: str


class SetDefaultResponse(BaseModel):
    default: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """Installed providers + current default (fast; uses cached health, if any)."""
    return ProvidersResponse(
        default=provider_manager.default_name(),
        providers=provider_manager.list_infos(),
    )


@router.post("/refresh", response_model=ProvidersResponse)
async def refresh_providers() -> ProvidersResponse:
    """Live-probe every provider (health/version/models) and return fresh status."""
    infos = await provider_manager.refresh_all()
    return ProvidersResponse(default=provider_manager.default_name(), providers=infos)


@router.post("/default", response_model=SetDefaultResponse)
async def set_default_provider(req: SetDefaultRequest) -> SetDefaultResponse:
    """Select the process default provider (rebuilds the shared runtime lazily)."""
    try:
        return SetDefaultResponse(default=provider_manager.set_default(req.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{name}", response_model=ProviderInfo)
async def get_provider(name: str) -> ProviderInfo:
    """Details for one provider (static info + last cached health)."""
    try:
        return ProviderInfo(**provider_manager.info(name))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{name}'")


@router.post("/{name}/test", response_model=HealthSnapshot)
async def test_provider(name: str) -> HealthSnapshot:
    """Live-test a single provider connection and return the fresh snapshot."""
    try:
        return HealthSnapshot(**await provider_manager.check(name))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{name}'")
