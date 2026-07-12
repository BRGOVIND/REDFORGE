"""First-run system checks for the onboarding / Setup page.

Provider-agnostic: every runtime fact comes from the **active provider** through
the Runtime Manager (``get_runtime``) and the provider abstraction — this module
never probes ``localhost:11434`` and never assumes Ollama. Setup guidance
(``setup_hint`` / ``docs_url``) is owned by the provider classes, so switching the
active runtime switches the guidance automatically.

Designed to be polled: each call is a bounded provider health probe plus a cheap
cached model list, so the wizard updates live as the runtime comes online.
"""
from __future__ import annotations

import platform

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Attack
from app.dataset import benchmark_loader
from app.health import health_service
from app.resources.resource_monitor import detect_gpu
from app.runtime.manager import get_runtime

router = APIRouter(prefix="/api/system", tags=["system"])

# Provider-agnostic starter models (only shown for providers that can pull).
RECOMMENDED_MODELS = ["llama3.2:3b", "llama3.1:8b", "mistral:7b", "qwen2.5:7b"]


def _check(key: str, label: str, status: str, detail: str = "", hint: str = "") -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail, "hint": hint}


async def _active_runtime() -> dict:
    """Probe the active provider through the shared runtime (never provider-specific).

    Returns provider metadata + live reachability + model list. All values come
    from the Runtime Manager / provider abstraction.
    """
    runtime = get_runtime()
    provider = runtime.provider
    online = False
    models: list[str] = []
    try:
        online = await provider.health()
    except Exception:  # noqa: BLE001 - health must never raise here
        online = False
    if online:
        try:
            models = await runtime.list_models(use_cache=False)
        except Exception:  # noqa: BLE001
            models = []
    return {
        "name": getattr(provider, "name", "runtime"),
        "label": getattr(provider, "label", "Runtime"),
        "base_url": getattr(provider, "base_url", None),
        "requires_api_key": bool(getattr(provider, "requires_api_key", False)),
        "api_key_present": bool(getattr(provider, "api_key", None)),
        "supports_pull": bool(provider.capabilities().get("supports_pull", False)),
        "docs_url": getattr(provider, "docs_url", "") or None,
        "setup_hint": getattr(provider, "setup_hint", "") or None,
        "reachable": online,
        "models": models,
    }


@router.get("/checks")
async def system_checks(
    db: AsyncSession = Depends(get_db),
    include_health: bool = Query(False, description="embed the full System Health Engine report"),
) -> dict:
    rt = await _active_runtime()
    checks: list[dict] = []

    # --- Runtime provider (active provider, via the Runtime Manager) -------
    label = rt["label"]
    if rt["reachable"]:
        checks.append(_check(
            "runtime_running", "Runtime Provider", "ok",
            detail=f"{label} reachable" + (f" · {rt['base_url']}" if rt["base_url"] else ""),
        ))
    elif rt["requires_api_key"] and not rt["api_key_present"]:
        checks.append(_check(
            "runtime_running", "Runtime Provider", "failed",
            detail=f"{label} API key not set", hint=rt["setup_hint"] or "",
        ))
    else:
        checks.append(_check(
            "runtime_running", "Runtime Provider", "failed",
            detail=f"{label} not reachable"
            + (f" at {rt['base_url']}" if rt["base_url"] else ""),
            hint=rt["setup_hint"] or "",
        ))

    # --- GPU (non-blocking) ----------------------------------------------
    gpu = detect_gpu()
    checks.append(_check(
        "gpu", "GPU Detected", "ok" if gpu.available else "warning",
        detail=gpu.name or "no GPU — evaluations will run on CPU",
    ))

    # --- Database initialized --------------------------------------------
    try:
        attack_count = (await db.execute(select(func.count(Attack.id)))).scalar_one()
        db_ok = True
    except Exception:
        attack_count = 0
        db_ok = False
    checks.append(_check(
        "database", "Database Ready", "ok" if db_ok else "failed",
        detail="database initialized" if db_ok else "database not reachable",
    ))

    # --- Attack dataset loaded -------------------------------------------
    try:
        bench_total = benchmark_loader.total_count()
    except Exception:
        bench_total = 0
    dataset_ok = attack_count > 0 and bench_total > 0
    checks.append(_check(
        "dataset", "Dataset Loaded", "ok" if dataset_ok else "failed",
        detail=f"{attack_count} attacks · {bench_total} benchmark cases",
    ))

    # --- Models available on the active provider -------------------------
    models = rt["models"]
    model_status = "ok" if models else ("warning" if rt["reachable"] else "failed")
    checks.append(_check(
        "models", "Models Available", model_status,
        detail=f"{len(models)} model(s)" if models else "no models available yet",
    ))

    ready = all(
        c["status"] == "ok"
        for c in checks
        if c["key"] in {"runtime_running", "database", "dataset", "models"}
    )

    # The full provider-agnostic Health Engine report, on demand.
    health = None
    if include_health:
        try:
            health = (await health_service.run()).model_dump()
        except Exception:  # noqa: BLE001
            health = None

    return {
        "ready": ready,
        "platform": platform.system(),
        "provider": {
            "name": rt["name"],
            "label": rt["label"],
            "base_url": rt["base_url"],
            "reachable": rt["reachable"],
            "requires_api_key": rt["requires_api_key"],
            "api_key_present": rt["api_key_present"],
            "supports_pull": rt["supports_pull"],
            "docs_url": rt["docs_url"],
            "setup_hint": rt["setup_hint"],
        },
        "checks": checks,
        "installed_models": models,
        "recommended_models": RECOMMENDED_MODELS if rt["supports_pull"] else [],
        "health": health,
    }
