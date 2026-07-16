"""RedForge V2 (AI Studio) — projects, playground, assistant.

All offline; the playground fakes the Runtime Manager so no live provider is
needed. Existing v1.2 behavior is untouched (see the runtime options test).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

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
    session = fac()
    yield session
    await session.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# -- Projects ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_project_crud_and_recent_order(client):
    a = (await client.post("/api/projects", json={"name": "Alpha"})).json()
    b = (await client.post("/api/projects", json={"name": "Beta", "models": ["llama3.1:8b"]})).json()
    assert a["id"] != b["id"]
    assert b["models"] == ["llama3.1:8b"]

    # list is most-recently-opened first → Beta (created last) leads.
    names = [p["name"] for p in (await client.get("/api/projects")).json()]
    assert names[:2] == ["Beta", "Alpha"]

    # opening Alpha bumps it to the top (Recent Projects).
    await client.post(f"/api/projects/{a['id']}/open")
    names = [p["name"] for p in (await client.get("/api/projects")).json()]
    assert names[0] == "Alpha"


@pytest.mark.asyncio
async def test_project_rename_duplicate_delete(client):
    p = (await client.post("/api/projects", json={"name": "Proj", "description": "d"})).json()
    pid = p["id"]

    renamed = (await client.patch(f"/api/projects/{pid}", json={"name": "Renamed"})).json()
    assert renamed["name"] == "Renamed"

    dup = (await client.post(f"/api/projects/{pid}/duplicate")).json()
    assert dup["name"] == "Renamed (copy)"
    assert dup["id"] != pid

    assert (await client.delete(f"/api/projects/{pid}")).json()["deleted"] is True
    assert (await client.get(f"/api/projects/{pid}")).status_code == 404
    # the duplicate survives
    assert (await client.get(f"/api/projects/{dup['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_project_limit_and_404(client):
    for i in range(3):
        await client.post("/api/projects", json={"name": f"P{i}"})
    limited = (await client.get("/api/projects", params={"limit": 2})).json()
    assert len(limited) == 2
    assert (await client.get("/api/projects/nope")).status_code == 404


# -- Playground (routes through the Runtime Manager) ------------------------

class _FakeProvider:
    name = "ollama"

    async def generate(self, model, prompt, *, options=None):
        _FakeProvider.last = {"model": model, "prompt": prompt, "options": options}
        from app.runtime.responses import GenerationResult
        return GenerationResult(model=model, text="hello from fake", latency_ms=12, eval_count=3)


class _FakeRuntime:
    provider = _FakeProvider()

    async def generate(self, model, prompt, *, options=None):
        return await self.provider.generate(model, prompt, options=options)


@pytest.mark.asyncio
async def test_playground_routes_through_runtime_with_options(client, monkeypatch):
    from app.api import playground as pg
    monkeypatch.setattr(pg, "get_runtime", lambda: _FakeRuntime())

    resp = await client.post("/api/playground/chat", json={
        "model": "llama3.1:8b",
        "messages": [{"role": "user", "content": "hi"}],
        "system": "be terse",
        "temperature": 0.4, "top_p": 0.9, "max_tokens": 128, "seed": 7,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "hello from fake"
    assert body["provider"] == "ollama"
    # sampling options + system were threaded through the runtime.
    opts = _FakeProvider.last["options"]
    assert opts["temperature"] == 0.4 and opts["seed"] == 7 and opts["system"] == "be terse"


@pytest.mark.asyncio
async def test_playground_empty_messages_422(client):
    resp = await client.post("/api/playground/chat", json={"model": "m", "messages": []})
    assert resp.status_code == 422


# -- Runtime options passthrough is additive (v1.2 unaffected) --------------

@pytest.mark.asyncio
async def test_runtime_generate_without_options_still_2arg():
    """Existing callers pass no options → provider is called with 2 args exactly."""
    from app.runtime.client import RuntimeClient

    class TwoArgProvider:
        name = "x"
        async def generate(self, model, prompt):  # no options kwarg at all
            from app.runtime.responses import GenerationResult
            return GenerationResult(model=model, text="ok", latency_ms=1)

    rc = RuntimeClient(TwoArgProvider())
    result = await rc.generate("m", "p")  # no options → must not pass the kwarg
    assert result.text == "ok"


# -- Assistant (offline, retrieval) -----------------------------------------

@pytest.mark.asyncio
async def test_assistant_answers_and_suggests(client):
    r = await client.post("/api/assistant/ask", json={"question": "how do I read a security score?"})
    assert r.status_code == 200
    body = r.json()
    assert body["sources"] and body["suggestions"]
    assert "score" in body["answer"].lower()

    s = (await client.get("/api/assistant/suggestions")).json()
    assert len(s["suggestions"]) >= 3


@pytest.mark.asyncio
async def test_assistant_unknown_question_is_graceful(client):
    r = await client.post("/api/assistant/ask", json={"question": "zxqw floop"})
    assert r.status_code == 200
    assert r.json()["sources"] == []
