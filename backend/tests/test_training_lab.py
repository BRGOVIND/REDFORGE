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


@pytest.fixture
def force_cpu(monkeypatch):
    """Force the Unsloth backend to report unavailable so backend-selection tests
    are deterministic regardless of the host GPU / ML stack. The GPU-available
    scenario is covered separately (see test_backends_endpoint_reports_unsloth)."""
    from app.training import manager
    from app.api import training as training_api

    class _Unavailable:
        name = "unsloth"
        label = "Unsloth (local GPU · LoRA/QLoRA)"
        def is_available(self):
            return False, "no CUDA GPU detected (simulated CPU-only env)"
        def diagnose(self, refresh=False):
            return {"backend": "unsloth", "label": self.label, "ready": False,
                    "checks": [{"name": "CUDA", "ok": False, "detail": "unavailable", "required": True}],
                    "missing_required": ["CUDA"], "status": "Not ready — CUDA unavailable",
                    "install_hint": ""}

    monkeypatch.setitem(manager._PROVIDERS, "unsloth", lambda: _Unavailable())
    manager.reset_availability_cache()
    monkeypatch.setattr(training_api, "_backends_cache", None, raising=False)
    yield
    manager.reset_availability_cache()


def test_registry_lists_backends_with_availability(force_cpu):
    from app.training import manager
    backs = manager.available_backends()
    names = {b["name"] for b in backs}
    assert "simulation" in names and "unsloth" in names
    sim = next(b for b in backs if b["name"] == "simulation")
    assert sim["available"] is True
    uns = next(b for b in backs if b["name"] == "unsloth")
    assert uns["available"] is False  # forced CPU-only by the fixture
    # With no real backend usable, auto-detection lands on simulation. (The old
    # module constant DEFAULT_BACKEND was removed — it always read "simulation"
    # regardless of hardware, one letter away from this function.)
    assert manager.default_backend() == "simulation"


def test_get_provider_auto_detects_simulation_when_nothing_else_is_usable(force_cpu):
    from app.training import manager
    assert manager.get_provider(None).name == "simulation"


def test_unknown_backend_raises_instead_of_silently_simulating(force_cpu):
    """A misspelled backend used to fall through to simulation, producing a *fake*
    run that reported success — the worst possible failure for a training tool."""
    from app.training import manager
    with pytest.raises(manager.UnknownBackendError):
        manager.get_provider("does-not-exist")


def test_get_provider_reports_unsloth_when_available(monkeypatch):
    """GPU-available scenario — selection must pick the real backend."""
    from app.training import manager

    class _Ready:
        name = "unsloth"; label = "Unsloth"
        def is_available(self):
            return True, "ready"

    monkeypatch.setitem(manager._PROVIDERS, "unsloth", lambda: _Ready())
    manager.reset_availability_cache()
    assert manager.default_backend() == "unsloth"


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
async def test_backends_endpoint(client, force_cpu):
    r = (await client.get("/api/training/backends")).json()
    assert r["default"] == "simulation"
    assert any(b["name"] == "unsloth" for b in r["backends"])


@pytest.mark.asyncio
async def test_diagnostics_endpoint(client):
    """Structured per-layer diagnostics — reports each dependency independently."""
    d = (await client.get("/api/training/diagnostics")).json()
    names = {c["name"] for c in d["checks"]}
    assert {"PyTorch", "CUDA", "GPU", "Transformers", "PEFT", "Unsloth"} <= names
    assert "ready" in d and "status" in d
    # every check has an explicit ok/detail — never a collapsed single message
    assert all("ok" in c and "detail" in c for c in d["checks"])


@pytest.mark.asyncio
async def test_diagnostics_never_defaults_to_simulation(client, monkeypatch):
    """The regression this pins down.

    Diagnostics answers "*why can't I train?*". When no real backend is usable —
    exactly the CI runner's situation, and any machine without a GPU — it must
    still report the real backend's per-layer breakdown. Defaulting to the
    *runnable* backend collapsed this to a single "Simulation (no GPU required)"
    check, which tells the user nothing about the missing PyTorch/CUDA/Unsloth.
    """
    from app.training import manager
    from app.training.providers.managed import ManagedRuntimeProvider
    from app.training.providers.unsloth import UnslothProvider

    def unavailable(cls):
        class _CI(cls):
            def is_available(self):
                return False, "not installed (simulated CI environment)"
        return _CI

    monkeypatch.setitem(manager._PROVIDERS, "unsloth", unavailable(UnslothProvider))
    monkeypatch.setitem(manager._PROVIDERS, "managed", unavailable(ManagedRuntimeProvider))
    manager.reset_availability_cache()

    # What will *run* is simulation …
    assert manager.default_backend() == "simulation"
    # … but what we *diagnose* is the real training path.
    assert manager.default_diagnostics_backend() != "simulation"

    d = (await client.get("/api/training/diagnostics")).json()
    assert d["backend"] != "simulation"
    names = {c["name"] for c in d["checks"]}
    assert {"PyTorch", "CUDA", "GPU", "Transformers", "PEFT", "Unsloth"} <= names


@pytest.mark.asyncio
async def test_diagnostics_rejects_an_unknown_backend(client):
    r = await client.get("/api/training/diagnostics", params={"backend": "not-a-backend"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_run_crud_notes_delete(client, force_cpu):
    from app.training import training_service
    # create directly via service (launch spawns a background task on a different DB)
    from app.db.database import get_db  # noqa: F401

    # use the API to create+list by launching then immediately inspecting the row.
    # base_model is a Foundation Model identity (HF repo) — training providers receive
    # a foundation id, never a runtime tag (an unresolvable tag is now a 422).
    resp = await client.post("/api/training/launch", json={
        "name": "My Run", "base_model": "meta-llama/Llama-3.1-8B", "method": "qlora",
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
async def test_launch_resolves_runtime_model_to_foundation(client, force_cpu, monkeypatch):
    """A Runtime Model tag is resolved to a Foundation Model (HF repo) BEFORE it can
    reach a training provider — the run + provider config carry the HF repo, never the
    tag. This is the architectural guarantee (providers are runtime-agnostic)."""
    from app.api import training as training_api

    async def fake_resolve(base_model):
        assert base_model == "qwen3:8b"   # the runtime tag the operator selected
        return {"id": "fm-1", "hf_repo": "Qwen/Qwen3-8B",
                "source": "resolved_from_runtime", "metadata": {"auto_resolved": True}}

    monkeypatch.setattr(training_api.foundation_model_service,
                        "ensure_foundation_for_base_model", fake_resolve)
    resp = await client.post("/api/training/launch", json={
        "name": "R", "base_model": "qwen3:8b", "method": "qlora", "params": {"epochs": 1}})
    assert resp.status_code == 202
    # The run stores the FOUNDATION identity, not the runtime tag.
    assert resp.json()["run"]["base_model"] == "Qwen/Qwen3-8B"


@pytest.mark.asyncio
async def test_launch_rejects_unresolvable_runtime_tag(client, force_cpu, monkeypatch):
    """If a runtime tag cannot be resolved to a real HF foundation repo, the launch
    fails honestly (422) instead of passing the tag to the provider."""
    from app.api import training as training_api

    async def fake_unverified(base_model):
        return {"id": "fm-2", "hf_repo": base_model, "source": "resolved_from_runtime",
                "metadata": {"unverified": True}}

    monkeypatch.setattr(training_api.foundation_model_service,
                        "ensure_foundation_for_base_model", fake_unverified)
    resp = await client.post("/api/training/launch", json={
        "name": "R", "base_model": "mysterymodel:xyz", "method": "qlora", "params": {"epochs": 1}})
    assert resp.status_code == 422


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
