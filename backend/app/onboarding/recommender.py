"""Hardware-aware runtime and model recommendations for onboarding.

Given the detected hardware and the live provider status, recommend the best
runtime to use and which models are a good fit. Everything is derived from
existing services:

  * hardware      → ``resources.resource_monitor.detect_resources`` + platform
  * providers     → ``runtime.management.provider_manager`` (Runtime Manager)
  * model sizing  → ``runtime.model_sizes`` (the same estimates the planner uses)

The functions are pure over their inputs (``recommend_runtime`` /
``recommend_models`` take plain data) so they are deterministic and testable
without touching hardware or the network.
"""
from __future__ import annotations

import platform
import sys
from typing import Optional

from app.resources.resource_monitor import ResourceSnapshot, detect_resources
from app.runtime.model_sizes import estimate_model_ram_mb

# Preferred order among *local* providers when several are available. Cloud
# providers are never auto-recommended (they need an API key and send data off
# the machine); onboarding is about getting a local runtime going.
LOCAL_PROVIDER_PREFERENCE = ["ollama", "lmstudio", "llamacpp", "vllm"]

# A small, curated catalog of good local target models across size tiers. Names
# are Ollama tags (the default, pull-capable provider). Each entry is annotated
# at request time with whether it fits the detected memory budget.
_MODEL_CATALOG = [
    {"name": "llama3.2:1b", "label": "Llama 3.2 1B", "params_b": 1.0,
     "note": "Tiny — runs on almost anything."},
    {"name": "llama3.2:3b", "label": "Llama 3.2 3B", "params_b": 3.0,
     "note": "Small and fast; a good first target."},
    {"name": "phi3:mini", "label": "Phi-3 Mini (3.8B)", "params_b": 3.8,
     "note": "Capable small model."},
    {"name": "mistral:7b", "label": "Mistral 7B", "params_b": 7.0,
     "note": "Strong general-purpose 7B."},
    {"name": "llama3.1:8b", "label": "Llama 3.1 8B", "params_b": 8.0,
     "note": "Well-rounded mid-size target."},
    {"name": "qwen2.5:14b", "label": "Qwen 2.5 14B", "params_b": 14.0,
     "note": "Larger; needs a capable machine."},
    {"name": "llama3.3:70b", "label": "Llama 3.3 70B", "params_b": 70.0,
     "note": "Large; high-VRAM or lots of RAM only."},
]

# Headroom so a recommendation leaves room for the OS and the app itself.
_MEMORY_HEADROOM_MB = 2000


def _memory_budget_mb(snapshot: ResourceSnapshot) -> tuple[Optional[int], str]:
    """The effective memory a model can use, and where it comes from.

    Prefer dedicated VRAM (fastest); otherwise available system RAM. Apple's
    unified memory is reported as GPU total, which is the right budget there too.
    """
    gpu = snapshot.gpu
    if gpu.available and gpu.total_mb:
        return gpu.total_mb, ("vram" if gpu.backend == "cuda" else "unified memory")
    if snapshot.ram_available_mb:
        return snapshot.ram_available_mb, "system RAM"
    return None, "unknown"


def recommend_runtime(providers: list[dict], default: str) -> dict:
    """Pick the best runtime from live provider infos (Runtime Manager shape).

    Rules, in order: a *running* local provider wins; else an *installed* one
    (registered + reachable base URL is irrelevant here — we use health);
    else fall back to the configured default with guidance to install it.
    """
    by_name = {p["name"]: p for p in providers}

    def _online(name: str) -> bool:
        h = by_name.get(name, {}).get("health") or {}
        return bool(h.get("online"))

    running = [n for n in LOCAL_PROVIDER_PREFERENCE if n in by_name and _online(n)]
    if running:
        choice = running[0]
        return {
            "provider": choice,
            "state": "running",
            "reason": f"{by_name[choice].get('label', choice)} is installed and running.",
            "action": None,
        }

    # None running — recommend the preferred registered local provider (default
    # first if it is local), and tell the user how to start it.
    ordered = ([default] if default in LOCAL_PROVIDER_PREFERENCE else []) + [
        n for n in LOCAL_PROVIDER_PREFERENCE if n != default
    ]
    for name in ordered:
        if name in by_name:
            return {
                "provider": name,
                "state": "not_running",
                "reason": f"{by_name[name].get('label', name)} is registered but not running.",
                "action": f"Start {name} (e.g. `ollama serve` for Ollama), then re-scan.",
            }
    return {
        "provider": default,
        "state": "missing",
        "reason": "No local runtime detected.",
        "action": "Install a local runtime such as Ollama (https://ollama.com/download).",
    }


def recommend_models(budget_mb: Optional[int], budget_source: str) -> dict:
    """Annotate the curated catalog with fit against the memory budget and pick
    the single best default (the largest model that fits with headroom)."""
    usable = None if budget_mb is None else max(0, budget_mb - _MEMORY_HEADROOM_MB)
    annotated = []
    best: Optional[str] = None
    for entry in _MODEL_CATALOG:
        need = estimate_model_ram_mb(entry["name"])
        fits = usable is None or need <= usable
        item = {
            "name": entry["name"],
            "label": entry["label"],
            "params_b": entry["params_b"],
            "estimated_ram_mb": need,
            "fits": bool(fits),
            "note": entry["note"],
            "recommended": False,
        }
        annotated.append(item)
        if fits:
            best = entry["name"]  # keep the largest fitting model

    for item in annotated:
        item["recommended"] = item["name"] == best

    return {
        "budget_mb": budget_mb,
        "budget_source": budget_source,
        "usable_mb": usable,
        "recommended": best,
        "models": annotated,
    }


def _hardware(snapshot: ResourceSnapshot) -> dict:
    v = sys.version_info
    gpu = snapshot.gpu
    return {
        "python_version": f"{v.major}.{v.minor}.{v.micro}",
        "python_ok": (v.major, v.minor) >= (3, 11),
        "platform": platform.system(),
        "cpu_count": snapshot.cpu_count,
        "ram_total_mb": snapshot.ram_total_mb,
        "ram_available_mb": snapshot.ram_available_mb,
        "gpu": {
            "available": gpu.available,
            "name": gpu.name,
            "vram_total_mb": gpu.total_mb,
            "backend": gpu.backend,
        },
    }


async def build_recommendations() -> dict:
    """Full onboarding recommendation payload: hardware + runtime + models."""
    from app.runtime.management import provider_manager

    snapshot = detect_resources()
    infos = await provider_manager.refresh_all()  # live provider health (reused)
    budget_mb, budget_source = _memory_budget_mb(snapshot)

    return {
        "hardware": _hardware(snapshot),
        "runtime": recommend_runtime(infos, provider_manager.default_name()),
        "models": recommend_models(budget_mb, budget_source),
    }
