"""Experiment Platform (V3 Epic 4) — domain, repository, service, event subscriber,
clone, comparison, snapshot, and API.

Everything runs offline against in-memory SQLite. The subscriber tests drive a fresh
Event Bus + in-memory service to prove the "engines publish into the Experiment via
events" mechanism without importing the Job System or the engines.
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


class _FakeArtifactQuery:
    """Stand-in for the Artifact Registry query service. Returns artifacts keyed by
    experiment_id so we can assert experiment→artifact reference behaviour offline."""

    def __init__(self) -> None:
        self.by_experiment: dict[str, list[dict]] = {}

    async def search(self, *, experiment_id=None, limit=500, **kwargs):
        return list(self.by_experiment.get(experiment_id, []))[:limit]


def _service(SessionLocal, artifacts=None):
    from app.experiments.repository import (
        SqlExperimentRepository, SqlJobRefRepository, SqlNoteRepository, SqlTimelineRepository,
    )
    from app.experiments.service import ExperimentService
    return ExperimentService(
        experiment_repo=SqlExperimentRepository(session_factory=SessionLocal),
        timeline_repo=SqlTimelineRepository(session_factory=SessionLocal),
        note_repo=SqlNoteRepository(session_factory=SessionLocal),
        jobref_repo=SqlJobRefRepository(session_factory=SessionLocal),
        artifact_query=artifacts or _FakeArtifactQuery())


@pytest_asyncio.fixture
async def svc(SessionLocal):
    return _service(SessionLocal)


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------

def test_domain_config_roundtrip_and_status_coercion():
    from app.experiments.domain import Experiment, ExperimentConfiguration, ExperimentStatus
    c = ExperimentConfiguration.from_dict({"base_model": "llama3:8b", "strategy": "qlora",
                                           "hyperparameters": {"epochs": 3}})
    assert ExperimentConfiguration.from_dict(c.to_dict()).strategy == "qlora"
    assert Experiment.coerce_status("active") == ExperimentStatus.ACTIVE
    assert Experiment.coerce_status("nonsense") == ExperimentStatus.DRAFT


# ---------------------------------------------------------------------------
# service — create / read / update / notes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_records_timeline_and_snapshot(svc):
    exp = await svc.create(name="exp1", description="first",
                           configuration={"base_model": "llama3:8b", "strategy": "lora"},
                           tags=["baseline"])
    assert exp["status"] == "active"
    assert exp["configuration"]["base_model"] == "llama3:8b"
    assert exp["snapshot"] is not None  # best-effort snapshot always captured
    assert exp["snapshot"]["platform"]  # environment metadata present

    fetched = await svc.get(exp["id"])
    assert fetched["name"] == "exp1" and fetched["tags"] == ["baseline"]

    timeline = await svc.timeline(exp["id"])
    assert any(e["kind"] == "experiment.created" for e in timeline)


@pytest.mark.asyncio
async def test_get_missing_returns_none(svc):
    assert await svc.get("nope") is None


@pytest.mark.asyncio
async def test_list_and_status_filter(svc):
    a = await svc.create(name="a", project_id="p1")
    await svc.create(name="b", project_id="p2")
    await svc.update(a["id"], status="concluded")

    assert len(await svc.list()) == 2
    assert [e["name"] for e in await svc.list(project_id="p1")] == ["a"]
    concluded = await svc.list(status="concluded")
    assert len(concluded) == 1 and concluded[0]["concluded_at"] is not None


@pytest.mark.asyncio
async def test_update_fields_and_tags(svc):
    exp = await svc.create(name="x")
    updated = await svc.update(exp["id"], name="x2", description="d", tags=["t1", "t2"])
    assert updated["name"] == "x2" and updated["description"] == "d"
    assert updated["tags"] == ["t1", "t2"]
    assert await svc.update("missing", name="q") is None


@pytest.mark.asyncio
async def test_notes_add_list_delete(svc):
    exp = await svc.create(name="n")
    note = await svc.add_note(exp["id"], "## observations\nloss plateaued")
    assert note["body"].startswith("## observations")
    assert len(await svc.notes(exp["id"])) == 1
    # a note also lands on the timeline
    assert any(e["kind"] == "note" for e in await svc.timeline(exp["id"]))
    assert await svc.delete_note(note["id"]) is True
    assert await svc.notes(exp["id"]) == []
    assert await svc.add_note("missing", "x") is None


@pytest.mark.asyncio
async def test_delete_cascades(svc):
    exp = await svc.create(name="d")
    await svc.add_note(exp["id"], "keep-notes-away")
    await svc.upsert_job_ref(exp["id"], "job-1", job_type="training", status="running")
    assert await svc.delete(exp["id"]) is True
    assert await svc.get(exp["id"]) is None
    assert await svc.notes(exp["id"]) == []
    assert await svc.jobs(exp["id"]) == []
    assert await svc.delete(exp["id"]) is False


# ---------------------------------------------------------------------------
# service — snapshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_recapture(svc):
    exp = await svc.create(name="s", configuration={"strategy": "lora", "provider": "simulation"})
    snap = await svc.snapshot(exp["id"])
    assert snap is not None and snap["strategy"] == "lora"
    assert any(e["kind"] == "snapshot.captured" for e in await svc.timeline(exp["id"]))
    assert await svc.snapshot("missing") is None


# ---------------------------------------------------------------------------
# service — clone (artifacts NOT duplicated; parent referenced)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clone_copies_config_tags_and_optionally_notes(SessionLocal):
    arts = _FakeArtifactQuery()
    svc = _service(SessionLocal, artifacts=arts)
    parent = await svc.create(name="p", configuration={"base_model": "m", "strategy": "qlora"},
                              tags=["orig"])
    arts.by_experiment[parent["id"]] = [{"id": "a1", "type": "adapter"}]
    await svc.add_note(parent["id"], "parent note")

    clone = await svc.clone(parent["id"], include_notes=True, name="p-clone")
    assert clone["name"] == "p-clone"
    assert clone["parent_experiment_id"] == parent["id"]
    assert clone["configuration"]["strategy"] == "qlora" and clone["tags"] == ["orig"]
    # notes copied when requested
    assert len(await svc.notes(clone["id"])) == 1
    # artifacts are referenced, never duplicated — clone starts with none of its own
    assert await svc.artifacts(clone["id"]) == []
    assert any(e["kind"] == "experiment.cloned" for e in await svc.timeline(clone["id"]))

    bare = await svc.clone(parent["id"])  # include_notes defaults off
    assert await svc.notes(bare["id"]) == []
    assert await svc.clone("missing") is None


# ---------------------------------------------------------------------------
# service — comparison
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_side_by_side(SessionLocal):
    arts = _FakeArtifactQuery()
    svc = _service(SessionLocal, artifacts=arts)
    a = await svc.create(name="A", configuration={"base_model": "m", "strategy": "lora"})
    b = await svc.create(name="B", configuration={"base_model": "m", "strategy": "qlora"})
    arts.by_experiment[a["id"]] = [{"id": "x", "type": "adapter"}, {"id": "y", "type": "checkpoint"}]
    await svc.record_metric(a["id"], "final_loss", 0.42)
    await svc.upsert_job_ref(a["id"], "j1", job_type="training", status="completed")

    result = await svc.compare([a["id"], b["id"], "missing"])
    cols = result["experiments"]
    assert len(cols) == 2  # missing id skipped
    ca = next(c for c in cols if c["id"] == a["id"])
    assert ca["strategy"] == "lora"
    assert ca["artifacts_total"] == 2 and ca["artifact_counts"]["adapter"] == 1
    assert ca["jobs_total"] == 1 and ca["final_loss"] == 0.42


# ---------------------------------------------------------------------------
# event subscriber — engines "publish into" the experiment via the Event Bus
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscriber_job_lifecycle_populates_timeline_and_jobrefs(SessionLocal):
    from app.events import EventBus
    from app.experiments.subscriber import register_experiment_subscribers

    svc = _service(SessionLocal)
    bus = EventBus()
    register_experiment_subscribers(service=svc, bus=bus)

    exp = await svc.create(name="e")
    eid = exp["id"]

    # events with no experiment_id are ignored entirely
    await bus.publish("job.started", {"id": "j0", "type": "training"})
    assert await svc.jobs(eid) == []

    await bus.publish("job.started", {"id": "j1", "type": "training", "experiment_id": eid})
    await bus.publish("job.completed", {"id": "j1", "type": "training", "experiment_id": eid,
                                        "artifacts": ["art-1"]})

    jobs = await svc.jobs(eid)
    assert len(jobs) == 1 and jobs[0]["job_id"] == "j1" and jobs[0]["status"] == "completed"
    kinds = {e["kind"] for e in await svc.timeline(eid)}
    assert {"job.started", "job.completed"} <= kinds


@pytest.mark.asyncio
async def test_subscriber_records_training_metrics_and_artifacts(SessionLocal):
    from app.events import EventBus
    from app.experiments.subscriber import register_experiment_subscribers

    svc = _service(SessionLocal)
    bus = EventBus()
    register_experiment_subscribers(service=svc, bus=bus)
    exp = await svc.create(name="e")
    eid = exp["id"]

    await bus.publish("training.completed", {"run_id": "r1", "experiment_id": eid,
                                             "final_loss": 0.13, "duration_seconds": 12.5})
    await bus.publish("training.checkpoint_saved", {"run_id": "r1", "experiment_id": eid, "step": 50})
    await bus.publish("artifact.published", {"id": "adp", "type": "adapter", "experiment_id": eid})

    fetched = await svc.get(eid)
    assert fetched["metrics"]["final_loss"] == 0.13
    assert fetched["metrics"]["training_duration_seconds"] == 12.5
    kinds = {e["kind"] for e in await svc.timeline(eid)}
    assert {"checkpoint.created", "artifact.published"} <= kinds


@pytest.mark.asyncio
async def test_jobref_upsert_is_idempotent(svc):
    exp = await svc.create(name="e")
    await svc.upsert_job_ref(exp["id"], "j", job_type="export", status="running")
    await svc.upsert_job_ref(exp["id"], "j", job_type="export", status="completed")
    jobs = await svc.jobs(exp["id"])
    assert len(jobs) == 1 and jobs[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(SessionLocal, monkeypatch):
    import app.api.experiments as api_mod
    arts = _FakeArtifactQuery()
    monkeypatch.setattr(api_mod, "experiment_service", _service(SessionLocal, artifacts=arts))
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c._arts = arts  # type: ignore[attr-defined]
        yield c


@pytest.mark.asyncio
async def test_api_crud_lifecycle(client):
    created = await client.post("/api/experiments", json={
        "name": "api-exp", "description": "d",
        "configuration": {"base_model": "llama3:8b", "strategy": "lora"}, "tags": ["t"]})
    assert created.status_code == 201
    eid = created.json()["id"]

    assert (await client.get(f"/api/experiments/{eid}")).json()["name"] == "api-exp"
    assert (await client.get("/api/experiments/missing")).status_code == 404

    listed = (await client.get("/api/experiments")).json()
    assert any(e["id"] == eid for e in listed)

    patched = await client.patch(f"/api/experiments/{eid}", json={"status": "concluded", "tags": ["z"]})
    assert patched.json()["status"] == "concluded" and patched.json()["tags"] == ["z"]

    deleted = await client.delete(f"/api/experiments/{eid}")
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True
    assert (await client.delete(f"/api/experiments/{eid}")).status_code == 404


@pytest.mark.asyncio
async def test_api_notes_timeline_snapshot(client):
    eid = (await client.post("/api/experiments", json={"name": "e"})).json()["id"]

    note = await client.post(f"/api/experiments/{eid}/notes", json={"body": "hello"})
    assert note.status_code == 201
    assert len((await client.get(f"/api/experiments/{eid}/notes")).json()) == 1

    assert (await client.post(f"/api/experiments/{eid}/snapshot")).status_code == 200
    timeline = (await client.get(f"/api/experiments/{eid}/timeline")).json()
    assert any(e["kind"] == "experiment.created" for e in timeline)


@pytest.mark.asyncio
async def test_api_clone_artifacts_jobs(client):
    eid = (await client.post("/api/experiments", json={
        "name": "src", "configuration": {"strategy": "qlora"}})).json()["id"]
    client._arts.by_experiment[eid] = [{"id": "a1", "type": "adapter"}]

    arts = (await client.get(f"/api/experiments/{eid}/artifacts")).json()
    assert len(arts) == 1 and arts[0]["type"] == "adapter"
    assert (await client.get(f"/api/experiments/{eid}/jobs")).json() == []

    clone = await client.post(f"/api/experiments/{eid}/clone", json={"name": "dst"})
    assert clone.status_code == 201
    body = clone.json()
    assert body["parent_experiment_id"] == eid and body["configuration"]["strategy"] == "qlora"
    assert (await client.post("/api/experiments/missing/clone", json={})).status_code == 404


@pytest.mark.asyncio
async def test_api_compare(client):
    a = (await client.post("/api/experiments", json={"name": "A"})).json()["id"]
    b = (await client.post("/api/experiments", json={"name": "B"})).json()["id"]
    resp = await client.get(f"/api/experiments/compare?ids={a},{b}")
    assert resp.status_code == 200 and len(resp.json()["experiments"]) == 2
    assert (await client.get("/api/experiments/compare?ids=")).status_code == 400
