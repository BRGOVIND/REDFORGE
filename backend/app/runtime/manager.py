"""Access point for the shared runtime.

Modules call ``get_runtime()`` — they never construct providers or import httpx.
The provider is chosen from config, so switching backends (or injecting a fake in
tests via ``set_runtime``) touches nothing else.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.config import settings
from app.network_policy import is_strict, LOCAL_RUNTIME_PROVIDERS, require_provider
from app.runtime.client import Provider, RuntimeClient
from app.runtime.providers import BUILTIN_PROVIDERS

_runtime: Optional[RuntimeClient] = None
_named_runtimes: dict[str, RuntimeClient] = {}

# Config-driven provider registry, seeded from the built-ins. Keys are the values
# REDFORGE_RUNTIME_PROVIDER accepts. Register more at runtime with
# ``register_provider`` without touching any selection/engine logic.
ProviderFactory = Callable[[], Provider]

_PROVIDERS: dict[str, ProviderFactory] = dict(BUILTIN_PROVIDERS)


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register (or override) a provider factory under ``name`` (case-insensitive)."""
    _PROVIDERS[name.lower()] = factory
    _named_runtimes.pop(name.lower(), None)


def available_providers() -> list[str]:
    names = _PROVIDERS
    return sorted(n for n in names if not is_strict() or n in LOCAL_RUNTIME_PROVIDERS)


def build_provider(name: str) -> Provider:
    """Construct a registered provider by name (does not change the default)."""
    key = name.lower()
    factory = _PROVIDERS.get(key)
    if factory is None:
        raise ValueError(
            f"unknown runtime provider '{name}' (known: {available_providers()})"
        )
    require_provider(key)
    provider = factory()
    require_provider(key, base_url=getattr(provider, "base_url", None))
    return provider


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
    require_provider(key)
    build_provider(key)  # validate configured endpoint before switching defaults
    settings.RUNTIME_PROVIDER = key
    reset_runtime()
    return key


def get_runtime() -> RuntimeClient:
    global _runtime
    require_provider(settings.RUNTIME_PROVIDER)
    if _runtime is None:
        _runtime = RuntimeClient(_build_provider())
    require_provider(_runtime.provider.name, base_url=getattr(_runtime.provider, "base_url", None))
    return _runtime


def get_runtime_for(name: str) -> RuntimeClient:
    """Select a registered adapter without mutating the process-wide default."""
    key = name.lower()
    require_provider(key)
    if key not in _named_runtimes:
        _named_runtimes[key] = RuntimeClient(build_provider(key))
    provider = _named_runtimes[key].provider
    require_provider(key, base_url=getattr(provider, "base_url", None))
    return _named_runtimes[key]


def set_runtime(runtime: Optional[RuntimeClient]) -> None:
    """Override the shared runtime (used by tests to inject a fake provider)."""
    global _runtime
    _runtime = runtime


def reset_runtime() -> None:
    set_runtime(None)
    _named_runtimes.clear()
