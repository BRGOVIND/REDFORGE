"""Foundation Model Platform (V3 Epic 1) — domain, repository, service, resolution, API.

Fully offline: resolution uses an injected fake introspector, the repository runs
against an in-memory SQLite DB, and the service singleton is monkeypatched onto the
test repository for API tests. No live provider, no network.
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
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def SessionLocal(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def repo(SessionLocal):
    from app.foundation_models.repository import SqlFoundationModelRepository
    return SqlFoundationModelRepository(session_factory=SessionLocal)


# Fake Ollama /api/show payloads.
async def fake_show_ambiguous(ref):
    return {"details": {"family": "llama", "parameter_size": "8.0B", "quantization_level": "Q4_0"},
            "modelfile": "FROM /root/.ollama/models/blobs/sha256-abc\nTEMPLATE ..."}

async def fake_show_from_repo(ref):
    return {"details": {"family": "llama", "parameter_size": "8.0B"},
            "modelfile": "FROM meta-llama/Llama-3.1-8B\n"}

async def fake_show_unique(ref):
    # phi3 3.8b has a single catalog candidate -> should auto-resolve
    return {"details": {"family": "phi3", "parameter_size": "3.8B"}, "modelfile": ""}


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------

def test_domain_identity_and_coercion():
    from app.foundation_models.domain import (
        FoundationModel, Quantization, WeightFormat, FoundationModelStatus)
    fm = FoundationModel(id="x", hf_repo="meta-llama/Llama-3.1-8B",
                         quantization=Quantization.BNB_4BIT)
    assert fm.identity_key == "meta-llama/Llama-3.1-8B@latest|safetensors|bnb_4bit"
    assert fm.is_local is False
    # unknown enum strings degrade rather than raise
    assert FoundationModel.coerce_format("nonsense") == WeightFormat.UNKNOWN
    assert FoundationModel.coerce_status("nonsense") == FoundationModelStatus.REFERENCED
    d = fm.to_dict()
    assert d["quantization"] == "bnb_4bit" and d["format"] == "safetensors"


# ---------------------------------------------------------------------------
# repository (dependency-inverted persistence)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repository_crud_and_identity(repo):
    from app.foundation_models.domain import FoundationModel, Quantization
    fm = FoundationModel(id="id1", hf_repo="meta-llama/Llama-3.1-8B")
    created = await repo.add(fm)
    assert created.id == "id1"

    got = await repo.get("id1")
    assert got is not None and got.hf_repo == "meta-llama/Llama-3.1-8B"

    by_identity = await repo.get_by_identity(fm.identity_key)
    assert by_identity is not None and by_identity.id == "id1"

    # a different quantization is a different identity
    fm2 = FoundationModel(id="id2", hf_repo="meta-llama/Llama-3.1-8B",
                          quantization=Quantization.BNB_4BIT)
    assert await repo.get_by_identity(fm2.identity_key) is None

    got.license = "llama-3"
    updated = await repo.update(got)
    assert updated.license == "llama-3"

    assert len(await repo.list()) == 1
    assert await repo.delete("id1") is True
    assert await repo.get("id1") is None


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_register_is_idempotent(repo):
    from app.foundation_models.service import FoundationModelService
    svc = FoundationModelService(repository=repo)
    a = await svc.register(hf_repo="meta-llama/Llama-3.1-8B")
    b = await svc.register(hf_repo="meta-llama/Llama-3.1-8B")
    assert a["id"] == b["id"]                      # same identity -> same row
    assert len(await svc.list()) == 1
    assert a["status"] == "referenced"             # no cache path -> honest status


@pytest.mark.asyncio
async def test_service_resolve_ambiguous_vs_confident(repo):
    from app.foundation_models.service import FoundationModelService
    from app.foundation_models.resolution import ModelResolutionService

    amb = FoundationModelService(
        repository=repo,
        resolution=ModelResolutionService(introspect_fn=fake_show_ambiguous, provider_name="ollama"))
    r = await amb.resolve("llama3.1:8b")
    assert r.is_ambiguous and r.resolved is None
    assert any("Llama-3.1-8B" in c.hf_repo for c in r.candidates)

    conf = FoundationModelService(
        repository=repo,
        resolution=ModelResolutionService(introspect_fn=fake_show_from_repo, provider_name="ollama"))
    r2 = await conf.resolve("custom-tag")
    assert r2.resolved is not None and r2.resolved.hf_repo == "meta-llama/Llama-3.1-8B"
    assert r2.resolved.confidence >= 0.9


@pytest.mark.asyncio
async def test_ensure_foundation_for_base_model_seam(repo):
    from app.foundation_models.service import FoundationModelService
    from app.foundation_models.resolution import ModelResolutionService

    # 1. An HF-repo-shaped string registers directly.
    svc = FoundationModelService(repository=repo)
    fm = await svc.ensure_foundation_for_base_model("meta-llama/Llama-3.1-8B")
    assert fm["hf_repo"] == "meta-llama/Llama-3.1-8B" and fm["source"] == "hf_hub"

    # 2. A runtime tag that resolves confidently is registered as resolved_from_runtime.
    svc2 = FoundationModelService(
        repository=repo,
        resolution=ModelResolutionService(introspect_fn=fake_show_unique, provider_name="ollama"))
    fm2 = await svc2.ensure_foundation_for_base_model("phi3:mini")
    assert fm2["source"] == "resolved_from_runtime"
    assert fm2["metadata"]["auto_resolved"] is True

    # 3. An unresolvable tag is recorded honestly as unverified, never fabricated.
    async def fake_blank(ref):
        return None
    svc3 = FoundationModelService(
        repository=repo,
        resolution=ModelResolutionService(introspect_fn=fake_blank, provider_name="generic"))
    fm3 = await svc3.ensure_foundation_for_base_model("mystery-model")
    assert fm3["metadata"].get("unverified") is True
    assert fm3["hf_repo"] == "mystery-model"


@pytest.mark.asyncio
async def test_service_sync_marks_missing_cache_invalid(repo):
    from app.foundation_models.service import FoundationModelService
    svc = FoundationModelService(repository=repo)
    fm = await svc.register(hf_repo="meta-llama/Llama-3.1-8B",
                            cache_path="/nonexistent/path/to/weights")
    # register with a nonexistent path stays referenced (honest, not local)
    assert fm["status"] == "referenced"
    synced = await svc.sync(fm["id"])
    assert synced["status"] == "invalid"          # recorded path missing -> honest invalid


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, monkeypatch):
    # Point the singleton service at the test DB via a test repository.
    from app.foundation_models.repository import SqlFoundationModelRepository
    from app.foundation_models.service import FoundationModelService
    from app.foundation_models.resolution import ModelResolutionService
    import app.foundation_models.service as svc_mod
    import app.api.foundation_models as api_mod

    test_svc = FoundationModelService(
        repository=SqlFoundationModelRepository(session_factory=SessionLocal),
        resolution=ModelResolutionService(introspect_fn=fake_show_from_repo, provider_name="ollama"))
    monkeypatch.setattr(svc_mod, "foundation_model_service", test_svc)
    monkeypatch.setattr(api_mod, "foundation_model_service", test_svc)

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_api_register_list_get(client):
    resp = await client.post("/api/foundation-models",
                             json={"hf_repo": "meta-llama/Llama-3.1-8B", "architecture": "llama"})
    assert resp.status_code == 201
    mid = resp.json()["id"]

    listed = (await client.get("/api/foundation-models")).json()
    assert any(m["id"] == mid for m in listed)

    one = await client.get(f"/api/foundation-models/{mid}")
    assert one.status_code == 200 and one.json()["hf_repo"] == "meta-llama/Llama-3.1-8B"

    st = (await client.get(f"/api/foundation-models/{mid}/status")).json()
    assert st["status"] == "referenced" and st["is_local"] is False

    assert (await client.get("/api/foundation-models/nope")).status_code == 404


@pytest.mark.asyncio
async def test_api_resolve(client):
    r = (await client.post("/api/foundation-models/resolve",
                           json={"runtime_ref": "my-llama"})).json()
    assert r["resolved"] is not None
    assert r["resolved"]["hf_repo"] == "meta-llama/Llama-3.1-8B"


@pytest.mark.asyncio
async def test_api_ensure_seam(client):
    r = (await client.post("/api/foundation-models/ensure",
                           json={"base_model": "meta-llama/Llama-3.1-8B"}))
    assert r.status_code == 201 and r.json()["source"] == "hf_hub"


@pytest.mark.asyncio
async def test_api_delete(client):
    mid = (await client.post("/api/foundation-models",
                             json={"hf_repo": "mistralai/Mistral-7B-v0.3"})).json()["id"]
    assert (await client.delete(f"/api/foundation-models/{mid}")).json()["deleted"] is True
    assert (await client.get(f"/api/foundation-models/{mid}")).status_code == 404
