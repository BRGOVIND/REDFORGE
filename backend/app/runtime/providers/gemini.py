"""Google Gemini provider — the ``generateContent`` wire format.

A third dialect (neither OpenAI nor Anthropic): per-model URLs
(``/v1beta/models/<model>:generateContent``), ``x-goog-api-key`` auth, and a
``contents``/``parts`` body. Shared plumbing comes from :class:`HttpProvider`.
"""
from __future__ import annotations

import json
import os
import time
from typing import AsyncIterator, Optional

from app.config import settings
from app.runtime.providers.base import HttpProvider
from app.runtime.responses import GenerationResult

_API_VERSION = "v1beta"


def _parse_gemini_chunk(obj: dict) -> dict:
    """Adapt a GenerateContentResponse (full or streamed) to the runtime chunk shape."""
    candidates = obj.get("candidates") or []
    text, finish = "", None
    if candidates:
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        text = "".join(p.get("text", "") for p in parts)
        finish = candidates[0].get("finishReason")
    usage = (obj.get("usageMetadata") or {}).get("candidatesTokenCount")
    chunk: dict = {"response": text, "done": bool(finish)}
    if finish:
        chunk["done_reason"] = finish
        if usage is not None:
            chunk["eval_count"] = usage
    return chunk


class GeminiProvider(HttpProvider):
    name = "gemini"
    label = "Gemini"
    default_base_url = "https://generativelanguage.googleapis.com"
    api_key_env = "GEMINI_API_KEY"
    docs_url = "https://aistudio.google.com/app/apikey"
    setup_hint = "Set your GEMINI_API_KEY environment variable"

    # The models list reports display name, description, and token limits.
    supports_metadata = True
    supports_context_length = True

    def _env_api_key(self) -> Optional[str]:
        # Accept the Google-standard var as a fallback.
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def _auth_headers(self) -> dict:
        return {"x-goog-api-key": self.api_key or "", "content-type": "application/json"}

    def _model_url(self, model: str, method: str) -> str:
        model_id = model[len("models/"):] if model.startswith("models/") else model
        return f"{self.base_url}/{_API_VERSION}/models/{model_id}:{method}"

    def _models_url(self) -> str:
        return f"{self.base_url}/{_API_VERSION}/models"

    @staticmethod
    def _body(prompt: str) -> dict:
        return {"contents": [{"parts": [{"text": prompt}]}]}

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        self._ensure_ready()
        start = time.monotonic()
        try:
            async with self._client(settings.RUNTIME_READ_TIMEOUT) as client:
                resp = await client.post(self._model_url(model, "generateContent"), json=self._body(prompt))
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        parsed = _parse_gemini_chunk(data)
        return GenerationResult(
            model=model, text=parsed["response"], latency_ms=latency_ms,
            eval_count=parsed.get("eval_count"), done_reason=parsed.get("done_reason"),
        )

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        self._ensure_ready()
        url = self._model_url(model, "streamGenerateContent") + "?alt=sse"
        try:
            async with self._client(settings.RUNTIME_READ_TIMEOUT) as client:
                async with client.stream("POST", url, json=self._body(prompt)) as resp:
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
                        yield _parse_gemini_chunk(obj)
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
        out: list[dict] = []
        for entry in data.get("models", []):
            raw = entry.get("name", "")
            model_id = raw[len("models/"):] if raw.startswith("models/") else raw
            if model_id:
                out.append(
                    {
                        "name": model_id,
                        "context_length": entry.get("inputTokenLimit"),
                        "output_token_limit": entry.get("outputTokenLimit"),
                        "display_name": entry.get("displayName"),
                        "description": entry.get("description"),
                        "version": entry.get("version"),
                    }
                )
        return out

    async def show_model(self, model: str) -> Optional[dict]:
        try:
            for entry in await self.list_models_raw():
                if entry.get("name") == model:
                    return entry
        except Exception:  # noqa: BLE001
            return None
        return None
