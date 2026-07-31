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
# auto-selects a real training provider when one is actually usable.
FALLBACK_BACKEND = "simulation"
# Preference order when auto-detecting; first available wins.
#   unsloth  — in-process; source installs that already have the ML stack
#   managed  — subprocess against the managed training runtime (the packaged app)
#   simulation — always available, never silently substituted (see get_provider)
_AUTO_ORDER = ["unsloth", "managed", "simulation"]


class UnknownBackendError(ValueError):
    """Raised for a backend name that is not registered.

    Deliberately loud. This used to fall through to the simulation provider,
    which meant a typo produced a *fake* run that reported success — the worst
    possible failure mode for a training platform.
    """

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(
            f"unknown training backend '{name}'. Available: {', '.join(available)}"
        )


def register_provider(name: str, factory: ProviderFactory) -> None:
    _PROVIDERS[name.lower()] = factory


def known_backends() -> list[str]:
    return sorted(_PROVIDERS)


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


# NOTE: a module constant named DEFAULT_BACKEND used to live here, always equal to
# "simulation" and one letter away from the auto-detecting default_backend().
# It had no callers and was a trap, so it is gone. Use default_backend().


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
    """Resolve a backend by name. ``None`` auto-detects.

    Raises :class:`UnknownBackendError` for an unregistered name — it must never
    silently degrade to simulation.
    """
    key = (name or default_backend()).lower()
    factory = _PROVIDERS.get(key)
    if factory is None:
        raise UnknownBackendError(key, known_backends())
    return factory()


def diagnostics(name: str | None = None, refresh: bool = False) -> dict:
    """Structured, per-layer diagnostics for a backend (default: the real training
    backend, ``unsloth``). Drives the Training Lab diagnostics panel so the UI shows
    the exact failing dependency instead of a collapsed message."""
    key = (name or default_backend()).lower()
    factory = _PROVIDERS.get(key)
    if factory is None:
        raise UnknownBackendError(key, known_backends())
    return factory().diagnose(refresh=refresh)


def reset_availability_cache() -> None:
    """Clear cached availability/diagnostics (hardware or install changed, or tests
    switching simulated environments). Never raises."""
    for factory in _PROVIDERS.values():
        try:
            prov = factory()
            if hasattr(type(prov), "_diag_cache"):
                type(prov)._diag_cache = None
        except Exception:  # noqa: BLE001
            pass
