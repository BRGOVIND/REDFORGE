"""Shared HTTP plumbing for network providers.

:class:`HttpProvider` holds everything the concrete providers have in common
*except the wire format*: base-URL resolution, API-key resolution, auth headers,
error mapping, the httpx client, and API-key-gated health. Each wire-format
family (OpenAI-compatible, Anthropic, Gemini, Ollama) subclasses this and adds
only its request building / response parsing.

Config convention (so adding a provider needs no ``config.py`` edits):
  * Base URL   → env ``REDFORGE_<NAME>_URL`` (falls back to ``default_base_url``).
  * API key    → env named by ``api_key_env`` (``None`` ⇒ no auth, e.g. local).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.config import settings
from app.runtime.client import Provider
from app.runtime.errors import ProviderUnavailable, RuntimeLLMError
from app.runtime.transport import map_transport_error


class HttpProvider(Provider):
    name = "http"
    label = "Provider"                       # used in error messages
    default_base_url = ""
    api_key_env: Optional[str] = None        # None ⇒ no API key required (local server)
    extra_headers: dict[str, str] = {}       # constant headers (e.g. OpenRouter attribution)

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = (base_url or self._env_base_url()).rstrip("/")
        self.api_key = api_key if api_key is not None else self._env_api_key()

    # -- config resolution ---------------------------------------------------

    def _env_base_url(self) -> str:
        return os.environ.get(f"REDFORGE_{self.name.upper()}_URL", self.default_base_url)

    def _env_api_key(self) -> Optional[str]:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    @property
    def requires_api_key(self) -> bool:
        return self.api_key_env is not None

    def _ensure_ready(self) -> None:
        """Raise a clear error before any network call if a required key is absent."""
        if self.requires_api_key and not self.api_key:
            raise ProviderUnavailable(f"{self.label} API key not set (set ${self.api_key_env})")

    # -- transport plumbing --------------------------------------------------

    def _auth_headers(self) -> dict:
        """Provider-specific auth headers. Override per wire format."""
        return {}

    def _headers(self) -> dict:
        return {**self.extra_headers, **self._auth_headers()}

    def _map_error(self, exc: Exception, model: str = "") -> RuntimeLLMError:
        return map_transport_error(
            exc, unavailable=ProviderUnavailable, label=self.label, model=model
        )

    def _client(self, read_timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(read_timeout, connect=settings.RUNTIME_CONNECT_TIMEOUT),
            headers=self._headers(),
        )

    # -- health (API-key gated; subclasses supply the probe) -----------------

    async def health(self) -> bool:
        if self.requires_api_key and not self.api_key:
            return False
        try:
            return await self._probe_health()
        except Exception:  # noqa: BLE001 - health is best-effort, never raises
            return False

    async def _probe_health(self) -> bool:
        raise NotImplementedError
