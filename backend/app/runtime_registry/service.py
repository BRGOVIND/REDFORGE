"""Runtime Registry service — register / resolve / list runnable checkpoints.

Registration is provider-agnostic through :func:`_register_with_provider`, which
returns the runtime model name to run and whether it fell back to the base model.
The default implementation falls back for every provider (no adapter files exist
without a real GPU fine-tune); real Ollama/LM Studio/llama.cpp/vLLM adapter
hosting plugs in here later with **no** changes to callers.

``resolve()`` is what the Runtime Manager consumers call: registry id → a model
name they pass to ``get_runtime().generate(...)`` exactly as today.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RegisteredModel
from app.logging_config import get_logger

logger = get_logger("runtime-registry")

# Which providers can host a fine-tuned adapter as a runnable model *today*.
# All False for now (honest: requires real adapter files + provider wiring).
# Flip to True and implement the create step when real training lands.
PROVIDER_CAN_HOST_ADAPTER: dict[str, bool] = {
    "ollama": False,
    "lmstudio": False,
    "llamacpp": False,
    "vllm": False,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(m: RegisteredModel) -> dict:
    return {
        "id": m.id,
        "run_id": m.run_id,
        "checkpoint_id": m.checkpoint_id,
        "project_id": m.project_id,
        "label": m.label,
        "step": m.step,
        "base_model": m.base_model,
        "provider": m.provider,
        "runtime_model": m.runtime_model,
        "adapter_path": m.adapter_path,
        "fallback": bool(m.fallback),
        "status": m.status,
        "metadata": m.model_metadata or {},
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _register_with_provider(provider: str, base_model: str,
                            adapter_path: Optional[str]) -> tuple[str, bool, dict]:
    """(runtime_model, fell_back, metadata). Extension point for real adapter
    hosting. Falls back to the base model when the provider can't host an adapter
    or no adapter file exists — the checkpoint identity is still registered."""
    can_host = PROVIDER_CAN_HOST_ADAPTER.get(provider.lower(), False)
    if can_host and adapter_path:
        # Real path (future): create the provider-side adapter model here and
        # return its name. Not reachable until a provider flips to True.
        return f"{base_model}+adapter", False, {"hosted_adapter": True}  # pragma: no cover
    reason = ("provider cannot host adapters yet" if not can_host
              else "no adapter file (simulation / base-model evaluation)")
    return base_model, True, {"fallback_reason": reason}


class RuntimeRegistry:
    async def register_checkpoint(
        self, db: AsyncSession, *, run_id: str, step: int, base_model: str,
        provider: str, checkpoint_id: Optional[str] = None,
        project_id: Optional[str] = None, adapter_path: Optional[str] = None,
        label: Optional[str] = None,
    ) -> dict:
        """Register a checkpoint as a runnable model. Idempotent per (run, step).
        Never raises into training — returns the record (possibly a fallback)."""
        reg_id = f"ckpt-{run_id[:8]}-step-{step}"
        existing = await db.get(RegisteredModel, reg_id)
        if existing is not None:
            return _to_dict(existing)

        runtime_model, fell_back, meta = _register_with_provider(provider, base_model, adapter_path)
        rec = RegisteredModel(
            id=reg_id, run_id=run_id, checkpoint_id=checkpoint_id, project_id=project_id,
            label=label or f"Checkpoint (step {step})", step=step, base_model=base_model,
            provider=provider, runtime_model=runtime_model, adapter_path=adapter_path,
            fallback=1 if fell_back else 0, status="registered", model_metadata=meta,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return _to_dict(rec)

    async def resolve(self, db: AsyncSession, registry_id: str) -> Optional[str]:
        """Registry id → the model name the Runtime Manager should run."""
        m = await db.get(RegisteredModel, registry_id)
        return m.runtime_model if m else None

    async def get(self, db: AsyncSession, registry_id: str) -> Optional[dict]:
        m = await db.get(RegisteredModel, registry_id)
        return _to_dict(m) if m else None

    async def list(self, db: AsyncSession, *, run_id: Optional[str] = None,
                   project_id: Optional[str] = None) -> list[dict]:
        stmt = select(RegisteredModel).where(RegisteredModel.status == "registered") \
            .order_by(RegisteredModel.created_at)
        if run_id is not None:
            stmt = stmt.where(RegisteredModel.run_id == run_id)
        if project_id is not None:
            stmt = stmt.where(RegisteredModel.project_id == project_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [_to_dict(m) for m in rows]

    async def unregister(self, db: AsyncSession, registry_id: str) -> bool:
        m = await db.get(RegisteredModel, registry_id)
        if m is None:
            return False
        m.status = "unregistered"
        await db.commit()
        return True


runtime_registry = RuntimeRegistry()
