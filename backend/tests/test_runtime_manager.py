"""Tests for the Runtime Manager (management layer over the provider registry).

No real backends: a fake provider is registered and made default so health/models/
version are deterministic. The management layer must not duplicate runtime logic —
it routes the default through the shared RuntimeClient (get_runtime()).
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.logging_config import configure_logging, get_logger
from app.runtime import manager
from app.runtime.client import Provider
from app.runtime.management import provider_manager
from app.runtime.responses import GenerationResult


class FakeMgmtProvider(Provider):
    name = "faketest"
    label = "Fake"
    base_url = "http://fake:1234"
    api_key_env = None
    api_key = None

    @property
    def requires_api_key(self) -> bool:
        return False

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        return GenerationResult(model, "ok", 1)

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        yield {"response": "ok", "done": True}

    async def health(self) -> bool:
        return True

    async def list_models_raw(self) -> list[dict]:
        return [{"name": "m1"}, {"name": "m2"}]

    async def show_model(self, model: str) -> Optional[dict]:
        return None

    async def version(self) -> Optional[str]:
        return "9.9-fake"


@pytest.fixture(autouse=True)
def _clean_runtime_state():
    """Register the fake provider; always restore the default + caches afterward."""
    original = settings.RUNTIME_PROVIDER
    manager.register_provider("faketest", FakeMgmtProvider)
    provider_manager._cache.clear()
    yield
    settings.RUNTIME_PROVIDER = original
    manager.reset_runtime()
    manager._PROVIDERS.pop("faketest", None)
    provider_manager._cache.clear()


async def _client() -> AsyncClient:
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- management service ----------------------------------------------------

@pytest.mark.asyncio
async def test_check_default_provider_reports_health_models_version():
    provider_manager.set_default("faketest")
    snap = await provider_manager.check("faketest")
    assert snap["online"] is True
    assert snap["healthy"] is True
    assert snap["model_count"] == 2
    assert snap["models"] == ["m1", "m2"]
    assert snap["version"] == "9.9-fake"
    assert snap["checked_at"] is not None


@pytest.mark.asyncio
async def test_check_unknown_provider_raises():
    with pytest.raises(KeyError):
        await provider_manager.check("does-not-exist")


def test_list_infos_marks_default_and_key_requirements():
    infos = {i["name"]: i for i in provider_manager.list_infos()}
    assert "ollama" in infos and "openai" in infos
    assert infos["openai"]["requires_api_key"] is True
    assert infos["lmstudio"]["requires_api_key"] is False


# --- API: list / detail ----------------------------------------------------

@pytest.mark.asyncio
async def test_get_providers_lists_all_and_default():
    async with await _client() as c:
        resp = await c.get("/api/providers")
    assert resp.status_code == 200
    body = resp.json()
    names = {p["name"] for p in body["providers"]}
    assert {"ollama", "lmstudio", "openai", "anthropic", "gemini"} <= names
    assert body["default"] == settings.RUNTIME_PROVIDER.lower()


@pytest.mark.asyncio
async def test_get_single_provider_and_unknown_404():
    async with await _client() as c:
        ok = await c.get("/api/providers/faketest")
        missing = await c.get("/api/providers/nope")
    assert ok.status_code == 200
    assert ok.json()["label"] == "Fake"
    assert missing.status_code == 404


# --- API: test connection --------------------------------------------------

@pytest.mark.asyncio
async def test_test_provider_returns_snapshot():
    provider_manager.set_default("faketest")
    async with await _client() as c:
        resp = await c.post("/api/providers/faketest/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["online"] is True
    assert body["model_count"] == 2
    assert body["version"] == "9.9-fake"


@pytest.mark.asyncio
async def test_test_unknown_provider_404():
    async with await _client() as c:
        resp = await c.post("/api/providers/ghost/test")
    assert resp.status_code == 404


# --- API: refresh ----------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_populates_health_for_all():
    async with await _client() as c:
        resp = await c.post("/api/providers/refresh")
    assert resp.status_code == 200
    providers = resp.json()["providers"]
    assert all(p.get("health") is not None for p in providers)
    fake = next(p for p in providers if p["name"] == "faketest")
    assert fake["health"]["online"] is True


# --- API: set default ------------------------------------------------------

@pytest.mark.asyncio
async def test_set_default_switches_active_provider():
    async with await _client() as c:
        resp = await c.post("/api/providers/default", json={"name": "faketest"})
        assert resp.status_code == 200
        assert resp.json()["default"] == "faketest"

        status = await c.get("/api/runtime/status")
        assert status.json()["provider"] == "faketest"


@pytest.mark.asyncio
async def test_set_default_unknown_is_400():
    async with await _client() as c:
        resp = await c.post("/api/providers/default", json={"name": "nope"})
    assert resp.status_code == 400


# --- API: runtime logs -----------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_logs_endpoint_returns_captured_lines():
    configure_logging()
    get_logger("test.runtime-manager").info("hello from runtime manager test")
    async with await _client() as c:
        resp = await c.get("/api/runtime/logs", params={"limit": 50})
    assert resp.status_code == 200
    lines = resp.json()["lines"]
    assert any("hello from runtime manager test" in ln["message"] for ln in lines)
