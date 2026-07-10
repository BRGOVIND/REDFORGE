"""Shared HTTP transport helpers for providers.

Error mapping lives here exactly once so every provider normalizes ``httpx``
failures identically. No provider re-implements this logic — they call
:func:`map_transport_error` with their own label and "unavailable" type.
"""
from __future__ import annotations

from typing import Type

import httpx

from app.runtime.errors import (
    ConnectionFailure,
    ModelNotFound,
    ProviderUnavailable,
    RuntimeLLMError,
)


def map_transport_error(
    exc: Exception,
    *,
    unavailable: Type[ProviderUnavailable] = ProviderUnavailable,
    label: str = "Provider",
    model: str = "",
) -> RuntimeLLMError:
    """Translate any transport exception into a stable runtime error.

    ``unavailable`` is the concrete "offline/unreachable" error to raise (e.g.
    ``OllamaUnavailable`` for Ollama); ``label`` names the provider in messages.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return unavailable(f"{label} is offline or unreachable")
    if isinstance(exc, httpx.TimeoutException):
        return ConnectionFailure(f"{label} request timed out")
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 404:
            return ModelNotFound(f"model '{model}' not found")
        return ProviderUnavailable(f"{label} returned HTTP {exc.response.status_code}")
    return ProviderUnavailable(f"{label} error: {exc}")
