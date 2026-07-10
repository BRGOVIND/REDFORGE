"""Access point for the shared runtime.

Modules call ``get_runtime()`` — they never construct providers or import httpx.
The provider is chosen from config, so switching backends (or injecting a fake in
tests via ``set_runtime``) touches nothing else.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.config import settings
from app.runtime.client import Provider, RuntimeClient
from app.runtime.providers import BUILTIN_PROVIDERS

_runtime: Optional[RuntimeClient] = None

# Config-driven provider registry, seeded from the built-ins. Keys are the values
# REDFORGE_RUNTIME_PROVIDER accepts. Register more at runtime with
# ``register_provider`` without touching any selection/engine logic.
ProviderFactory = Callable[[], Provider]

_PROVIDERS: dict[str, ProviderFactory] = dict(BUILTIN_PROVIDERS)


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register (or override) a provider factory under ``name`` (case-insensitive)."""
    _PROVIDERS[name.lower()] = factory


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def build_provider(name: str) -> Provider:
    """Construct a registered provider by name (does not change the default)."""
    factory = _PROVIDERS.get(name.lower())
    if factory is None:
        raise ValueError(
            f"unknown runtime provider '{name}' (known: {available_providers()})"
        )
    return factory()


def _build_provider() -> Provider:
    return build_provider(settings.RUNTIME_PROVIDER)


def set_default_provider(name: str) -> str:
    """Switch the process-wide default provider and drop the cached runtime so the
    next ``get_runtime()`` rebuilds against it. Process-local (not persisted)."""
    key = name.lower()
    if key not in _PROVIDERS:
        raise ValueError(
            f"unknown runtime provider '{name}' (known: {available_providers()})"
        )
    settings.RUNTIME_PROVIDER = key
    reset_runtime()
    return key


def get_runtime() -> RuntimeClient:
    global _runtime
    if _runtime is None:
        _runtime = RuntimeClient(_build_provider())
    return _runtime


def set_runtime(runtime: Optional[RuntimeClient]) -> None:
    """Override the shared runtime (used by tests to inject a fake provider)."""
    global _runtime
    _runtime = runtime


def reset_runtime() -> None:
    set_runtime(None)
