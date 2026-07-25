"""Automatic Foundation Model discovery (V3 Epic 4.5) — discovery pipeline,
resolution, duplicate prevention, availability sync, manual resolution, events,
the background Job, and the API.

Fully offline: the runtime is a fake (injected model list + provider status), the
resolver uses an injected fake introspector, and persistence runs against in-memory
SQLite. No live Ollama, no network — mirrors CI.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:",
                              connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def SessionLocal(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# --- Fake Ollama /api/show introspection, keyed by runtime ref -------------

async def fake_introspect(ref: str):
    if ref in ("phi3:mini", "phi4"):
        # phi3 3.8b has a single catalog candidate -> confident auto-resolve
        return {"details": {"family": "phi3", "parameter_size": "3.8B"}, "modelfile": ""}
    if ref == "llama3.1:8b":
        # llama 8b has two catalog candidates -> ambiguous -> needs resolution
        return {"details": {"family": "llama", "parameter_size": "8.0B"}, "modelfile": ""}
    if ref == "custom:tag":
        # Modelfile FROM naming an HF repo -> very confident
        return {"details": {"family": "llama", "parameter_size": "8.0B"},
                "modelfile": "FROM meta-llama/Llama-3.1-8B\n"}
    # unknown -> no facts -> no candidates -> needs resolution (honest, never guessed)
    return None


def _build(SessionLocal, *, models, online=True, provider="ollama"):
    """Construct a DiscoveryService wired to in-memory persistence + a fake runtime.
    ``models`` is a mutable list so tests can change what the runtime 'serves'."""
    from app.events import EventBus
    from app.foundation_models.discovery import DiscoveryService
    from app.foundation_models.repository import (
        SqlFoundationModelRepository, SqlRuntimeModelRepository)
    from app.foundation_models.resolution import ModelResolutionService
    from app.foundation_models.service import FoundationModelService

    state = {"models": list(models), "online": online}
    fm_service = FoundationModelService(
        repository=SqlFoundationModelRepository(session_factory=SessionLocal),
        resolution=ModelResolutionService(introspect_fn=fake_introspect, provider_name="ollama"))

    async def list_models_fn():
        return list(state["models"])

    async def provider_status_fn():
        return {"name": provider, "label": provider.title(), "online": state["online"]}

    bus = EventBus()
    svc = DiscoveryService(
        foundation_service=fm_service,
        runtime_repo=SqlRuntimeModelRepository(session_factory=SessionLocal),
        list_models_fn=list_models_fn, provider_status_fn=provider_status_fn, bus=bus)
    return svc, fm_service, state, bus


# ---------------------------------------------------------------------------
# discovery pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_discovery_registers_confident_and_flags_ambiguous(SessionLocal):
    svc, fm_service, _state, _bus = _build(
        SessionLocal, models=["phi3:mini", "llama3.1:8b", "mystery-model"])
    summary = await svc.run_discovery()

    assert summary["discovered"] == 3
    assert summary["resolved"] == 1          # only phi3 auto-resolves
    assert summary["needs_resolution"] == 2  # llama (ambiguous) + mystery (no candidates)
    assert summary["registered"] == 1

    # exactly one Foundation Model was auto-registered (phi3), from runtime resolution
    fms = await fm_service.list()
    assert len(fms) == 1 and fms[0]["source"] == "resolved_from_runtime"

    tracked = {t["runtime_ref"]: t for t in await svc.list_tracked()}
    assert tracked["phi3:mini"]["status"] == "resolved"
    assert tracked["phi3:mini"]["foundation_model_id"] == fms[0]["id"]
    assert tracked["llama3.1:8b"]["status"] == "needs_resolution"
    assert len(tracked["llama3.1:8b"]["candidates"]) >= 2      # candidates preserved
    assert tracked["mystery-model"]["status"] == "needs_resolution"
    assert tracked["mystery-model"]["candidates"] == []        # never fabricated


@pytest.mark.asyncio
async def test_discovery_idempotent_no_duplicates(SessionLocal):
    svc, fm_service, _state, _bus = _build(SessionLocal, models=["phi3:mini", "llama3.1:8b"])
    first = await svc.run_discovery()
    second = await svc.run_discovery()

    assert first["registered"] == 1
    assert second["registered"] == 0                # nothing new the second time
    assert len(await fm_service.list()) == 1        # no duplicate Foundation Model
    assert len(await svc.list_tracked()) == 2       # no duplicate runtime rows


@pytest.mark.asyncio
async def test_sync_marks_vanished_unavailable_keeps_foundation(SessionLocal):
    svc, fm_service, state, _bus = _build(SessionLocal, models=["phi3:mini"])
    await svc.run_discovery()
    assert len(await fm_service.list()) == 1

    # The runtime model disappears (e.g. `ollama rm`) while the runtime is reachable.
    state["models"] = []
    summary = await svc.run_discovery()
    assert summary["unavailable"] == 1

    tracked = (await svc.list_tracked())[0]
    assert tracked["available"] is False
    assert tracked["status"] == "unavailable"
    # Foundation identity is NEVER deleted — availability is state, identity persists.
    assert len(await fm_service.list()) == 1

    # It comes back -> available again.
    state["models"] = ["phi3:mini"]
    await svc.run_discovery()
    assert (await svc.list_tracked())[0]["available"] is True


@pytest.mark.asyncio
async def test_offline_does_not_mark_unavailable(SessionLocal):
    svc, _fm, state, _bus = _build(SessionLocal, models=["phi3:mini"])
    await svc.run_discovery()

    # Runtime goes offline: we can't SEE models, which is not the same as removed.
    state["models"] = []
    state["online"] = False
    summary = await svc.run_discovery()
    assert summary["online"] is False
    assert summary["unavailable"] == 0
    assert (await svc.list_tracked())[0]["available"] is True   # untouched — honest


# ---------------------------------------------------------------------------
# manual resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_one_adopts_top_candidate(SessionLocal):
    svc, fm_service, _state, _bus = _build(SessionLocal, models=["llama3.1:8b"])
    await svc.run_discovery()
    tracked = (await svc.list_tracked())[0]
    assert tracked["status"] == "needs_resolution"

    result = await svc.resolve_one(tracked["id"])
    assert result["foundation_model"] is not None
    assert result["runtime_model"]["status"] == "resolved"
    assert result["runtime_model"]["foundation_model_id"] == result["foundation_model"]["id"]
    assert len(await fm_service.list()) == 1


@pytest.mark.asyncio
async def test_resolve_one_explicit_repo(SessionLocal):
    svc, fm_service, _state, _bus = _build(SessionLocal, models=["mystery-model"])
    await svc.run_discovery()
    tracked = (await svc.list_tracked())[0]

    result = await svc.resolve_one(tracked["id"], hf_repo="some-org/Custom-7B")
    assert result["foundation_model"]["hf_repo"] == "some-org/Custom-7B"
    assert result["foundation_model"]["metadata"]["manual"] is True
    assert result["runtime_model"]["status"] == "resolved"


@pytest.mark.asyncio
async def test_resolve_one_unknown_returns_none(SessionLocal):
    svc, _fm, _state, _bus = _build(SessionLocal, models=[])
    assert await svc.resolve_one("does-not-exist") is None


@pytest.mark.asyncio
async def test_list_unresolved(SessionLocal):
    svc, _fm, _state, _bus = _build(SessionLocal, models=["phi3:mini", "llama3.1:8b"])
    await svc.run_discovery()
    unresolved = await svc.list_unresolved()
    assert {u["runtime_ref"] for u in unresolved} == {"llama3.1:8b"}


# ---------------------------------------------------------------------------
# events + failure handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_emitted(SessionLocal):
    svc, _fm, _state, bus = _build(SessionLocal, models=["phi3:mini"])
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    await svc.run_discovery()
    assert "runtime.models_discovered" in seen
    assert "foundation.model_resolved" in seen
    assert "foundation.model_registered" in seen
    assert "runtime.sync_completed" in seen


@pytest.mark.asyncio
async def test_sync_failed_event_on_list_error(SessionLocal):
    from app.events import EventBus
    from app.foundation_models.discovery import DiscoveryService
    from app.foundation_models.repository import SqlRuntimeModelRepository

    async def boom():
        raise RuntimeError("runtime exploded")

    async def status():
        return {"name": "ollama", "label": "Ollama", "online": True}

    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.name))
    svc = DiscoveryService(runtime_repo=SqlRuntimeModelRepository(session_factory=SessionLocal),
                           list_models_fn=boom, provider_status_fn=status, bus=bus)
    summary = await svc.run_discovery()
    assert "error" in summary
    assert "runtime.sync_failed" in seen


# ---------------------------------------------------------------------------
# background Job (Epic 2 Job System)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_discovery_job(SessionLocal, monkeypatch):
    import app.foundation_models.discovery as disc
    from app.foundation_models.discovery import register_discovery_handlers
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService

    svc, fm_service, _state, _bus = _build(SessionLocal, models=["phi3:mini"])
    # The Job handler uses the module singleton — point it at our wired instance.
    monkeypatch.setattr(disc, "discovery_service", svc)

    register_discovery_handlers()
    jobs = JobService(repository=SqlJobRepository(session_factory=SessionLocal), auto_worker=False)
    job = await jobs.submit(type="runtime_discovery")
    await jobs.drain()

    done = await jobs.get(job["id"])
    assert done["status"] == "completed"
    assert done["result"]["data"]["resolved"] == 1
    assert len(await fm_service.list()) == 1


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, monkeypatch):
    import app.api.foundation_models as fm_api
    import app.api.runtime_models as rm_api
    svc, fm_service, _state, _bus = _build(
        SessionLocal, models=["phi3:mini", "llama3.1:8b", "mystery-model"])
    monkeypatch.setattr(fm_api, "discovery_service", svc)
    monkeypatch.setattr(fm_api, "foundation_model_service", fm_service)
    monkeypatch.setattr(rm_api, "discovery_service", svc)

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c._svc = svc  # type: ignore[attr-defined]
        yield c


@pytest.mark.asyncio
async def test_api_discover_and_list(client):
    summary = (await client.post("/api/foundation-models/discover")).json()
    assert summary["discovered"] == 3 and summary["resolved"] == 1

    runtime_models = (await client.get("/api/runtime-models")).json()
    assert len(runtime_models) == 3

    unresolved = (await client.get("/api/runtime-models/unresolved")).json()
    assert {u["runtime_ref"] for u in unresolved} == {"llama3.1:8b", "mystery-model"}

    # Foundation Models were auto-registered and are immediately listable.
    fms = (await client.get("/api/foundation-models")).json()
    assert len(fms) == 1


@pytest.mark.asyncio
async def test_api_sync_is_idempotent(client):
    await client.post("/api/foundation-models/discover")
    summary = (await client.post("/api/foundation-models/sync")).json()
    assert summary["registered"] == 0                     # nothing new
    assert len((await client.get("/api/foundation-models")).json()) == 1


@pytest.mark.asyncio
async def test_api_resolve_runtime_model(client):
    await client.post("/api/foundation-models/discover")
    unresolved = (await client.get("/api/runtime-models/unresolved")).json()
    target = next(u for u in unresolved if u["runtime_ref"] == "llama3.1:8b")

    resolved = await client.post(f"/api/runtime-models/{target['id']}/resolve", json={})
    assert resolved.status_code == 200
    assert resolved.json()["runtime_model"]["status"] == "resolved"

    assert (await client.post("/api/runtime-models/nope/resolve", json={})).status_code == 404
