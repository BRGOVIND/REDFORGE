"""Anthropic provider — the Messages API wire format.

Not OpenAI-compatible: different endpoint (``/v1/messages``), auth (``x-api-key``
+ ``anthropic-version``), request shape (``max_tokens`` required), and SSE event
protocol. It reuses all shared plumbing from :class:`HttpProvider` and only
implements Anthropic-specific request building / response parsing.
"""
from __future__ import annotations

import json
import os
import time
from typing import AsyncIterator, Optional

from app.config import settings
from app.runtime.providers.base import HttpProvider
from app.runtime.providers.openai_compat import _normalize_models
from app.runtime.responses import GenerationResult

_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(HttpProvider):
    name = "anthropic"
    label = "Anthropic"
    default_base_url = "https://api.anthropic.com"
    api_key_env = "ANTHROPIC_API_KEY"

    # The models list reports display names / creation dates.
    supports_metadata = True

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 max_tokens: Optional[int] = None) -> None:
        super().__init__(base_url, api_key)
        self.max_tokens = max_tokens or int(
            os.environ.get("REDFORGE_ANTHROPIC_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
        )

    def _auth_headers(self) -> dict:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _messages_url(self) -> str:
        return f"{self.base_url}/v1/messages"

    def _models_url(self) -> str:
        return f"{self.base_url}/v1/models"

    def _body(self, model: str, prompt: str, *, stream: bool) -> dict:
        return {
            "model": model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        self._ensure_ready()
        start = time.monotonic()
        try:
            async with self._client(settings.RUNTIME_READ_TIMEOUT) as client:
                resp = await client.post(self._messages_url(), json=self._body(model, prompt, stream=False))
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = (data.get("usage") or {}).get("output_tokens")
        return GenerationResult(
            model=model, text=text, latency_ms=latency_ms,
            eval_count=usage, done_reason=data.get("stop_reason"),
        )

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        self._ensure_ready()
        out_tokens: Optional[int] = None
        stop_reason: Optional[str] = None
        try:
            async with self._client(settings.RUNTIME_READ_TIMEOUT) as client:
                async with client.stream(
                    "POST", self._messages_url(), json=self._body(model, prompt, stream=True)
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        try:
                            obj = json.loads(payload)
                        except ValueError:
                            continue
                        kind = obj.get("type")
                        if kind == "content_block_delta":
                            text = (obj.get("delta") or {}).get("text") or ""
                            if text:
                                yield {"response": text, "done": False}
                        elif kind == "message_delta":
                            usage = obj.get("usage") or {}
                            if usage.get("output_tokens") is not None:
                                out_tokens = usage["output_tokens"]
                            reason = (obj.get("delta") or {}).get("stop_reason")
                            if reason:
                                stop_reason = reason
                        elif kind == "message_stop":
                            done: dict = {"response": "", "done": True}
                            if stop_reason:
                                done["done_reason"] = stop_reason
                            if out_tokens is not None:
                                done["eval_count"] = out_tokens
                            yield done
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc

    async def _probe_health(self) -> bool:
        async with self._client(settings.RUNTIME_METADATA_TIMEOUT) as client:
            resp = await client.get(self._models_url())
            return resp.status_code == 200

    async def list_models_raw(self) -> list[dict]:
        self._ensure_ready()
        try:
            async with self._client(settings.RUNTIME_METADATA_TIMEOUT) as client:
                resp = await client.get(self._models_url())
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc
        return _normalize_models(data)

    async def show_model(self, model: str) -> Optional[dict]:
        try:
            for entry in await self.list_models_raw():
                if entry.get("name") == model:
                    return entry
        except Exception:  # noqa: BLE001
            return None
        return None
