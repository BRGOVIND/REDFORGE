"""OpenAI Chat Completions family.

One base implements the ``/v1/chat/completions`` + ``/v1/models`` dialect; every
concrete provider that speaks it is a ~5-line subclass differing only in base
URL and auth. This single family already covers LM Studio, llama.cpp, vLLM,
OpenAI, Groq, and OpenRouter — adding another (Together, Fireworks, DeepSeek, …)
is one more subclass.
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

from app.config import settings
from app.runtime.providers.base import HttpProvider
from app.runtime.responses import GenerationResult


# ---------------------------------------------------------------------------
# Wire-format helpers (pure functions — trivially unit-testable)
# ---------------------------------------------------------------------------

def _parse_chat_completion(data: dict) -> tuple[str, Optional[str], Optional[int]]:
    """Extract (text, finish_reason, completion_tokens) from a chat completion."""
    choices = data.get("choices") or []
    text, finish = "", None
    if choices:
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        finish = choices[0].get("finish_reason")
    usage = (data.get("usage") or {}).get("completion_tokens")
    return text, finish, usage


def _parse_sse_line(line: str) -> Optional[dict]:
    """Adapt one OpenAI SSE line into the runtime's chunk shape.

    Returns ``{"response", "done", ...}`` (like Ollama's chunks) so
    :func:`app.runtime.stream.run_stream` consumes every provider uniformly.
    Non-data / keep-alive lines return ``None`` (skipped).
    """
    line = line.strip()
    if not line or not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if payload == "[DONE]":
        # Terminator sentinel — the real completion already arrived; skip so it
        # can't clobber the accumulated eval_count/done_reason.
        return None
    try:
        obj = json.loads(payload)
    except ValueError:
        return None

    choices = obj.get("choices") or []
    delta_text, finish = "", None
    if choices:
        delta = choices[0].get("delta") or {}
        delta_text = delta.get("content") or ""
        finish = choices[0].get("finish_reason")

    chunk: dict = {"response": delta_text, "done": bool(finish)}
    if finish:
        chunk["done_reason"] = finish
        usage = (obj.get("usage") or {}).get("completion_tokens")
        if usage is not None:
            chunk["eval_count"] = usage
    return chunk


def _normalize_models(data: dict) -> list[dict]:
    """Normalize ``/v1/models`` entries to a dict carrying ``name`` + any metadata.

    The runtime contract only requires ``name``; extra keys (created, owned_by,
    display_name, created_at, …) are preserved so the Model Manager's agnostic
    mapper can surface whatever a provider happens to expose.
    """
    entries = data.get("data") or data.get("models") or []
    out: list[dict] = []
    for entry in entries:
        name = entry.get("id") or entry.get("name")
        if not name:
            continue
        item = {"name": name}
        for key in (
            "size", "modified_at", "digest",       # Ollama-ish
            "created", "owned_by",                  # OpenAI
            "display_name", "created_at",           # Anthropic
            "description",
        ):
            if entry.get(key) is not None:
                item[key] = entry[key]
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider(HttpProvider):
    """Base for any server implementing the OpenAI REST subset we use."""

    name = "openai_compatible"
    label = "OpenAI-compatible"

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _chat_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    def _models_url(self) -> str:
        return f"{self.base_url}/v1/models"

    def _chat_body(self, model: str, prompt: str, *, stream: bool) -> dict:
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        self._ensure_ready()
        start = time.monotonic()
        try:
            async with self._client(settings.RUNTIME_READ_TIMEOUT) as client:
                resp = await client.post(self._chat_url(), json=self._chat_body(model, prompt, stream=False))
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 - normalize every transport error
            raise self._map_error(exc, model) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        text, finish, usage = _parse_chat_completion(data)
        return GenerationResult(
            model=model, text=text, latency_ms=latency_ms, eval_count=usage, done_reason=finish
        )

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        self._ensure_ready()
        try:
            async with self._client(settings.RUNTIME_READ_TIMEOUT) as client:
                async with client.stream(
                    "POST", self._chat_url(), json=self._chat_body(model, prompt, stream=True)
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        chunk = _parse_sse_line(line)
                        if chunk is not None:
                            yield chunk
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
        # OpenAI-style servers expose little per-model metadata; best-effort match
        # from the model list (mirrors Ollama's best-effort, never-raising contract).
        try:
            for entry in await self.list_models_raw():
                if entry.get("name") == model:
                    return entry
        except Exception:  # noqa: BLE001
            return None
        return None


# ---------------------------------------------------------------------------
# Concrete providers — local (no API key)
# ---------------------------------------------------------------------------

class LMStudioProvider(OpenAICompatibleProvider):
    """LM Studio's local server (default port 1234)."""

    name = "lmstudio"
    label = "LM Studio"
    default_base_url = "http://localhost:1234"


class LlamaCppProvider(OpenAICompatibleProvider):
    """llama.cpp's ``llama-server`` (default port 8080)."""

    name = "llamacpp"
    label = "llama.cpp"
    default_base_url = "http://localhost:8080"


class VLLMProvider(OpenAICompatibleProvider):
    """vLLM's OpenAI-compatible server (default port 8000; usually keyless)."""

    name = "vllm"
    label = "vLLM"
    default_base_url = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Concrete providers — hosted (API key required)
# ---------------------------------------------------------------------------

class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    label = "OpenAI"
    default_base_url = "https://api.openai.com"
    api_key_env = "OPENAI_API_KEY"


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    label = "Groq"
    default_base_url = "https://api.groq.com/openai"
    api_key_env = "GROQ_API_KEY"


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    label = "OpenRouter"
    default_base_url = "https://openrouter.ai/api"
    api_key_env = "OPENROUTER_API_KEY"
    extra_headers = {"HTTP-Referer": "https://redforge.local", "X-Title": "RedForge"}
