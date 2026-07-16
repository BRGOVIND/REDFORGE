"""Training Manager — the swappable-provider registry.

Mirrors the Runtime Manager pattern: providers register once, selection is by
name from config/request, and nothing else in the app constructs a provider
directly. Unsloth is never hardcoded outside its provider.
"""
from __future__ import annotations

from typing import Callable

from app.training.providers import BUILTIN_PROVIDERS
from app.training.providers.base import TrainingProvider

ProviderFactory = Callable[[], TrainingProvider]

_PROVIDERS: dict[str, ProviderFactory] = {
    name: (lambda cls=cls: cls()) for name, cls in BUILTIN_PROVIDERS.items()
}

# Simulation is the guaranteed fallback (zero ML deps). ``default_backend()``
# auto-selects the real Unsloth provider when a CUDA GPU + the ML stack exist.
FALLBACK_BACKEND = "simulation"
# Preference order when auto-detecting; first available wins.
_AUTO_ORDER = ["unsloth", "simulation"]


def register_provider(name: str, factory: ProviderFactory) -> None:
    _PROVIDERS[name.lower()] = factory


def default_backend() -> str:
    """Auto-detect the best available backend: real training if the GPU + ML
    stack are present, otherwise the simulation. Never raises."""
    for name in _AUTO_ORDER:
        factory = _PROVIDERS.get(name)
        if factory is None:
            continue
        try:
            ok, _ = factory().is_available()
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            return name
    return FALLBACK_BACKEND


# Backwards-compatible alias (existing callers referenced DEFAULT_BACKEND).
DEFAULT_BACKEND = FALLBACK_BACKEND


def available_backends() -> list[dict]:
    """Every registered backend with its availability (drives the wizard)."""
    out = []
    for name in sorted(_PROVIDERS):
        p = _PROVIDERS[name]()
        ok, reason = p.is_available()
        out.append({"name": name, "label": getattr(p, "label", name),
                    "available": ok, "reason": reason})
    return out


def get_provider(name: str | None = None) -> TrainingProvider:
    key = (name or default_backend()).lower()
    factory = _PROVIDERS.get(key) or _PROVIDERS[FALLBACK_BACKEND]
    return factory()
