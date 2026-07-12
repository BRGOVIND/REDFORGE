"""Runtime management service — the read/refresh layer over the provider registry.

This is pure orchestration on top of the existing runtime. It lists registered
providers and probes their health / version / models **through the Provider
interface** — it never re-implements transport, queue, retries, metrics, or
cancellation (all of which remain in :class:`~app.runtime.client.RuntimeClient`).

The default provider is always queried via :func:`get_runtime` so the shared
``RuntimeClient`` stays the single source of truth; non-default providers are
built on demand purely to report status.

Each probe result is cached in memory so the UI can show a "last health check"
timestamp without hammering backends on every render.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.runtime import manager
from app.runtime.client import Provider
from app.runtime.errors import RuntimeLLMError
from app.runtime.manager import get_runtime


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderManager:
    def __init__(self) -> None:
        # name -> last health snapshot (dict). In-memory only.
        self._cache: dict[str, dict] = {}

    # -- default / selection ------------------------------------------------

    def default_name(self) -> str:
        return settings.RUNTIME_PROVIDER.lower()

    def set_default(self, name: str) -> str:
        return manager.set_default_provider(name)

    def is_known(self, name: str) -> bool:
        return name.lower() in manager._PROVIDERS

    # -- static (no network) ------------------------------------------------

    def _static(self, name: str) -> dict:
        provider = manager.build_provider(name)
        caps = provider.capabilities() if hasattr(provider, "capabilities") else {}
        return {
            "name": name,
            "label": getattr(provider, "label", name),
            "is_default": name == self.default_name(),
            "base_url": getattr(provider, "base_url", None),
            "requires_api_key": bool(getattr(provider, "requires_api_key", False)),
            "api_key_env": getattr(provider, "api_key_env", None),
            "api_key_present": bool(getattr(provider, "api_key", None)),
            "docs_url": getattr(provider, "docs_url", "") or None,
            "setup_hint": getattr(provider, "setup_hint", "") or None,
            "supports_pull": bool(caps.get("supports_pull", False)),
            "health": self._cache.get(name),
        }

    def list_infos(self) -> list[dict]:
        return [self._static(name) for name in manager.available_providers()]

    def info(self, name: str) -> dict:
        key = name.lower()
        if not self.is_known(key):
            raise KeyError(key)
        return self._static(key)

    # -- live probes --------------------------------------------------------

    def _provider_for(self, name: str) -> Provider:
        """Default provider comes from the shared runtime; others are built ad hoc."""
        if name == self.default_name():
            return get_runtime().provider
        return manager.build_provider(name)

    async def _version(self, provider: Provider) -> Optional[str]:
        """Optional provider capability — duck-typed, never required by the ABC."""
        fn = getattr(provider, "version", None)
        if fn is None:
            return None
        try:
            return await fn()
        except Exception:  # noqa: BLE001
            return None

    async def _list_models(self, name: str, provider: Provider) -> list[str]:
        # Route the default through the shared RuntimeClient (its cache/logging).
        if name == self.default_name():
            return await get_runtime().list_models()
        return await provider.list_models()

    async def check(self, name: str) -> dict:
        key = name.lower()
        if not self.is_known(key):
            raise KeyError(key)
        provider = self._provider_for(key)

        start = time.monotonic()
        online = False
        error: Optional[str] = None
        try:
            online = await provider.health()
        except Exception as exc:  # noqa: BLE001 - health must never raise here
            error = str(exc)
        latency_ms = round((time.monotonic() - start) * 1000, 1)

        version = await self._version(provider)

        models: list[str] = []
        model_count: Optional[int] = None
        if online:
            try:
                models = await self._list_models(key, provider)
                model_count = len(models)
            except RuntimeLLMError as exc:
                error = error or exc.message
            except Exception as exc:  # noqa: BLE001
                error = error or str(exc)

        snapshot = {
            "name": key,
            "online": bool(online),
            "healthy": bool(online) and error is None,
            "version": version,
            "model_count": model_count,
            "models": models,
            "base_url": getattr(provider, "base_url", None),
            "latency_ms": latency_ms,
            "checked_at": _utcnow_iso(),
            "error": error,
        }
        self._cache[key] = snapshot
        return snapshot

    async def refresh_all(self) -> list[dict]:
        names = manager.available_providers()
        # Probe concurrently; timeouts are bounded by each provider's client.
        await asyncio.gather(*(self.check(n) for n in names), return_exceptions=True)
        return [self._static(n) for n in names]


# Process-wide singleton (management state only; no runtime logic).
provider_manager = ProviderManager()
