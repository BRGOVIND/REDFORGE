"""Training Lab — provider/registry, run loop + checkpoints, API CRUD, assistant.

All offline (simulation backend; no ML stack). The real Unsloth path is GPU-gated
and not exercised here."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base


# -- provider / registry ----------------------------------------------------

def test_registry_lists_backends_with_availability():
    from app.training import manager
    backs = manager.available_backends()
    names = {b["name"] for b in backs}
    assert "simulation" in names and "unsloth" in names
    sim = next(b for b in backs if b["name"] == "simulation")
    assert sim["available"] is True
    uns = next(b for b in backs if b["name"] == "unsloth")
    assert uns["available"] is False  # no GPU/ML stack here
    assert manager.DEFAULT_BACKEND == "simulation"


def test_get_provider_defaults_to_simulation():
    from app.training import manager
    assert manager.get_provider(None).name == "simulation"
    assert manager.get_provider("does-not-exist").name == "simulation"


@pytest.mark.asyncio
async def test_simulation_provider_produces_decreasing_loss_and_checkpoints():
    from app.training.providers.simulation import SimulationProvider
    from app.training.providers.base import TrainingConfig

    prov = SimulationProvider()
    prov._step_delay = 0  # fast
    cfg = TrainingConfig(base_model="m", epochs=2, batch_size=2,
                         gradient_accumulation=2, dataset_records=list(range(20)))
    events = [e async for e in prov.run(cfg, lambda: False)]
    assert events[-1].status == "completed"
    losses = [e.loss for e in events if e.loss is not None]
    assert losses[-1] < losses[0]  # loss decreases
    assert any(e.checkpoint for e in events)  # checkpoints emitted


@pytest.mark.asyncio
async def test_simulation_respects_cancel():
    from app.training.providers.simulation import SimulationProvider
    from app.training.providers.base import TrainingConfig

    prov = SimulationProvider()
    prov._step_delay = 0
    cfg = TrainingConfig(base_model="m", epochs=5, dataset_records=list(range(50)))
    seen = 0

    def cancel():
        nonlocal seen
        seen += 1
        return seen > 3  # cancel after a few steps

    events = [e async for e in prov.run(cfg, cancel)]
    assert events[-1].status == "cancelled"


# -- runner integration (in-memory DB) --------------------------------------

@pytest_asyncio.fixture
async def mem_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_runner_completes_and_persists_checkpoints(mem_factory):
    from app.training import training_service
    from app.training.providers import simulation
    from app.training.providers.base import TrainingConfig
    from app.training.runner import run_training
    from app.training.store import progress_store

    simulation.SimulationProvider._step_delay = 0  # fast

    async with mem_factory() as db:
        run = await training_service.create(
            db, name="R", base_model="m", dataset_id=None, method="lora",
            backend="simulation", config={"epochs": 2}, output_dir="out",
        )
    rid = run["id"]
    cfg = TrainingConfig(base_model="m", epochs=2, dataset_records=list(range(20)))
    await run_training(rid, "simulation", cfg, session_factory=mem_factory)

    # live store reached terminal state
    assert progress_store.get(rid).status == "completed"
    # durable record updated + checkpoints persisted
    async with mem_factory() as db:
        final = await training_service.get(db, rid)
        assert final["status"] == "completed"
        assert final["duration_seconds"] is not None
        cps = await training_service.checkpoints(db, rid)
        assert len(cps) >= 1


# -- API --------------------------------------------------------------------

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


@pytest.mark.asyncio
async def test_backends_endpoint(client):
    r = (await client.get("/api/training/backends")).json()
    assert r["default"] == "simulation"
    assert any(b["name"] == "unsloth" for b in r["backends"])


@pytest.mark.asyncio
async def test_run_crud_notes_delete(client):
    from app.training import training_service
    # create directly via service (launch spawns a background task on a different DB)
    from app.db.database import get_db  # noqa: F401

    # use the API to create+list by launching then immediately inspecting the row
    resp = await client.post("/api/training/launch", json={
        "name": "My Run", "base_model": "llama3.1:8b", "method": "qlora",
        "params": {"epochs": 1},
    })
    assert resp.status_code == 202
    rid = resp.json()["run"]["id"]
    assert resp.json()["backend"] == "simulation"

    got = await client.get(f"/api/training/{rid}")
    assert got.status_code == 200 and got.json()["method"] == "qlora"

    listed = (await client.get("/api/training")).json()
    assert any(r["id"] == rid for r in listed)

    noted = (await client.patch(f"/api/training/{rid}/notes", json={"notes": "hi"})).json()
    assert noted["notes"] == "hi"

    # snapshot endpoint returns a shape even for an unknown/idle run
    prog = (await client.get(f"/api/training/{rid}/progress")).json()
    assert "status" in prog and "history" in prog

    assert (await client.delete(f"/api/training/{rid}")).json()["deleted"] is True
    assert (await client.get(f"/api/training/{rid}")).status_code == 404


@pytest.mark.asyncio
async def test_training_run_404s(client):
    assert (await client.get("/api/training/nope")).status_code == 404
    assert (await client.get("/api/training/nope/checkpoints")).status_code == 404


# -- assistant --------------------------------------------------------------

@pytest.mark.asyncio
async def test_assistant_explains_training_concepts(client):
    for q, needle in [
        ("Should I use LoRA or QLoRA?", "qlora"),
        ("Explain rank", "rank"),
        ("Explain alpha", "alpha"),
        ("Why is VRAM full?", "vram"),
    ]:
        r = (await client.post("/api/assistant/ask", json={"question": q})).json()
        assert needle in r["answer"].lower()


@pytest.mark.asyncio
async def test_assistant_answers_from_run_metadata(client):
    from app.training import training_service
    from app.db.database import get_db
    # grab the overridden session
    db = client._transport.app.dependency_overrides[get_db]()  # type: ignore
    run = await training_service.create(
        db, name="Diag", base_model="m", dataset_id=None, method="lora",
        backend="simulation", config={"learning_rate": 0.02},
    )
    r = (await client.post("/api/assistant/ask", json={
        "question": "why is loss increasing?", "run_id": run["id"],
    })).json()
    assert r["sources"][0]["title"].startswith("Training")
