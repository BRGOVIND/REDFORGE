"""Training Lab API (RedForge V2, Phase 2.2).

Local LoRA/QLoRA training as first-class runs. Additive router under
``/api/training``; isolated from runtime/security. Training executes through the
swappable Training Manager provider (simulation by default; Unsloth when the GPU
+ ML stack exist) — never a hardcoded backend.

Live progress is exposed two ways: an SSE stream (``/stream``) and a JSON
snapshot (``/progress``) for robust polling. Nothing is ever uploaded.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.continuous_security import continuous_security
from app.datasets_lab import dataset_service
from app.db.database import get_db
from app.foundation_models import foundation_model_service
from app.logging_config import get_logger
from app.runtime_registry import runtime_registry
from app.training import manager, training_service
from app.training.providers.base import TrainingConfig
from app.training.report import build_run_report
from app.training.runner import run_training
from app.training.store import progress_store

router = APIRouter(prefix="/api/training", tags=["training"])
logger = get_logger("training-api")

# A Hugging Face repo id is ``owner/name`` (alphanumeric/_/-/. only) with NO ``:`` tag.
# A runtime tag like ``qwen3:8b`` fails this — and must never reach a training provider.
_HF_REPO_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")


def _is_hf_repo(ref: str) -> bool:
    return bool(_HF_REPO_RE.match((ref or "").strip()))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TrainingParams(BaseModel):
    epochs: int = Field(3, ge=1, le=100)
    learning_rate: float = Field(2e-4, gt=0, le=1)
    batch_size: int = Field(2, ge=1, le=256)
    gradient_accumulation: int = Field(4, ge=1, le=256)
    rank: int = Field(16, ge=1, le=512)
    alpha: int = Field(32, ge=1, le=1024)
    dropout: float = Field(0.05, ge=0, le=0.9)
    scheduler: str = "cosine"
    optimizer: str = "adamw_8bit"
    warmup_steps: int = Field(10, ge=0, le=10000)
    max_seq_length: int = Field(2048, ge=8, le=131072)
    seed: int = 42
    validation_split: float = Field(0.1, ge=0, le=0.9)
    output_dir: str = ""


class LaunchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    base_model: str = Field(..., min_length=1)
    dataset_id: Optional[str] = None
    method: str = Field("lora", pattern="^(lora|qlora)$")
    backend: Optional[str] = None          # None → default (simulation)
    params: TrainingParams = TrainingParams()
    project_id: Optional[str] = None
    # Continuous Security: auto-evaluate each checkpoint with this attack profile.
    continuous_security: bool = False
    security_profile: str = Field("quick", pattern="^(quick|standard|full|custom)$")


class NotesRequest(BaseModel):
    notes: str


# ---------------------------------------------------------------------------
# Backends / metadata
# ---------------------------------------------------------------------------

# Availability probing imports torch/CUDA, which is multi-second on first call.
# Doing that on the event loop freezes every other endpoint (the cause of the
# frontend ECONNRESET on /api/models, /api/registry, …). So we run it in a worker
# thread and cache the result for the process lifetime (hardware/stack are static;
# `?refresh=true` re-probes after a driver/install change).
_backends_cache: Optional[dict] = None


def _compute_backends() -> dict:
    """The authoritative backend list + the default the UI must use.

    ``default`` is the *effective* backend: a user preference from Settings when
    it names a usable backend, otherwise auto-detection. The UI must never invent
    its own fallback — see the `ready` flag, which gates the Launch button.
    """
    available = manager.available_backends()
    usable = {b["name"] for b in available if b["available"]}
    auto = manager.default_backend()

    preferred = _preferred_backend()
    default = auto
    preference_note = ""
    if preferred and preferred in usable:
        default = preferred
    elif preferred and preferred not in usable:
        preference_note = (
            f"Settings prefers '{preferred}', which is not available on this machine; "
            f"using '{auto}' instead."
        )

    return {
        "backends": available,
        "default": default,
        "auto_detected": auto,
        "preferred": preferred,
        "preference_note": preference_note,
        # Explicit readiness signal so the client never guesses.
        "ready": True,
        "real_training_available": bool(usable - {"simulation"}),
    }


def _effective_backend() -> str:
    """The backend an 'auto' request resolves to — Settings preference if usable,
    otherwise auto-detection. Blocking (probes the stack); call via a thread."""
    preferred = _preferred_backend()
    if preferred:
        try:
            ok, _ = manager.get_provider(preferred).is_available()
        except manager.UnknownBackendError:
            ok = False
        if ok:
            return preferred
    return manager.default_backend()


def _backend_availability(name: str) -> tuple[bool, str]:
    """(available, reason) for a named backend. Blocking; call via a thread."""
    try:
        return manager.get_provider(name).is_available()
    except manager.UnknownBackendError as exc:
        return False, str(exc)


def _preferred_backend() -> Optional[str]:
    """The user's Settings choice, if any.

    Settings are authoritative: a value shown in the UI must affect behaviour.
    Read defensively — a settings failure must not take training down.
    """
    try:
        from app.settings import settings_service
        value = settings_service.get_sync("training.default_backend")
    except Exception:  # noqa: BLE001
        return None
    if not value or not isinstance(value, str):
        return None
    value = value.strip().lower()
    # "auto" means "no preference — auto-detect".
    if value in ("", "auto"):
        return None
    return value


@router.get("/backends")
async def backends(refresh: bool = Query(False)) -> dict:
    global _backends_cache
    if _backends_cache is None or refresh:
        if refresh:
            await asyncio.to_thread(manager.reset_availability_cache)
        _backends_cache = await asyncio.to_thread(_compute_backends)
    return _backends_cache


@router.get("/diagnostics")
async def training_diagnostics(backend: Optional[str] = Query(None),
                               refresh: bool = Query(False)) -> dict:
    """Structured, per-layer training diagnostics (PyTorch / CUDA / GPU /
    Transformers / PEFT / Unsloth / bitsandbytes). Computed off the event loop so
    the heavy torch import never blocks other requests.

    Without ``backend`` this describes the **real** training path — never the
    simulation backend, whose diagnostics are a single collapsed check and would
    not answer "why can't I train?".
    """
    if refresh:
        await asyncio.to_thread(manager.reset_availability_cache)
    try:
        return await asyncio.to_thread(manager.diagnostics, backend, refresh)
    except manager.UnknownBackendError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_backend",
                "message": str(exc),
                "fix": f"Use one of: {', '.join(exc.available)}.",
                "available_backends": exc.available,
            },
        ) from exc


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@router.get("")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=200),
) -> list[dict]:
    return await training_service.list(db, project_id=project_id, limit=limit)


def _training_enabled() -> bool:
    """Settings → Training → Enable training. Authoritative, not decorative."""
    try:
        from app.settings import settings_service
        return bool(settings_service.get_sync("training.enabled"))
    except Exception:  # noqa: BLE001 - a settings failure must not disable training
        return True


@router.post("/launch", status_code=202)
async def launch(req: LaunchRequest, db: AsyncSession = Depends(get_db)) -> dict:
    if not _training_enabled():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "training_disabled",
                "message": "Training is disabled in Settings.",
                "fix": "Enable it under Settings → Training → Enable training.",
            },
        )
    # An explicit "auto" (or nothing) means "resolve it for me"; anything else must
    # name a real, registered backend. Silently substituting simulation here would
    # produce a fake run that reports success — never acceptable.
    requested = (req.backend or "").strip().lower()
    if requested in ("", "auto"):
        backend = await asyncio.to_thread(_effective_backend)
    else:
        known = manager.known_backends()
        if requested not in known:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unknown_backend",
                    "message": f"Unknown training backend '{requested}'.",
                    "fix": f"Use one of: {', '.join(known)}, or 'auto'.",
                    "available_backends": known,
                },
            )
        backend = requested

    # A backend that exists but cannot run here is also a 400 — with the reason.
    available, reason = await asyncio.to_thread(_backend_availability, backend)
    if not available:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "backend_unavailable",
                "message": f"The '{backend}' training backend is not available on this machine.",
                "reason": reason,
                "fix": ("Install the training runtime (Training → Runtime), "
                        "or choose the Simulation backend."),
                "backend": backend,
            },
        )
    logger.info("[launch] backend=%s model=%s", backend, req.base_model)

    # --- Foundation Model resolution (the architectural seam) -----------------
    # A training provider must ONLY ever receive a Foundation Model identity (a
    # Hugging Face repo), NEVER a Runtime Model tag (e.g. an Ollama 'qwen3:8b').
    # Resolve the operator's selection through the Foundation Platform's existing
    # seam (ensure_foundation_for_base_model → provider-agnostic ModelResolution
    # Service). This makes the training providers runtime-agnostic and works for
    # every runtime (Ollama / llama.cpp / LM Studio / vLLM / OpenAI-compat / …) —
    # no hardcoded mappings, no per-provider branching here.
    logger.info("[model-id] launch: requested base_model=%r backend=%r", req.base_model, backend)
    foundation = await foundation_model_service.ensure_foundation_for_base_model(req.base_model)
    hf_repo = (foundation.get("hf_repo") or "").strip()
    logger.info("[model-id] resolved: runtime_ref=%r → foundation id=%s hf_repo=%r source=%s",
                req.base_model, foundation.get("id"), hf_repo, foundation.get("source"))
    if foundation.get("metadata", {}).get("unverified") or not _is_hf_repo(hf_repo):
        # Never hand a runtime tag to the provider — fail honestly instead.
        raise HTTPException(
            status_code=422,
            detail=(f"'{req.base_model}' is a runtime model that could not be resolved to a "
                    "Hugging Face foundation model. Resolve it on the Foundation Models page, "
                    "or enter a Hugging Face repo id (owner/name)."),
        )

    # --- Hardware pre-flight (Hardware Compatibility Engine) ------------------
    # Never let an impossible job reach a provider. For real GPU backends, estimate
    # the run's VRAM need for (model, strategy, hyperparameters) on the DETECTED GPU
    # BEFORE loading a single weight. Block if it cannot fit (and recommend a model
    # that does); apply the engine's safe defaults when it only fits tightly. This is
    # provider-agnostic and is the correct alternative to CPU offload.
    params = req.params.model_dump()
    hw_warnings: list[str] = []
    assessment_dict = None
    if backend not in ("simulation", "mock"):
        from app.hardware import hardware_service
        assessment = hardware_service.assess(
            base_model=hf_repo, strategy=req.method,
            max_seq_length=int(params.get("max_seq_length", 2048)),
            batch_size=int(params.get("batch_size", 2)),
            gradient_accumulation=int(params.get("gradient_accumulation", 4)),
            provider=backend)
        assessment_dict = assessment.to_dict()
        logger.info("[hardware] %r on %s → %s | %s", hf_repo,
                    assessment.gpu.name, assessment.verdict.value, assessment.reason)
        if not assessment.can_launch:
            # Impossible job — refuse before loading, with a concrete recommendation.
            raise HTTPException(status_code=422, detail={
                "error": "insufficient_gpu_memory",
                "message": assessment.reason,
                "recommended_models": assessment.recommended_models,
                "assessment": assessment_dict,
            })
        if assessment.verdict.value == "tight":
            # Fit it by reducing seq/batch (NOT by offloading) — the engine's safe
            # defaults, applied automatically so a first-time user need not tune.
            params.update(assessment.safe_defaults.as_overrides())
            hw_warnings = list(assessment.warnings)

    # Load dataset records (local) if a dataset is attached.
    records: list[Any] = []
    if req.dataset_id:
        records = await dataset_service._current_records(db, req.dataset_id) or []

    config_public = {
        "method": req.method, **params,
        "continuous_security": req.continuous_security,
        "security_profile": req.security_profile,
        # Provenance: the runtime selection and the foundation identity it resolved to.
        "runtime_ref": req.base_model,
        "foundation_model_id": foundation.get("id"),
        "hardware_assessment": assessment_dict,
        "hardware_warnings": hw_warnings,
    }
    # The run + the provider config carry the FOUNDATION identity (hf_repo), not the tag,
    # and the hardware-safe hyperparameters (``params``), not necessarily the requested.
    run = await training_service.create(
        db, name=req.name, base_model=hf_repo, dataset_id=req.dataset_id,
        method=req.method, backend=backend, config=config_public,
        output_dir=params.get("output_dir", ""), project_id=req.project_id,
    )

    cfg = TrainingConfig(
        base_model=hf_repo, method=req.method, dataset_records=records, **params,
    )

    # Continuous Security hook — register the checkpoint in the Runtime Registry,
    # then evaluate the *resolved runnable model* via the existing Security Center.
    # The registry falls back to the base model until real adapters can be hosted,
    # but the checkpoint identity + runtime linkage are recorded either way.
    # Non-blocking; never fatal to training.
    hook = None
    if req.continuous_security:
        run_id, base, prof = run["id"], req.base_model, req.security_profile
        eval_provider = settings.RUNTIME_PROVIDER.lower()

        async def hook(cp: dict) -> None:  # noqa: ANN001
            from app.db.database import AsyncSessionLocal
            step = cp.get("step", 0)
            registry_id, target = None, base
            try:
                async with AsyncSessionLocal() as db2:
                    reg = await runtime_registry.register_checkpoint(
                        db2, run_id=run_id, step=step, base_model=base,
                        provider=eval_provider, project_id=req.project_id,
                        label=f"Checkpoint (step {step})",
                    )
                    registry_id = reg["id"]
                    target = reg["runtime_model"]
            except Exception:  # noqa: BLE001 - registry failure must not stop training
                registry_id, target = None, base
            await continuous_security.schedule(
                run_id=run_id, step=step, target_model=target,
                checkpoint_id=None, profile=prof,
                runtime_id=registry_id, provider=eval_provider,
            )

    # Fire-and-forget background run (own DB session inside the runner).
    asyncio.create_task(run_training(run["id"], backend, cfg, checkpoint_hook=hook))
    return {"run": run, "backend": backend, "streaming": True,
            "continuous_security": req.continuous_security}


@router.get("/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    r = await training_service.get(db, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return r


@router.patch("/{run_id}/notes")
async def set_notes(run_id: str, req: NotesRequest, db: AsyncSession = Depends(get_db)) -> dict:
    r = await training_service.update_notes(db, run_id, req.notes)
    if r is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return r


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    progress_store.cancel(run_id)
    await training_service.set_status(db, run_id, "cancelled")
    return {"cancelled": True, "id": run_id}


@router.post("/{run_id}/pause")
async def pause_run(run_id: str, paused: bool = Query(True)) -> dict:
    ok = progress_store.pause(run_id, paused)
    if not ok:
        raise HTTPException(status_code=404, detail="run not active")
    return {"paused": paused, "id": run_id}


@router.delete("/{run_id}")
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not await training_service.delete(db, run_id):
        raise HTTPException(status_code=404, detail="training run not found")
    progress_store.discard(run_id)
    return {"deleted": True, "id": run_id}


# ---------------------------------------------------------------------------
# Live progress: snapshot (poll) + SSE (stream)
# ---------------------------------------------------------------------------

@router.get("/{run_id}/progress")
async def progress(run_id: str) -> dict:
    st = progress_store.get(run_id)
    if st is None:
        return {"run_id": run_id, "status": "idle", "latest": {}, "history": [], "logs": [], "paused": False}
    return st.snapshot()


@router.get("/{run_id}/stream")
async def stream(run_id: str) -> StreamingResponse:
    """Server-Sent Events stream of live progress until the run finishes."""

    async def gen():
        terminal = {"completed", "failed", "cancelled"}
        while True:
            st = progress_store.get(run_id)
            if st is None:
                yield f"data: {json.dumps({'status': 'idle'})}\n\n"
                return
            yield f"data: {json.dumps(st.snapshot(history_tail=1))}\n\n"
            if st.status in terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------

@router.get("/{run_id}/checkpoints")
async def list_checkpoints(run_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    cps = await training_service.checkpoints(db, run_id)
    if cps is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return cps


@router.get("/{run_id}/checkpoints/compare")
async def compare_checkpoints(
    run_id: str, a: int = Query(...), b: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = await training_service.compare_checkpoints(db, run_id, a, b)
    if r is None:
        raise HTTPException(status_code=404, detail="checkpoints not found")
    return r


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint(checkpoint_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not await training_service.delete_checkpoint(db, checkpoint_id):
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return {"deleted": True, "id": checkpoint_id}


# ---------------------------------------------------------------------------
# Continuous Security — per-checkpoint evaluation timeline + comparison
# ---------------------------------------------------------------------------

@router.get("/{run_id}/security")
async def security_timeline(run_id: str) -> dict:
    """The security timeline: one evaluation result per checkpoint, ordered by step."""
    return {"run_id": run_id, "timeline": await continuous_security.timeline(run_id)}


@router.get("/{run_id}/report")
async def training_report(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Composed engineering report — reuses existing data, stores nothing new."""
    report = await build_run_report(db, run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="training run not found")
    return report


@router.get("/{run_id}/security/compare")
async def security_compare(run_id: str, a: int = Query(...), b: int = Query(...)) -> dict:
    r = await continuous_security.compare(run_id, a, b)
    if r is None:
        raise HTTPException(status_code=404, detail="checkpoint security results not found")
    return r


@router.get("/security/queue")
async def security_queue() -> dict:
    """Continuous-security evaluation queue status (pending / running)."""
    return continuous_security.queue_status()


@router.post("/security/{job_id}/cancel")
async def security_cancel(job_id: str) -> dict:
    await continuous_security.cancel(job_id)
    return {"cancelled": True, "id": job_id}
