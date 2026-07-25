"""Training Platform (V3 Epic 3) — service, strategies, estimation, Job execution,
artifact publication + lineage, API.

The end-to-end test drives the real ``training`` Job handler with the Simulation
provider, producing real checkpoint files + Artifacts with lineage — all offline.
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


@pytest_asyncio.fixture
async def registry(SessionLocal):
    from app.artifacts.repository import SqlArtifactRepository, SqlArtifactRelationshipRepository
    from app.artifacts.service import ArtifactRegistryService, ArtifactQueryService
    repo = SqlArtifactRepository(session_factory=SessionLocal)
    edges = SqlArtifactRelationshipRepository(session_factory=SessionLocal)
    return {"registry": ArtifactRegistryService(repository=repo, relationships=edges),
            "query": ArtifactQueryService(repository=repo), "repo": repo, "edges": edges}


@pytest_asyncio.fixture
async def platform(SessionLocal, monkeypatch):
    """A training platform service wired to in-memory repos, with the execution
    module's singletons pointed at the same repos so the Job handler is coherent."""
    from app.training.repository import SqlTrainingRunRepository, SqlCheckpointRepository
    from app.training.platform_service import TrainingPlatformService
    import app.training.execution as execmod
    run_repo = SqlTrainingRunRepository(session_factory=SessionLocal)
    ckpt_repo = SqlCheckpointRepository(session_factory=SessionLocal)
    monkeypatch.setattr(execmod, "_run_repo", run_repo)
    monkeypatch.setattr(execmod, "_checkpoint_repo", ckpt_repo)
    return TrainingPlatformService(run_repo=run_repo, checkpoint_repo=ckpt_repo)


# ---------------------------------------------------------------------------
# strategies + estimation + create
# ---------------------------------------------------------------------------

def test_strategies_and_provider_resolution():
    from app.training.strategies import list_strategies, get_strategy, compatible_providers
    keys = {s["key"] for s in list_strategies()}
    assert {"lora", "qlora", "sft", "dpo", "ppo", "rlhf"} <= keys
    assert get_strategy("lora").implemented and not get_strategy("dpo").implemented
    assert "simulation" in compatible_providers("lora")


@pytest.mark.asyncio
async def test_create_and_estimate(platform):
    run = await platform.create(name="t1", base_model="llama3:8b", strategy="lora",
                                provider="simulation", hyperparameters={"epochs": 1})
    assert run["status"] == "created"
    assert run["configuration"]["provider"] == "simulation"
    assert run["estimate"] is not None and run["estimate"]["vram_mb"] > 0

    est = await platform.estimate(base_model="llama3:8b", strategy="qlora", provider="simulation")
    assert "vram_mb" in est and "duration_seconds" in est


@pytest.mark.asyncio
async def test_launch_refuses_unimplemented_strategy(platform):
    run = await platform.create(name="t", base_model="m", strategy="dpo", provider="simulation")
    res = await platform.launch(run["id"])
    assert "error" in res and "not yet runnable" in res["error"]


# ---------------------------------------------------------------------------
# full end-to-end: training as a Job, producing checkpoints + adapter + lineage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_training_job_end_to_end(platform, SessionLocal, registry, tmp_path, monkeypatch):
    from app.training.execution import register_training_handlers
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService

    # Make the simulation provider fast.
    from app.training.providers import simulation
    monkeypatch.setattr(simulation.SimulationProvider, "_step_delay", 0.0)

    register_training_handlers()
    run = await platform.create(name="run1", base_model="llama3:1b", strategy="lora",
                                provider="simulation", hyperparameters={"epochs": 1},
                                output_dir=str(tmp_path / "run1"))

    jobs = JobService(repository=SqlJobRepository(session_factory=SessionLocal),
                      artifact_registry=registry["registry"], artifact_query=registry["query"],
                      auto_worker=False)
    job = await jobs.submit(type="training", params={"run_id": run["id"]})
    await jobs.drain()

    done_job = await jobs.get(job["id"])
    assert done_job["status"] == "completed"

    finished = await platform.get(run["id"])
    assert finished["status"] == "completed"
    assert finished["run_artifact_id"] and finished["adapter_artifact_id"]

    # checkpoints were persisted with real files + artifacts
    checkpoints = await platform.checkpoints(run["id"])
    assert len(checkpoints) >= 1 and all(c["artifact_id"] for c in checkpoints)

    # lineage: adapter descends from a checkpoint which descends from the run artifact
    from app.artifacts.service import ArtifactLineageService
    lin = ArtifactLineageService(repository=registry["repo"], relationships=registry["edges"])
    adapter_lineage = await lin.lineage(finished["adapter_artifact_id"])
    ancestor_ids = {a["id"] for a in adapter_lineage["ancestors"]}
    assert finished["run_artifact_id"] in ancestor_ids


@pytest.mark.asyncio
async def test_launch_submits_job(platform, monkeypatch):
    import app.jobs as jobs_pkg

    captured = {}

    class _FakeJobs:
        async def submit(self, **kwargs):
            captured.update(kwargs)
            return {"id": "job-x", "status": "queued"}
    monkeypatch.setattr(jobs_pkg, "job_service", _FakeJobs())

    run = await platform.create(name="t", base_model="m", strategy="lora", provider="simulation")
    res = await platform.launch(run["id"])
    assert res["run"]["status"] == "queued" and res["job"]["id"] == "job-x"
    assert captured["type"] == "training" and captured["params"]["run_id"] == run["id"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, monkeypatch):
    from app.training.repository import SqlTrainingRunRepository, SqlCheckpointRepository
    from app.training.platform_service import TrainingPlatformService
    import app.training.execution as execmod
    import app.api.training_platform as api_mod
    run_repo = SqlTrainingRunRepository(session_factory=SessionLocal)
    ckpt_repo = SqlCheckpointRepository(session_factory=SessionLocal)
    monkeypatch.setattr(execmod, "_run_repo", run_repo)
    monkeypatch.setattr(execmod, "_checkpoint_repo", ckpt_repo)
    monkeypatch.setattr(api_mod, "training_platform",
                        TrainingPlatformService(run_repo=run_repo, checkpoint_repo=ckpt_repo))
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_api_strategies_providers_create(client):
    strategies = (await client.get("/api/training-platform/strategies")).json()
    assert any(s["key"] == "lora" for s in strategies)
    providers = (await client.get("/api/training-platform/providers")).json()
    assert all(not p["dev_only"] or p["name"] == "simulation" for p in providers)

    est = await client.post("/api/training-platform/estimate",
                            json={"base_model": "llama3:8b", "strategy": "lora", "provider": "simulation"})
    assert est.status_code == 200 and est.json()["vram_mb"] > 0

    run = await client.post("/api/training-platform",
                            json={"name": "r", "base_model": "llama3:8b", "strategy": "lora",
                                  "provider": "simulation", "hyperparameters": {"epochs": 1}})
    assert run.status_code == 201
    rid = run.json()["id"]
    assert (await client.get(f"/api/training-platform/{rid}")).json()["status"] == "created"
    # launching a dpo (unimplemented) run is refused
    dpo = (await client.post("/api/training-platform",
                             json={"name": "d", "base_model": "m", "strategy": "dpo", "provider": "simulation"})).json()
    assert (await client.post(f"/api/training-platform/{dpo['id']}/launch")).status_code == 400
