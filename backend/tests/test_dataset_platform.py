"""Dataset Platform (V3 Epic 3) — service, versioning, artifact publication, jobs, API.

Offline: repositories run against in-memory SQLite; the service is wired to a test
artifact registry so dataset artifacts are real; API tests monkeypatch the singleton.
"""
from __future__ import annotations

import json

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
    from app.artifacts.service import ArtifactRegistryService
    return ArtifactRegistryService(
        repository=SqlArtifactRepository(session_factory=SessionLocal),
        relationships=SqlArtifactRelationshipRepository(session_factory=SessionLocal))


@pytest_asyncio.fixture
async def svc(SessionLocal, registry):
    from app.datasets.repository import SqlDatasetRepository, SqlDatasetVersionRepository
    from app.datasets.service import DatasetPlatformService
    return DatasetPlatformService(
        dataset_repo=SqlDatasetRepository(session_factory=SessionLocal),
        version_repo=SqlDatasetVersionRepository(session_factory=SessionLocal),
        artifact_registry=registry)


SAMPLE = [{"instruction": "hi", "response": "hello"}, {"instruction": "bye", "response": "goodbye"}]


@pytest.mark.asyncio
async def test_register_publishes_dataset_artifact(svc, registry):
    d = await svc.register(name="support", records=SAMPLE)
    assert d["status"] == "ready" and d["current_version"] == 1
    assert d["statistics"]["record_count"] == 2
    assert d["content_hash"]
    # the version was published as a real dataset artifact
    assert d["artifact_id"]
    art = await registry.get(d["artifact_id"])
    assert art is not None and art["type"] == "dataset" and art["status"] == "ready"
    assert art["location"]["table"] == "v3_dataset_versions"


@pytest.mark.asyncio
async def test_import_bytes_jsonl(svc):
    data = ("\n".join(json.dumps(r) for r in SAMPLE)).encode("utf-8")
    d = await svc.import_bytes(name="imported", data=data, filename="data.jsonl")
    assert d["format"] == "jsonl" and d["statistics"]["record_count"] == 2


@pytest.mark.asyncio
async def test_preview_and_validate(svc):
    d = await svc.register(name="d", records=SAMPLE)
    prev = await svc.preview(d["id"], offset=0, limit=1)
    assert prev["total"] == 2 and len(prev["rows"]) == 1
    val = await svc.validate(d["id"])
    assert "valid" in val and "score" in val and "grade" in val


@pytest.mark.asyncio
async def test_split_creates_new_version_and_artifact(svc, registry):
    records = [{"text": f"row {i}"} for i in range(10)]
    d = await svc.register(name="d", records=records)
    res = await svc.split(d["id"], train=0.8, val=0.1, test=0.1)
    assert res["version"] == 2 and res["artifact_id"]
    # the new version's artifact descends from the first version's artifact (lineage)
    from app.artifacts.service import ArtifactLineageService
    lin = ArtifactLineageService(repository=registry._repo, relationships=registry._edges)
    lineage = await lin.lineage(res["artifact_id"])
    assert len(lineage["parents"]) == 1
    got = await svc.get(d["id"])
    assert got["current_version"] == 2


@pytest.mark.asyncio
async def test_dataset_processing_job(svc, SessionLocal, registry):
    """Dataset processing runs through the Job System."""
    from app.datasets.handlers import register_dataset_handlers
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService
    import app.datasets.service as ds_mod
    register_dataset_handlers()
    # point the module singleton the handler uses at our test service
    import types
    ds_mod.dataset_platform = svc  # handler imports app.datasets.dataset_platform
    import app.datasets as ds_pkg
    ds_pkg.dataset_platform = svc

    d = await svc.register(name="d", records=[{"text": f"r{i}"} for i in range(8)])
    jobs = JobService(repository=SqlJobRepository(session_factory=SessionLocal),
                      artifact_registry=registry, auto_worker=False)
    job = await jobs.submit(type="dataset_processing",
                            params={"dataset_id": d["id"], "operation": "split"})
    await jobs.drain()
    done = await jobs.get(job["id"])
    assert done["status"] == "completed"
    assert done["result"]["data"]["split"]["version"] == 2


# -- API --------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, registry, monkeypatch):
    from app.datasets.repository import SqlDatasetRepository, SqlDatasetVersionRepository
    from app.datasets.service import DatasetPlatformService
    import app.api.dataset_platform as api_mod
    test_svc = DatasetPlatformService(
        dataset_repo=SqlDatasetRepository(session_factory=SessionLocal),
        version_repo=SqlDatasetVersionRepository(session_factory=SessionLocal),
        artifact_registry=registry)
    monkeypatch.setattr(api_mod, "dataset_platform", test_svc)
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_api_register_list_preview(client):
    d = (await client.post("/api/dataset-platform",
                           json={"name": "d", "records": SAMPLE})).json()
    assert d["current_version"] == 1

    listed = (await client.get("/api/dataset-platform")).json()
    assert any(x["id"] == d["id"] for x in listed)

    prev = (await client.get(f"/api/dataset-platform/{d['id']}/preview")).json()
    assert prev["total"] == 2

    stats = (await client.get(f"/api/dataset-platform/{d['id']}/statistics")).json()
    assert stats["record_count"] == 2

    assert (await client.get("/api/dataset-platform/nope")).status_code == 404
