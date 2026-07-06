"""Access point for the shared runtime.

Modules call ``get_runtime()`` — they never construct providers or import httpx.
The provider is chosen from config, so switching backends (or injecting a fake in
tests via ``set_runtime``) touches nothing else.
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.runtime.client import OllamaProvider, Provider, RuntimeClient

_runtime: Optional[RuntimeClient] = None


def _build_provider() -> Provider:
    name = settings.RUNTIME_PROVIDER.lower()
    if name == "ollama":
        return OllamaProvider()
    # Future: "lmstudio", "llamacpp", "vllm", "openai" → return that Provider.
    raise ValueError(f"unknown runtime provider '{settings.RUNTIME_PROVIDER}'")


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
