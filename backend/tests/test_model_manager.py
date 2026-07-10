"""Tests for the Model Manager (provider-agnostic catalog + detail + delete).

A rich fake provider is registered and made default so metadata mapping, the
capability system, and deletion are deterministic without real backends.
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.runtime import manager
from app.runtime.client import Provider
from app.runtime.model_catalog import (
    _parse_stop_tokens,
    _unix_to_iso,
    to_basic,
    to_extended,
)
from app.runtime.responses import GenerationResult

_MODELS = {
    "m-8b": {
        "name": "m-8b", "size": 4_700_000_000, "digest": "sha256:abc",
        "modified_at": "2026-07-01T00:00:00Z",
        "details": {"parameter_size": "8B", "quantization_level": "Q4_K_M",
                    "family": "llama", "families": ["llama"], "format": "gguf"},
    },
    "m-1b": {
        "name": "m-1b", "size": 900_000_000,
        "details": {"parameter_size": "1B", "quantization_level": "Q8_0"},
    },
}

_SHOW = {
    "license": "MIT License",
    "modelfile": "FROM m-8b",
    "template": "{{ .Prompt }}",
    "parameters": 'stop "<|im_end|>"\nstop "<|user|>"',
    "details": {"parameter_size": "8B", "quantization_level": "Q4_K_M", "families": ["llama"]},
    "model_info": {"general.architecture": "llama", "llama.context_length": 8192,
                   "tokenizer.ggml.model": "gpt2"},
}


class FakeCatalogProvider(Provider):
    name = "fakecat"
    label = "FakeCat"
    supports_deletion = True
    supports_metadata = True
    supports_context_length = True

    base_url = "http://fakecat"
    deleted: list[str] = []

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        return GenerationResult(model, "ok", 1)

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        yield {"response": "ok", "done": True}

    async def health(self) -> bool:
        return True

    async def list_models_raw(self) -> list[dict]:
        return list(_MODELS.values())

    async def show_model(self, model: str) -> Optional[dict]:
        return _SHOW if model in _MODELS else None

    async def delete_model(self, model: str) -> bool:
        FakeCatalogProvider.deleted.append(model)
        return True


@pytest.fixture(autouse=True)
def _fake_default():
    original = settings.RUNTIME_PROVIDER
    FakeCatalogProvider.deleted = []
    manager.register_provider("fakecat", FakeCatalogProvider)
    settings.RUNTIME_PROVIDER = "fakecat"
    manager.reset_runtime()
    yield
    settings.RUNTIME_PROVIDER = original
    manager.reset_runtime()
    manager._PROVIDERS.pop("fakecat", None)


async def _client() -> AsyncClient:
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- pure mappers ----------------------------------------------------------

def test_to_basic_maps_common_fields():
    caps = {"supports_delete": True}
    b = to_basic("fakecat", "FakeCat", caps, True, _MODELS["m-8b"])
    assert b["name"] == "m-8b"
    assert b["size"] == 4_700_000_000
    assert b["quantization"] == "Q4_K_M"
    assert b["family"] == "llama"
    assert b["status"] == "available"
    assert b["capabilities"] is caps


def test_to_basic_offline_status():
    assert to_basic("x", "X", {}, False, {"name": "m"})["status"] == "unreachable"


def test_to_extended_parses_ollama_show():
    ext = to_extended(_MODELS["m-8b"], _SHOW)
    assert ext["context_length"] == 8192
    assert ext["parameter_count"] == "8B"
    assert ext["architecture"] == "llama"
    assert ext["license"] == "MIT License"
    assert ext["tokenizer"] == "gpt2"
    assert ext["stop_tokens"] == ["<|im_end|>", "<|user|>"]
    assert ext["families"] == ["llama"]


def test_to_extended_degrades_gracefully():
    ext = to_extended({"name": "x"}, None)
    assert ext["context_length"] is None
    assert ext["stop_tokens"] == []
    assert ext["architecture"] is None


def test_parse_stop_tokens_and_unix():
    assert _parse_stop_tokens(None) == []
    assert _parse_stop_tokens('stop "A"\nstop "B"') == ["A", "B"]
    assert _unix_to_iso(0) is not None
    assert _unix_to_iso("bad") is None


# --- catalog ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_catalog_groups_by_provider_with_capabilities():
    async with await _client() as c:
        resp = await c.get("/api/models/catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] == "fakecat"
    groups = {g["provider"]: g for g in body["providers"]}
    assert set(groups) >= {"ollama", "openai", "fakecat"}

    fake = groups["fakecat"]
    assert fake["online"] is True
    assert fake["can_delete"] is True
    assert fake["capabilities"]["supports_context_length"] is True
    assert fake["model_count"] == 2
    m = next(x for x in fake["models"] if x["name"] == "m-8b")
    assert m["size"] == 4_700_000_000
    assert m["quantization"] == "Q4_K_M"
    assert m["capabilities"]["supports_delete"] is True
    # Extended fields are NOT in the catalog (basic only).
    assert "context_length" not in m


@pytest.mark.asyncio
async def test_catalog_offline_provider_is_graceful():
    async with await _client() as c:
        body = (await c.get("/api/models/catalog")).json()
    groups = {g["provider"]: g for g in body["providers"]}
    # A hosted provider with no key is offline but must not break the catalog.
    openai = groups["openai"]
    assert openai["online"] is False
    assert openai["models"] == []
    assert openai["capabilities"]["supports_streaming"] is True


# --- detail (extended, on demand) ------------------------------------------

@pytest.mark.asyncio
async def test_detail_loads_extended_metadata():
    async with await _client() as c:
        resp = await c.get("/api/models/detail", params={"provider": "fakecat", "name": "m-8b"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["context_length"] == 8192
    assert body["architecture"] == "llama"
    assert body["parameter_count"] == "8B"
    assert body["stop_tokens"] == ["<|im_end|>", "<|user|>"]
    assert body["size"] == 4_700_000_000  # basic fields present too


@pytest.mark.asyncio
async def test_detail_unknown_provider_and_model_404():
    async with await _client() as c:
        bad_provider = await c.get("/api/models/detail", params={"provider": "ghost", "name": "x"})
        bad_model = await c.get("/api/models/detail", params={"provider": "fakecat", "name": "nope"})
    assert bad_provider.status_code == 404
    assert bad_model.status_code == 404


# --- delete (capability-gated) ---------------------------------------------

@pytest.mark.asyncio
async def test_delete_supported_provider():
    async with await _client() as c:
        resp = await c.request("DELETE", "/api/models/instance", params={"provider": "fakecat", "name": "m-1b"})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert "m-1b" in FakeCatalogProvider.deleted


@pytest.mark.asyncio
async def test_delete_unsupported_provider_400():
    async with await _client() as c:
        resp = await c.request("DELETE", "/api/models/instance", params={"provider": "lmstudio", "name": "x"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_unknown_provider_404():
    async with await _client() as c:
        resp = await c.request("DELETE", "/api/models/instance", params={"provider": "ghost", "name": "x"})
    assert resp.status_code == 404


# --- backwards compatibility -----------------------------------------------

@pytest.mark.asyncio
async def test_existing_models_endpoint_unchanged():
    async with await _client() as c:
        resp = await c.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body
    assert {m["name"] for m in body["models"]} == {"m-8b", "m-1b"}
