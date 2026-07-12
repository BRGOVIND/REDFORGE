"""Ollama provider — the native (non-OpenAI) local runtime.

Talks to Ollama's own ``/api/generate`` / ``/api/tags`` / ``/api/show`` endpoints.
This is the reference provider; its behavior is unchanged from v1.0.
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

import httpx

from app.config import settings
from app.runtime.client import Provider
from app.runtime.errors import OllamaUnavailable, RuntimeLLMError
from app.runtime.responses import GenerationResult
from app.runtime.transport import map_transport_error


class OllamaProvider(Provider):
    name = "ollama"
    label = "Ollama"
    docs_url = "https://ollama.com/download"
    setup_hint = "Start Ollama with: ollama serve"

    # Ollama is the richest local provider: full metadata, context length via
    # /api/show, model deletion via /api/delete, and pull via /api/pull.
    supports_deletion = True
    supports_metadata = True
    supports_context_length = True
    supports_pull = True

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    def _timeout(self, read: float) -> httpx.Timeout:
        return httpx.Timeout(read, connect=settings.RUNTIME_CONNECT_TIMEOUT)

    @staticmethod
    def _map_error(exc: Exception, model: str = "") -> RuntimeLLMError:
        return map_transport_error(exc, unavailable=OllamaUnavailable, label="Ollama", model=model)

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout(settings.OLLAMA_TIMEOUT)) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 - normalize every transport error
            raise self._map_error(exc, model) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        return GenerationResult(
            model=model,
            text=data.get("response", ""),
            latency_ms=latency_ms,
            eval_count=data.get("eval_count"),
            done_reason=data.get("done_reason"),
        )

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout(settings.OLLAMA_TIMEOUT)) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        yield json.loads(line)
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def version(self) -> Optional[str]:
        """Ollama server version (optional capability, best-effort)."""
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                resp.raise_for_status()
                return resp.json().get("version")
        except Exception:  # noqa: BLE001
            return None

    async def list_models_raw(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TAGS_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc
        return data.get("models", [])

    async def show_model(self, model: str) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_SHOW_TIMEOUT) as client:
                resp = await client.post(f"{self.base_url}/api/show", json={"name": model})
                resp.raise_for_status()
                return resp.json()
        except Exception:  # noqa: BLE001 - metadata is best-effort
            return None

    async def pull_model(self, model: str):
        """Stream Ollama's /api/pull progress as raw dicts (status/total/completed).

        Pulls can take minutes; a long read timeout is used and each JSON line is
        yielded as it arrives so callers can report progress live."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=settings.RUNTIME_CONNECT_TIMEOUT)) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/pull",
                    json={"name": model, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield json.loads(line)
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc

    async def delete_model(self, model: str) -> bool:
        """Delete an installed model via Ollama's /api/delete. Raises on failure."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout(settings.OLLAMA_SHOW_TIMEOUT)) as client:
                resp = await client.request(
                    "DELETE", f"{self.base_url}/api/delete", json={"name": model}
                )
                resp.raise_for_status()
                return True
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc
