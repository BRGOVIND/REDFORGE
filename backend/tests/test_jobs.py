"""Execution Platform / Job System (V3 Epic 2) — domain, service, handlers, API.

Offline & deterministic: JobService runs with ``auto_worker=False`` and is driven by
``drain()``; handlers are exercised with an in-memory artifact registry so the full
Job → progress → result → publish-artifact pipeline is proven without a live provider.
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
async def artifacts(SessionLocal):
    from app.artifacts.repository import SqlArtifactRepository, SqlArtifactRelationshipRepository
    from app.artifacts.service import ArtifactRegistryService, ArtifactQueryService
    repo = SqlArtifactRepository(session_factory=SessionLocal)
    edges = SqlArtifactRelationshipRepository(session_factory=SessionLocal)
    return {
        "registry": ArtifactRegistryService(repository=repo, relationships=edges),
        "query": ArtifactQueryService(repository=repo),
    }


@pytest_asyncio.fixture
async def svc(SessionLocal, artifacts):
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService
    return JobService(repository=SqlJobRepository(session_factory=SessionLocal),
                      artifact_registry=artifacts["registry"], artifact_query=artifacts["query"],
                      auto_worker=False)


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------

def test_job_status_terminal_and_types():
    from app.jobs.domain import JobStatus
    from app.jobs.job_types import get_job_type, list_job_types
    assert JobStatus.COMPLETED.is_terminal and not JobStatus.RUNNING.is_terminal
    assert get_job_type("training").concurrency == 1     # training serialized
    assert get_job_type("some_future_kind").concurrency >= 1  # unknown kinds accepted
    assert any(t["key"] == "diagnostics" for t in list_job_types())


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_diagnostics_job_runs_with_progress(svc):
    job = await svc.submit(type="diagnostics", params={"steps": 4})
    assert job["status"] == "queued"
    await svc.drain()
    done = await svc.get(job["id"])
    assert done["status"] == "completed"
    assert done["result"]["success"] is True and done["result"]["data"]["steps"] == 4
    assert done["progress"]["fraction"] == 1.0
    assert done["attempts"] == 1


@pytest.mark.asyncio
async def test_failed_job_always_has_reason(svc):
    # a handler-less kind fails with a non-null reason
    job = await svc.submit(type="nonexistent_kind")
    await svc.drain()
    done = await svc.get(job["id"])
    assert done["status"] == "failed"
    assert done["error"] and "no handler" in done["error"]["message"].lower()
    assert done["completed_at"] is not None


@pytest.mark.asyncio
async def test_handler_exception_is_captured(svc):
    from app.jobs.handlers import handler_registry
    from app.jobs.domain import JobResult

    async def boom(job, ctx) -> JobResult:
        raise RuntimeError("kaboom")
    handler_registry.register("test_boom", boom)
    try:
        job = await svc.submit(type="test_boom")
        await svc.drain()
        done = await svc.get(job["id"])
        assert done["status"] == "failed"
        assert "kaboom" in done["error"]["message"]
        assert "RuntimeError" in done["error"]["traceback"]   # real traceback preserved
    finally:
        handler_registry._handlers.pop("test_boom", None)


@pytest.mark.asyncio
async def test_job_publishes_artifact(svc, artifacts):
    """The full pipeline: a job whose handler publishes an artifact records the
    artifact id on its result, and the artifact is real in the registry."""
    from app.jobs.handlers import handler_registry
    from app.jobs.domain import JobResult

    async def producer(job, ctx) -> JobResult:
        await ctx.report_progress(0.5, "producing")
        art = await ctx.publish_artifact(type="report", name="job-report",
                                         table="reports", row_id="r1")
        return JobResult(success=True, artifact_ids=[art["id"]], message="produced")
    handler_registry.register("test_producer", producer)
    try:
        job = await svc.submit(type="test_producer")
        await svc.drain()
        done = await svc.get(job["id"])
        assert done["status"] == "completed"
        aid = done["result"]["artifact_ids"][0]
        art = await artifacts["registry"].get(aid)
        assert art is not None and art["status"] == "ready" and art["producer"] == f"job:{job['id']}"
    finally:
        handler_registry._handlers.pop("test_producer", None)


@pytest.mark.asyncio
async def test_cancel_queued_job(svc):
    job = await svc.submit(type="diagnostics", params={"steps": 2})
    await svc.cancel(job["id"])
    await svc.drain()
    assert (await svc.get(job["id"]))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_retry_failed_job(svc):
    job = await svc.submit(type="nonexistent_kind", max_attempts=2)
    await svc.drain()
    assert (await svc.get(job["id"]))["status"] == "failed"
    retried = await svc.retry(job["id"])
    assert retried["status"] == "queued"
    await svc.drain()
    # still fails (no handler) but proves the retry path re-ran it
    assert (await svc.get(job["id"]))["attempts"] == 2


@pytest.mark.asyncio
async def test_model_discovery_job_uses_foundation_service(svc, monkeypatch):
    import app.foundation_models as fm

    async def fake_discover():
        return [{"runtime_ref": "llama3:8b", "suggested": None, "candidate_count": 0, "is_ambiguous": False}]
    monkeypatch.setattr(fm.foundation_model_service, "discover", fake_discover)

    job = await svc.submit(type="model_discovery")
    await svc.drain()
    done = await svc.get(job["id"])
    assert done["status"] == "completed"
    assert done["result"]["data"]["candidates"][0]["runtime_ref"] == "llama3:8b"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, artifacts, monkeypatch):
    from app.jobs.repository import SqlJobRepository
    from app.jobs.service import JobService
    import app.api.jobs as api_mod
    test_svc = JobService(repository=SqlJobRepository(session_factory=SessionLocal),
                          artifact_registry=artifacts["registry"], artifact_query=artifacts["query"],
                          auto_worker=False)
    monkeypatch.setattr(api_mod, "job_service", test_svc)
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, test_svc


@pytest.mark.asyncio
async def test_api_submit_and_read(client):
    c, svc = client
    assert (await c.get("/api/jobs/types")).status_code == 200

    submitted = await c.post("/api/jobs", json={"type": "diagnostics", "params": {"steps": 2}})
    assert submitted.status_code == 201
    jid = submitted.json()["id"]

    await svc.drain()
    done = (await c.get(f"/api/jobs/{jid}")).json()
    assert done["status"] == "completed"

    prog = (await c.get(f"/api/jobs/{jid}/progress")).json()
    assert prog["fraction"] == 1.0

    listed = (await c.get("/api/jobs", params={"type": "diagnostics"})).json()
    assert any(j["id"] == jid for j in listed)

    assert (await c.get("/api/jobs/nope")).status_code == 404
