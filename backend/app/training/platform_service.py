"""Training Platform — application service (RedForge V3, Epic 3).

The V3 training facade: create a configuration, estimate resources, launch a run
(which executes as a Job — never directly), and read runs/checkpoints/logs. Owns the
run lifecycle up to dispatch; the actual training runs in ``execution.py`` under the
Execution Platform. Depends on repository interfaces; never on SQLAlchemy, never on
Unsloth, never on the Runtime Engine.

Named ``platform_service`` to sit alongside (not replace) the legacy
``app/training/service.py`` — strangler-fig, additive.
"""
from __future__ import annotations

import os
from typing import Optional
from uuid import uuid4

from app.training import estimation, execution
from app.training.domain import (
    AdapterConfiguration,
    HyperparameterSet,
    TrainingConfiguration,
    TrainingRun,
    TrainingStatus,
)
from app.training.strategies import get_strategy, resolve_provider
from app.logging_config import get_logger

logger = get_logger("training-platform")


def _default_output_dir(run_id: str) -> str:
    return os.path.join(os.getcwd(), ".redforge", "training", run_id)


class TrainingPlatformService:
    def __init__(self, run_repo=None, checkpoint_repo=None, dataset_service=None) -> None:
        # Share execution's singletons by default so create/launch/read are coherent
        # (the Job handler uses execution._run_repo / _checkpoint_repo).
        self._runs = run_repo or execution._run_repo
        self._checkpoints = checkpoint_repo or execution._checkpoint_repo
        self._datasets = dataset_service

    def _dataset_svc(self):
        if self._datasets is not None:
            return self._datasets
        from app.datasets import dataset_platform
        return dataset_platform

    async def _resolve_base_model(self, foundation_model_id: Optional[str],
                                  base_model: Optional[str]) -> str:
        if base_model:
            return base_model
        if foundation_model_id:
            try:
                from app.foundation_models import foundation_model_service
                fm = await foundation_model_service.get(foundation_model_id)
                if fm:
                    return fm["hf_repo"]
            except Exception:  # noqa: BLE001
                pass
        return base_model or "unknown"

    async def _record_count(self, dataset_id: Optional[str]) -> int:
        if not dataset_id:
            return 0
        d = await self._dataset_svc().get(dataset_id)
        return (d or {}).get("statistics", {}).get("record_count", 0) if d else 0

    def _build_config(self, *, foundation_model_id, base_model, dataset_id, dataset_version,
                      strategy, provider, hyperparameters, adapter, strategy_params) -> TrainingConfiguration:
        return TrainingConfiguration(
            foundation_model_id=foundation_model_id, base_model=base_model,
            dataset_id=dataset_id, dataset_version=dataset_version,
            strategy=strategy, provider=resolve_provider(strategy, provider),
            hyperparameters=HyperparameterSet.from_dict(hyperparameters or {}),
            adapter=AdapterConfiguration(**{k: v for k, v in (adapter or {}).items()
                                            if k in ("rank", "alpha", "dropout")}),
            strategy_params=strategy_params or {})

    # -- estimate (wizard step 6, no run created) -----------------------------

    async def estimate(self, *, foundation_model_id=None, base_model=None, dataset_id=None,
                       strategy="lora", provider=None, hyperparameters=None, adapter=None) -> dict:
        base = await self._resolve_base_model(foundation_model_id, base_model)
        config = self._build_config(
            foundation_model_id=foundation_model_id, base_model=base, dataset_id=dataset_id,
            dataset_version=None, strategy=strategy, provider=provider,
            hyperparameters=hyperparameters, adapter=adapter, strategy_params=None)
        rc = await self._record_count(dataset_id)
        return estimation.estimate(config, record_count=rc).to_dict()

    # -- create / launch ------------------------------------------------------

    async def create(self, *, name, foundation_model_id=None, base_model=None, dataset_id=None,
                     dataset_version=None, strategy="lora", provider=None, hyperparameters=None,
                     adapter=None, strategy_params=None, project_id=None, experiment_id=None,
                     output_dir: Optional[str] = None) -> dict:
        base = await self._resolve_base_model(foundation_model_id, base_model)
        config = self._build_config(
            foundation_model_id=foundation_model_id, base_model=base, dataset_id=dataset_id,
            dataset_version=dataset_version, strategy=strategy, provider=provider,
            hyperparameters=hyperparameters, adapter=adapter, strategy_params=strategy_params)
        run_id = str(uuid4())
        rc = await self._record_count(dataset_id)
        run = TrainingRun(
            id=run_id, name=name, configuration=config, status=TrainingStatus.CREATED,
            estimate=estimation.estimate(config, record_count=rc), project_id=project_id,
            output_dir=output_dir or _default_output_dir(run_id))
        # experiment association rides in metrics (no schema change); launch reads it.
        if experiment_id:
            run.metrics = {**(run.metrics or {}), "experiment_id": experiment_id}
        await self._runs.add(run)
        logger.info("created v3 training run %s (%s/%s)", run_id, config.strategy, config.provider)
        return run.to_dict()

    async def launch(self, run_id: str) -> Optional[dict]:
        """Launch a created run as a Job. Never executes training inline."""
        run = await self._runs.get(run_id)
        if run is None:
            return None
        if run.status not in (TrainingStatus.CREATED, TrainingStatus.FAILED, TrainingStatus.CANCELLED):
            return {"error": f"run is {run.status.value}; only created/failed/cancelled can launch"}
        if not get_strategy(run.configuration.strategy).implemented:
            return {"error": f"strategy '{run.configuration.strategy}' is not yet runnable"}
        from app.jobs import job_service
        job = await job_service.submit(type="training", target_ref=run_id,
                                       project_id=run.project_id,
                                       experiment_id=(run.metrics or {}).get("experiment_id"),
                                       params={"run_id": run_id})
        run.status = TrainingStatus.QUEUED
        run.job_id = job["id"]
        await self._runs.update(run)
        return {"run": run.to_dict(), "job": job}

    # -- reads ----------------------------------------------------------------

    async def get(self, run_id: str) -> Optional[dict]:
        run = await self._runs.get(run_id)
        return run.to_dict() if run else None

    async def list(self, *, project_id=None) -> list[dict]:
        return [r.to_dict() for r in await self._runs.list(project_id=project_id)]

    async def checkpoints(self, run_id: str) -> list[dict]:
        return [c.to_dict() for c in await self._checkpoints.list(run_id)]

    async def logs(self, run_id: str) -> Optional[list[str]]:
        run = await self._runs.get(run_id)
        return run.logs if run else None

    async def cancel(self, run_id: str) -> Optional[dict]:
        run = await self._runs.get(run_id)
        if run is None:
            return None
        if run.job_id:
            from app.jobs import job_service
            await job_service.cancel(run.job_id)
        return {"cancelled": True, "id": run_id}

    async def delete(self, run_id: str) -> bool:
        return await self._runs.delete(run_id)


training_platform = TrainingPlatformService()
