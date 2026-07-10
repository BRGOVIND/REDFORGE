"""First-run system checks for the onboarding wizard.

Reports, cross-platform, whether every dependency RedForge needs is in place:
Ollama installed + running + reachable, models pulled, GPU present, database
initialized, and the attack dataset loaded. Designed to be polled — each call is
fast (short Ollama timeout) so the wizard can update statuses live.
"""
from __future__ import annotations

import platform
import shutil

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

RECOMMENDED_MODELS = ["qwen3:8b", "gemma", "llama3", "mistral"]
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"

# status values: "ok" | "warning" | "failed"


def _check(key: str, label: str, status: str, detail: str = "", hint: str = "") -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail, "hint": hint}


def _start_hint() -> str:
    system = platform.system()
    if system == "Linux":
        return "systemctl start ollama   (or: ollama serve)"
    return "ollama serve"


async def _ollama_tags() -> tuple[bool, list[str]]:
    """(reachable, model names) — fresh (cache-bypassed) so the wizard reacts
    immediately when Ollama starts or a model is pulled."""
    try:
        models = await get_runtime().list_models(use_cache=False)
        return True, models
    except Exception:
        return False, []


@router.get("/checks")
async def system_checks(
    db: AsyncSession = Depends(get_db),
    include_health: bool = Query(False, description="embed the full System Health Engine report"),
) -> dict:
    checks: list[dict] = []

    # --- Ollama installed -------------------------------------------------
    ollama_path = shutil.which("ollama")
    installed = ollama_path is not None
    checks.append(
        _check(
            "ollama_installed",
            "Ollama Installed",
            "ok" if installed else "failed",
            detail=ollama_path or "not found on PATH",
            hint="" if installed else OLLAMA_DOWNLOAD_URL,
        )
    )

    # --- Ollama running / reachable + models -----------------------------
    reachable, models = await _ollama_tags()
    checks.append(
        _check(
            "ollama_running",
            "Ollama Running",
            "ok" if reachable else "failed",
            detail="localhost:11434" if reachable else "not reachable on localhost:11434",
            hint="" if reachable else _start_hint(),
        )
    )

    # --- GPU (non-blocking) ----------------------------------------------
    gpu = detect_gpu()
    checks.append(
        _check(
            "gpu",
            "GPU Detected",
            "ok" if gpu.available else "warning",
            detail=gpu.name or "no GPU — evaluations will run on CPU",
        )
    )

    # --- Database initialized --------------------------------------------
    try:
        attack_count = (await db.execute(select(func.count(Attack.id)))).scalar_one()
        db_ok = True
    except Exception:
        attack_count = 0
        db_ok = False
    checks.append(
        _check(
            "database",
            "SQLite Ready",
            "ok" if db_ok else "failed",
            detail="database initialized" if db_ok else "database not reachable",
        )
    )

    # --- Attack dataset loaded -------------------------------------------
    try:
        bench_total = benchmark_loader.total_count()
    except Exception:
        bench_total = 0
    dataset_ok = attack_count > 0 and bench_total > 0
    checks.append(
        _check(
            "dataset",
            "Dataset Loaded",
            "ok" if dataset_ok else "failed",
            detail=f"{attack_count} attacks · {bench_total} benchmark cases",
        )
    )

    # --- Models installed (warning, not blocking install, but needed to run) --
    model_status = "ok" if models else ("warning" if reachable else "failed")
    checks.append(
        _check(
            "models",
            "Models Installed",
            model_status,
            detail=f"{len(models)} model(s)" if models else "no models pulled yet",
        )
    )

    ready = all(
        c["status"] == "ok"
        for c in checks
        if c["key"] in {"ollama_installed", "ollama_running", "database", "dataset", "models"}
    )

    # Consume the centralized System Health Engine on demand: the onboarding keys
    # above stay Ollama-specific (this is the Ollama wizard) and the endpoint stays
    # cheap to poll; pass ?include_health=true to embed the full provider-agnostic
    # report (or call GET /api/health directly). Best-effort; never blocks.
    health = None
    if include_health:
        try:
            health = (await health_service.run()).model_dump()
        except Exception:  # noqa: BLE001
            health = None

    return {
        "ready": ready,
        "platform": platform.system(),
        "checks": checks,
        "installed_models": models,
        "recommended_models": RECOMMENDED_MODELS,
        "ollama_download_url": OLLAMA_DOWNLOAD_URL,
        "health": health,
    }
