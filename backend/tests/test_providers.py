"""Tests for the multi-provider runtime.

The providers only implement provider-specific communication; the shared
RuntimeClient logic (queue/retry/metrics/cancel) is covered by test_runtime.py
against a FakeProvider. Here we verify each wire-format translation and the
config-driven selection — with a mocked HTTP transport, no real servers/keys.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import settings
from app.runtime import manager
from app.runtime.client import RuntimeClient
from app.runtime.errors import ProviderUnavailable
from app.runtime.providers import (
    AnthropicProvider,
    BUILTIN_PROVIDERS,
    GeminiProvider,
    GroqProvider,
    LlamaCppProvider,
    LMStudioProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    OpenRouterProvider,
    VLLMProvider,
    _normalize_models,
    _parse_chat_completion,
    _parse_sse_line,
)
from app.runtime.responses import StreamEventKind


def _install(monkeypatch, handler):
    """Route every httpx.AsyncClient through a MockTransport with ``handler``."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


# --- pure wire-format helpers (OpenAI family) ------------------------------

def test_parse_chat_completion_extracts_text_finish_usage():
    data = {
        "choices": [{"message": {"content": "hello world"}, "finish_reason": "stop"}],
        "usage": {"completion_tokens": 7},
    }
    assert _parse_chat_completion(data) == ("hello world", "stop", 7)


def test_parse_chat_completion_tolerates_missing_fields():
    assert _parse_chat_completion({}) == ("", None, None)


def test_parse_sse_line_token_and_done():
    assert _parse_sse_line('data: {"choices":[{"delta":{"content":"Hel"}}]}') == {
        "response": "Hel", "done": False
    }
    done = _parse_sse_line(
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"completion_tokens":2}}'
    )
    assert done == {"response": "", "done": True, "done_reason": "stop", "eval_count": 2}


def test_parse_sse_line_skips_noise_and_terminator():
    assert _parse_sse_line("") is None
    assert _parse_sse_line(": keep-alive") is None
    assert _parse_sse_line("data: [DONE]") is None


def test_normalize_models_maps_id_to_name():
    data = {"data": [{"id": "qwen3:8b"}, {"id": "llama3"}, {"nope": 1}]}
    assert _normalize_models(data) == [{"name": "qwen3:8b"}, {"name": "llama3"}]


# --- OpenAI-compatible family (LM Studio / llama.cpp / vLLM / OpenAI / …) ---

def _openai_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})
    if request.method == "POST" and request.url.path == "/v1/chat/completions":
        body = json.loads(request.content)
        if body.get("stream"):
            sse = (
                'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"completion_tokens":2}}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, content=sse.encode())
        return httpx.Response(200, json={
            "choices": [{"message": {"content": f"echo:{body['messages'][0]['content']}"},
                         "finish_reason": "stop"}],
            "usage": {"completion_tokens": 3},
        })
    return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def openai_server(monkeypatch):
    _install(monkeypatch, _openai_handler)


@pytest.mark.asyncio
async def test_lmstudio_generate(openai_server):
    r = await LMStudioProvider("http://x").generate("m1", "hi")
    assert r.text == "echo:hi"
    assert r.eval_count == 3
    assert r.done_reason == "stop"


@pytest.mark.asyncio
async def test_llamacpp_generate(openai_server):
    assert (await LlamaCppProvider("http://x").generate("m1", "hi")).text == "echo:hi"


@pytest.mark.asyncio
async def test_openai_generate_with_key(openai_server):
    assert (await OpenAIProvider("http://x", api_key="k").generate("m1", "hi")).text == "echo:hi"


@pytest.mark.asyncio
async def test_provider_list_models_and_health(openai_server):
    p = LMStudioProvider("http://x")
    assert await p.health() is True
    assert await p.list_models() == ["m1", "m2"]
    assert await p.show_model("m2") == {"name": "m2"}
    assert await p.show_model("ghost") is None


@pytest.mark.asyncio
async def test_openai_family_streams_through_runtime(openai_server):
    rc = RuntimeClient(LMStudioProvider("http://x"))
    events = [e async for e in rc.generate_stream("m1", "hi")]
    assert events[0].kind == StreamEventKind.TOKEN
    assert events[-1].kind == StreamEventKind.COMPLETION
    assert events[-1].result.text == "Hello"
    assert events[-1].result.eval_count == 2  # not clobbered by [DONE]


# --- Anthropic family (Messages API) ---------------------------------------

def _anthropic_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "claude-x"}]})
    if request.method == "POST" and request.url.path == "/v1/messages":
        body = json.loads(request.content)
        if body.get("stream"):
            sse = (
                'event: content_block_delta\n'
                'data: {"type":"content_block_delta","delta":{"text":"Hel"}}\n\n'
                'event: content_block_delta\n'
                'data: {"type":"content_block_delta","delta":{"text":"lo"}}\n\n'
                'event: message_delta\n'
                'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":2}}\n\n'
                'event: message_stop\n'
                'data: {"type":"message_stop"}\n\n'
            )
            return httpx.Response(200, content=sse.encode())
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "echo:hi"}],
            "stop_reason": "end_turn", "usage": {"output_tokens": 3},
        })
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_anthropic_generate(monkeypatch):
    _install(monkeypatch, _anthropic_handler)
    r = await AnthropicProvider("http://x", api_key="k").generate("claude-x", "hi")
    assert r.text == "echo:hi"
    assert r.eval_count == 3
    assert r.done_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_streams_through_runtime(monkeypatch):
    _install(monkeypatch, _anthropic_handler)
    rc = RuntimeClient(AnthropicProvider("http://x", api_key="k"))
    events = [e async for e in rc.generate_stream("claude-x", "hi")]
    assert events[-1].kind == StreamEventKind.COMPLETION
    assert events[-1].result.text == "Hello"
    assert events[-1].result.eval_count == 2
    assert events[-1].result.done_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_health_and_models(monkeypatch):
    _install(monkeypatch, _anthropic_handler)
    p = AnthropicProvider("http://x", api_key="k")
    assert await p.health() is True
    assert await p.list_models() == ["claude-x"]


# --- Gemini family (generateContent) ---------------------------------------

def _gemini_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "GET" and path.endswith("/v1beta/models"):
        return httpx.Response(200, json={"models": [{"name": "models/gemini-1.5-flash"}]})
    if request.method == "POST" and path.endswith(":generateContent"):
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "echo:hi"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"candidatesTokenCount": 3},
        })
    if request.method == "POST" and path.endswith(":streamGenerateContent"):
        sse = (
            'data: {"candidates":[{"content":{"parts":[{"text":"Hel"}]}}]}\n\n'
            'data: {"candidates":[{"content":{"parts":[{"text":"lo"}]},"finishReason":"STOP"}],'
            '"usageMetadata":{"candidatesTokenCount":2}}\n\n'
        )
        return httpx.Response(200, content=sse.encode())
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_gemini_generate(monkeypatch):
    _install(monkeypatch, _gemini_handler)
    r = await GeminiProvider("http://x", api_key="k").generate("gemini-1.5-flash", "hi")
    assert r.text == "echo:hi"
    assert r.eval_count == 3
    assert r.done_reason == "STOP"


@pytest.mark.asyncio
async def test_gemini_streams_through_runtime(monkeypatch):
    _install(monkeypatch, _gemini_handler)
    rc = RuntimeClient(GeminiProvider("http://x", api_key="k"))
    events = [e async for e in rc.generate_stream("gemini-1.5-flash", "hi")]
    assert events[-1].kind == StreamEventKind.COMPLETION
    assert events[-1].result.text == "Hello"
    assert events[-1].result.eval_count == 2


@pytest.mark.asyncio
async def test_gemini_list_models_strips_prefix(monkeypatch):
    _install(monkeypatch, _gemini_handler)
    assert await GeminiProvider("http://x", api_key="k").list_models() == ["gemini-1.5-flash"]


# --- auth gating (hosted providers) ----------------------------------------

@pytest.mark.asyncio
async def test_missing_api_key_raises_on_generate():
    with pytest.raises(ProviderUnavailable, match="API key not set"):
        await OpenAIProvider("http://x", api_key="").generate("gpt", "hi")


@pytest.mark.asyncio
async def test_missing_api_key_health_is_false():
    assert await AnthropicProvider("http://x", api_key="").health() is False


def test_openrouter_sets_attribution_headers():
    headers = OpenRouterProvider(api_key="k")._headers()
    assert headers["Authorization"] == "Bearer k"
    assert headers["X-Title"] == "RedForge"


def test_local_providers_need_no_key():
    assert LMStudioProvider().requires_api_key is False
    assert VLLMProvider().requires_api_key is False


# --- transport error mapping ------------------------------------------------

@pytest.mark.asyncio
async def test_generate_maps_connection_error_to_provider_unavailable(monkeypatch):
    class _Client(httpx.AsyncClient):
        async def post(self, *a, **k):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    with pytest.raises(ProviderUnavailable):
        await LlamaCppProvider("http://x").generate("m1", "hi")


# --- config-driven selection & registration --------------------------------

def test_registry_has_all_nine_providers():
    expected = {"ollama", "lmstudio", "llamacpp", "vllm", "openai",
                "anthropic", "gemini", "groq", "openrouter"}
    assert expected <= set(BUILTIN_PROVIDERS)
    assert expected <= set(manager.available_providers())


@pytest.mark.parametrize("name, cls", [
    ("ollama", None),
    ("lmstudio", LMStudioProvider),
    ("llamacpp", LlamaCppProvider),
    ("vllm", VLLMProvider),
    ("openai", OpenAIProvider),
    ("anthropic", AnthropicProvider),
    ("gemini", GeminiProvider),
    ("groq", GroqProvider),
    ("openrouter", OpenRouterProvider),
])
def test_build_provider_is_config_driven(monkeypatch, name, cls):
    monkeypatch.setattr(settings, "RUNTIME_PROVIDER", name)
    provider = manager._build_provider()
    assert provider.name == name
    if cls is not None:
        assert isinstance(provider, cls)


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(settings, "RUNTIME_PROVIDER", "nope")
    with pytest.raises(ValueError, match="unknown runtime provider"):
        manager._build_provider()


def test_register_provider_extends_registry(monkeypatch):
    class Custom(OpenAICompatibleProvider):
        name = "custom"

    manager.register_provider("custom", lambda: Custom("http://x"))
    try:
        monkeypatch.setattr(settings, "RUNTIME_PROVIDER", "custom")
        assert isinstance(manager._build_provider(), Custom)
    finally:
        manager._PROVIDERS.pop("custom", None)
