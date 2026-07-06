"""Tests for the first-run system-checks endpoint."""
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


def _status(body: dict, key: str) -> str:
    return next(c["status"] for c in body["checks"] if c["key"] == key)


@pytest.mark.asyncio
async def test_checks_ready_when_everything_present(db_session, monkeypatch):
    import app.api.system as system
    from app.main import app
    from app.db.database import get_db

    monkeypatch.setattr(system.shutil, "which", lambda _: "/usr/bin/ollama")

    async def fake_tags():
        return True, ["llama3:8b", "gemma:2b"]

    monkeypatch.setattr(system, "_ollama_tags", fake_tags)

    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/system/checks")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert _status(body, "ollama_installed") == "ok"
    assert _status(body, "ollama_running") == "ok"
    assert _status(body, "database") == "ok"
    assert _status(body, "dataset") == "ok"
    assert _status(body, "models") == "ok"
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_checks_not_ready_when_ollama_missing(db_session, monkeypatch):
    import app.api.system as system
    from app.main import app
    from app.db.database import get_db

    monkeypatch.setattr(system.shutil, "which", lambda _: None)

    async def fake_tags():
        return False, []

    monkeypatch.setattr(system, "_ollama_tags", fake_tags)

    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/system/checks")
    app.dependency_overrides.clear()

    body = resp.json()
    assert _status(body, "ollama_installed") == "failed"
    assert _status(body, "ollama_running") == "failed"
    assert _status(body, "models") == "failed"
    assert body["ready"] is False
    # Dataset/database still fine even when Ollama is absent.
    assert _status(body, "database") == "ok"
    assert _status(body, "dataset") == "ok"
    assert body["ollama_download_url"].startswith("http")


@pytest.mark.asyncio
async def test_checks_running_but_no_models_is_warning(db_session, monkeypatch):
    import app.api.system as system
    from app.main import app
    from app.db.database import get_db

    monkeypatch.setattr(system.shutil, "which", lambda _: "/usr/bin/ollama")

    async def fake_tags():
        return True, []

    monkeypatch.setattr(system, "_ollama_tags", fake_tags)

    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/system/checks")
    app.dependency_overrides.clear()

    body = resp.json()
    assert _status(body, "models") == "warning"
    assert body["ready"] is False  # a model is required to run
    assert body["recommended_models"]
