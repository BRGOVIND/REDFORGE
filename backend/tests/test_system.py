"""Tests for the provider-agnostic first-run system-checks endpoint.

The endpoint reports the ACTIVE provider through the Runtime Manager. Tests fake
``get_runtime`` so no live provider (Ollama or otherwise) is needed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.attacks.library import seed_attacks
from app.db.database import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fac = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with fac() as db:
        await seed_attacks(db)
    session = fac()
    yield session
    await session.close()
    await engine.dispose()


class _FakeProvider:
    def __init__(self, *, online, label="Ollama", name="ollama", supports_pull=True,
                 requires_api_key=False, api_key=None):
        self._online = online
        self.name = name
        self.label = label
        self.base_url = "http://localhost:1234"
        self.docs_url = "https://example.test/download"
        self.setup_hint = f"Start {label}"
        self.requires_api_key = requires_api_key
        self.api_key = api_key
        self._supports_pull = supports_pull

    def capabilities(self):
        return {"supports_pull": self._supports_pull}

    async def health(self):
        return self._online


class _FakeRuntime:
    def __init__(self, provider, models):
        self.provider = provider
        self._models = models

    async def list_models(self, use_cache=True):
        return self._models


def _patch_runtime(monkeypatch, *, online, models, **kw):
    import app.api.system as system
    provider = _FakeProvider(online=online, **kw)
    monkeypatch.setattr(system, "get_runtime", lambda: _FakeRuntime(provider, models))


def _status(body: dict, key: str) -> str:
    return next(c["status"] for c in body["checks"] if c["key"] == key)


async def _call(db_session) -> dict:
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/system/checks")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_ready_when_provider_reachable_with_models(db_session, monkeypatch):
    _patch_runtime(monkeypatch, online=True, models=["llama3.1:8b", "mistral:7b"])
    body = await _call(db_session)
    assert _status(body, "runtime_running") == "ok"
    assert _status(body, "database") == "ok"
    assert _status(body, "dataset") == "ok"
    assert _status(body, "models") == "ok"
    assert body["ready"] is True
    # Provider block reflects the active provider, not a hardcoded Ollama.
    assert body["provider"]["label"] == "Ollama"
    assert body["provider"]["reachable"] is True


@pytest.mark.asyncio
async def test_not_ready_when_provider_offline(db_session, monkeypatch):
    _patch_runtime(monkeypatch, online=False, models=[], label="LM Studio", name="lmstudio")
    body = await _call(db_session)
    assert _status(body, "runtime_running") == "failed"
    assert _status(body, "models") == "failed"
    assert body["ready"] is False
    assert _status(body, "database") == "ok"
    assert _status(body, "dataset") == "ok"
    # Guidance comes from the active provider, not "install Ollama".
    assert body["provider"]["label"] == "LM Studio"
    assert body["provider"]["docs_url"].startswith("http")
    assert "LM Studio" in next(c["hint"] for c in body["checks"] if c["key"] == "runtime_running")


@pytest.mark.asyncio
async def test_running_but_no_models_is_warning(db_session, monkeypatch):
    _patch_runtime(monkeypatch, online=True, models=[])
    body = await _call(db_session)
    assert _status(body, "models") == "warning"
    assert body["ready"] is False
    assert body["recommended_models"]  # pull-capable provider suggests models


@pytest.mark.asyncio
async def test_cloud_provider_missing_key(db_session, monkeypatch):
    _patch_runtime(
        monkeypatch, online=False, models=[], label="OpenAI", name="openai",
        supports_pull=False, requires_api_key=True, api_key=None,
    )
    body = await _call(db_session)
    assert _status(body, "runtime_running") == "failed"
    assert "API key" in next(c["detail"] for c in body["checks"] if c["key"] == "runtime_running")
    # Non-pull provider does not suggest pull commands.
    assert body["recommended_models"] == []
