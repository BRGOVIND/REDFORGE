"""Export Engine (V3 Epic 3) — providers, merge→GGUF→Ollama pipeline, lineage, API.

Offline: runs in simulated mode (no llama.cpp/ollama binaries), producing real
placeholder files + artifacts with lineage. Honestly flagged ``simulated``.
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


def test_export_providers_listed():
    from app.export import list_export_providers
    provs = list_export_providers()
    targets = {p["target"] for p in provs}
    assert {"gguf", "ollama"} <= targets
    # architecture-ready future targets are listed honestly as not-yet-implemented
    assert {"lmstudio", "vllm"} <= targets


@pytest.mark.asyncio
async def test_export_pipeline_end_to_end(SessionLocal, registry, tmp_path):
    """A checkpoint artifact → merged_model → gguf → runtime_model, with lineage."""
    from app.export.handlers import register_export_handlers
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService

    # Seed a file-backed checkpoint artifact (as training would produce).
    ckpt_path = tmp_path / "step-40"
    ckpt_path.write_text('{"step": 40}')
    ckpt = await registry["registry"].register(
        type="checkpoint", name="ckpt", file_path=str(ckpt_path), producer="test")
    await registry["registry"].publish(ckpt["id"])

    register_export_handlers()
    jobs = JobService(repository=SqlJobRepository(session_factory=SessionLocal),
                      artifact_registry=registry["registry"], artifact_query=registry["query"],
                      auto_worker=False)

    job = await jobs.submit(type="export", params={"config": {
        "source_artifact_id": ckpt["id"], "target": "ollama", "base_model": "llama3:8b",
        "quantization": "q4_k_m", "model_name": "my-model"}})
    await jobs.drain()

    done = await jobs.get(job["id"])
    assert done["status"] == "completed"
    export = done["result"]["data"]["export"]
    assert export["simulated"] is True                # no real toolchain in CI — honest
    assert export["runtime_model_name"] == "my-model"
    assert export["merged_model_artifact_id"] and export["gguf_artifact_id"] and export["runtime_model_artifact_id"]

    # full lineage: runtime_model → gguf → merged_model → checkpoint
    from app.artifacts.service import ArtifactLineageService
    lin = ArtifactLineageService(repository=registry["repo"], relationships=registry["edges"])
    rt_lineage = await lin.lineage(export["runtime_model_artifact_id"])
    ancestor_ids = {a["id"] for a in rt_lineage["ancestors"]}
    assert export["gguf_artifact_id"] in ancestor_ids
    assert export["merged_model_artifact_id"] in ancestor_ids
    assert ckpt["id"] in ancestor_ids                 # traces all the way back to the checkpoint


# -- API --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_export_providers_and_submit(SessionLocal, registry, monkeypatch):
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService
    from app.export.handlers import register_export_handlers
    import app.jobs as jobs_pkg
    register_export_handlers()
    test_jobs = JobService(repository=SqlJobRepository(session_factory=SessionLocal),
                           artifact_registry=registry["registry"], artifact_query=registry["query"],
                           auto_worker=False)
    monkeypatch.setattr(jobs_pkg, "job_service", test_jobs)

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        provs = (await c.get("/api/export/providers")).json()
        assert any(p["target"] == "gguf" for p in provs)

        # seed a checkpoint artifact through the registry the job service shares
        ckpt = await registry["registry"].register(type="checkpoint", name="c",
                                                   file_path=__file__, producer="test")
        submitted = await c.post("/api/export", json={
            "source_artifact_id": ckpt["id"], "target": "gguf", "base_model": "m"})
        assert submitted.status_code == 202
        await test_jobs.drain()
        done = await test_jobs.get(submitted.json()["id"])
        assert done["status"] == "completed"
