"""Training Platform API (RedForge V3, Epic 3).

Additive router at ``/api/training-platform`` (distinct from the legacy
``/api/training``). Thin adapter over :mod:`app.training.platform_service`. Training
is launched as a Job — never executed inline. Literal routes precede ``/{run_id}``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.training.platform_service import training_platform
from app.training.strategies import list_strategies

router = APIRouter(prefix="/api/training-platform", tags=["training-platform"])


class EstimateRequest(BaseModel):
    foundation_model_id: Optional[str] = None
    base_model: Optional[str] = None
    dataset_id: Optional[str] = None
    strategy: str = "lora"
    provider: Optional[str] = None
    hyperparameters: dict = Field(default_factory=dict)
    adapter: dict = Field(default_factory=dict)


class CreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    foundation_model_id: Optional[str] = None
    base_model: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_version: Optional[int] = None
    strategy: str = "lora"
    provider: Optional[str] = None
    hyperparameters: dict = Field(default_factory=dict)
    adapter: dict = Field(default_factory=dict)
    strategy_params: dict = Field(default_factory=dict)
    project_id: Optional[str] = None
    experiment_id: Optional[str] = None


@router.get("/strategies")
async def strategies() -> list[dict]:
    return list_strategies()


@router.get("/providers")
async def providers() -> list[dict]:
    """The V3 training providers with availability + dev-only flag. Simulation/mock
    are dev-only and never offered as production options."""
    from app.training import manager
    from app.training.execution import _register_transformers_provider
    _register_transformers_provider()
    out = []
    for name in ("unsloth", "transformers", "simulation"):
        factory = manager._PROVIDERS.get(name)
        if factory is None:
            continue
        prov = factory()
        ok, reason = prov.is_available()
        out.append({"name": name, "label": getattr(prov, "label", name),
                    "available": ok, "reason": reason,
                    "dev_only": name in ("simulation", "mock")})
    return out


@router.post("/estimate")
async def estimate(req: EstimateRequest) -> dict:
    return await training_platform.estimate(**req.model_dump())


@router.get("")
async def list_runs(project_id: Optional[str] = Query(None)) -> list[dict]:
    return await training_platform.list(project_id=project_id)


@router.post("", status_code=201)
async def create(req: CreateRequest) -> dict:
    return await training_platform.create(**req.model_dump())


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict:
    r = await training_platform.get(run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return r


@router.post("/{run_id}/launch", status_code=202)
async def launch(run_id: str) -> dict:
    res = await training_platform.launch(run_id)
    if res is None:
        raise HTTPException(status_code=404, detail="training run not found")
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.get("/{run_id}/checkpoints")
async def checkpoints(run_id: str) -> list[dict]:
    return await training_platform.checkpoints(run_id)


@router.get("/{run_id}/logs")
async def logs(run_id: str) -> dict:
    lg = await training_platform.logs(run_id)
    if lg is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return {"id": run_id, "logs": lg}


@router.post("/{run_id}/cancel")
async def cancel(run_id: str) -> dict:
    res = await training_platform.cancel(run_id)
    if res is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return res


@router.delete("/{run_id}")
async def delete(run_id: str) -> dict:
    ok = await training_platform.delete(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="training run not found")
    return {"deleted": True, "id": run_id}
