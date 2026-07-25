"""Artifact Registry (V3 Epic 2) — domain, storage, repository, services, lineage, API.

Offline: repositories run against an in-memory SQLite DB; services are constructed
with those repositories; API tests monkeypatch the singletons onto the test DB.
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
async def services(SessionLocal):
    from app.artifacts.repository import (
        SqlArtifactRepository, SqlArtifactRelationshipRepository, SqlArtifactVersionRepository)
    from app.artifacts.service import (
        ArtifactRegistryService, ArtifactQueryService, ArtifactLineageService, ArtifactVersionService)
    repo = SqlArtifactRepository(session_factory=SessionLocal)
    edges = SqlArtifactRelationshipRepository(session_factory=SessionLocal)
    vrepo = SqlArtifactVersionRepository(session_factory=SessionLocal)
    return {
        "registry": ArtifactRegistryService(repository=repo, relationships=edges),
        "query": ArtifactQueryService(repository=repo),
        "lineage": ArtifactLineageService(repository=repo, relationships=edges),
        "versions": ArtifactVersionService(repository=repo, versions=vrepo, relationships=edges),
    }


# ---------------------------------------------------------------------------
# domain + types + storage
# ---------------------------------------------------------------------------

def test_artifact_types_extensible():
    from app.artifacts.artifact_types import get_artifact_type, is_file_backed, list_artifact_types
    assert any(t["key"] == "checkpoint" for t in list_artifact_types())
    assert is_file_backed("checkpoint") is True
    assert is_file_backed("benchmark") is False
    # an unknown type is accepted, not rejected (extensible without code change)
    unk = get_artifact_type("some_future_type")
    assert unk.key == "some_future_type" and unk.backing == "file"


def test_local_storage_and_checksum(tmp_path):
    from app.artifacts.storage import LocalStorageProvider
    from app.artifacts.checksum import sha256_bytes
    p = tmp_path / "weights.bin"
    p.write_bytes(b"hello world")
    s = LocalStorageProvider()
    assert s.exists(str(p)) and s.size(str(p)) == 11
    assert s.checksum(str(p)) == sha256_bytes(b"hello world")
    assert s.exists(str(tmp_path / "nope")) is False


# ---------------------------------------------------------------------------
# registry + lineage + versioning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_publish_and_lineage(services):
    reg, lin = services["registry"], services["lineage"]

    ds = await reg.register(type="dataset", name="support-data", producer="user_import",
                            table="datasets", row_id="d1")
    fm = await reg.register(type="foundation_model", name="Llama-3.1-8B", table="foundation_models", row_id="f1")
    assert ds["status"] == "draft" and ds["location"]["kind"] == "data"

    # training run derived from dataset + foundation model (two parents — DAG)
    tr = await reg.register(type="training_run", name="run-1",
                            parents=[(ds["id"], "consumed"), (fm["id"], "consumed")])
    ck = await reg.register(type="checkpoint", name="ckpt-step-40",
                            parents=[(tr["id"], "derived_from")])

    published = await reg.publish(ck["id"])
    assert published["status"] == "ready"

    # lineage: checkpoint's ancestors include training_run, dataset, foundation model
    lineage = await lin.lineage(ck["id"])
    ancestor_ids = {a["id"] for a in lineage["ancestors"]}
    assert tr["id"] in ancestor_ids and ds["id"] in ancestor_ids and fm["id"] in ancestor_ids
    # and the dataset's descendants include the checkpoint (impact query)
    ds_lineage = await lin.lineage(ds["id"])
    assert ck["id"] in {d["id"] for d in ds_lineage["descendants"]}
    # direct parents of the training run are the dataset + foundation model
    tr_parents = await lin.parents(tr["id"])
    assert {p["id"] for p in tr_parents} == {ds["id"], fm["id"]}


@pytest.mark.asyncio
async def test_versioning_shares_lineage(services):
    reg, ver = services["registry"], services["versions"]
    a = await reg.register(type="dataset", name="v1", table="datasets", row_id="d1")
    v2 = await ver.create_version(a["id"], description="cleaned")
    assert v2["version"] == 2 and v2["lineage_id"] == a["lineage_id"]
    v3 = await ver.create_version(v2["id"], description="split")
    assert v3["version"] == 3 and v3["lineage_id"] == a["lineage_id"]
    history = await ver.history(a["id"])
    assert [h["version"] for h in history] == [1, 2, 3]


@pytest.mark.asyncio
async def test_file_backed_checksum_and_validate(services, tmp_path):
    reg = services["registry"]
    from app.artifacts.domain import ArtifactLocation
    p = tmp_path / "adapter.safetensors"
    p.write_bytes(b"adapter-weights")
    a = await reg.register(type="adapter", name="lora", location=ArtifactLocation.file(str(p)))
    assert a["size_bytes"] == len(b"adapter-weights") and a["checksum"]["value"]

    valid = await reg.validate(a["id"])
    assert valid["valid"] is True

    p.unlink()  # delete the file -> integrity check must fail honestly
    invalid = await reg.validate(a["id"])
    assert invalid["valid"] is False
    got = await reg.get(a["id"])
    assert got["status"] == "invalid"


@pytest.mark.asyncio
async def test_publish_emits_event(services):
    from app.events import event_bus
    seen = []
    unsub = event_bus.subscribe("artifact.published", lambda e: seen.append(e.payload["id"]))
    a = await services["registry"].register(type="report", name="r", table="reports", row_id="1")
    await services["registry"].publish(a["id"])
    unsub()
    assert a["id"] in seen


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, monkeypatch):
    from app.artifacts.repository import (
        SqlArtifactRepository, SqlArtifactRelationshipRepository, SqlArtifactVersionRepository)
    from app.artifacts.service import (
        ArtifactRegistryService, ArtifactQueryService, ArtifactLineageService, ArtifactVersionService)
    import app.api.artifacts as api_mod
    repo = SqlArtifactRepository(session_factory=SessionLocal)
    edges = SqlArtifactRelationshipRepository(session_factory=SessionLocal)
    vrepo = SqlArtifactVersionRepository(session_factory=SessionLocal)
    monkeypatch.setattr(api_mod, "artifact_registry", ArtifactRegistryService(repository=repo, relationships=edges))
    monkeypatch.setattr(api_mod, "artifact_query", ArtifactQueryService(repository=repo))
    monkeypatch.setattr(api_mod, "artifact_lineage", ArtifactLineageService(repository=repo, relationships=edges))
    monkeypatch.setattr(api_mod, "artifact_versions", ArtifactVersionService(repository=repo, versions=vrepo, relationships=edges))
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_api_register_search_lineage(client):
    assert (await client.get("/api/artifacts/types")).status_code == 200

    ds = (await client.post("/api/artifacts", json={
        "type": "dataset", "name": "d", "table": "datasets", "row_id": "d1"})).json()
    tr = (await client.post("/api/artifacts", json={
        "type": "training_run", "name": "run",
        "parents": [{"parent_id": ds["id"], "relationship": "consumed"}]})).json()

    listed = (await client.get("/api/artifacts", params={"type": "dataset"})).json()
    assert any(a["id"] == ds["id"] for a in listed)

    lineage = (await client.get(f"/api/artifacts/{tr['id']}/lineage")).json()
    assert ds["id"] in {a["id"] for a in lineage["ancestors"]}

    v2 = (await client.post(f"/api/artifacts/{ds['id']}/version", json={"description": "v2"}))
    assert v2.status_code == 201 and v2.json()["version"] == 2

    assert (await client.get("/api/artifacts/nope")).status_code == 404
    assert (await client.delete(f"/api/artifacts/{tr['id']}")).json()["deleted"] is True
