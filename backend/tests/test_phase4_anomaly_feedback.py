"""Phase 4 local anomaly and reviewed trace-feedback safety checks."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.anomaly_monitor import evaluate_rule, scan_due
from app.db.database import Base, get_db
from app.db.models import (AnomalyAlert, AnomalyRule, Dataset, DatasetVersion,
    EvaluationCollection, EvaluationResult, FeedbackCase, Project, Prompt, PromptSet,
    PromptVersion, TraceEvent, WorkbenchSession)
from app.main import app
from app.jobs.domain import Job
from app.jobs.handlers import JobContext
from app.feedback_retention import cleanup_expired_feedback


@pytest.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as con:
        await con.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project, other, set_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as db:
        db.add_all([Project(id=project, name="A", models=[], datasets=[], settings={}),
                    Project(id=other, name="B", models=[], datasets=[], settings={})])
        col = EvaluationCollection(id=str(uuid.uuid4()), project_id=project, name="Evaluation")
        db.add(col)
        await db.flush()
        db.add(PromptSet(id=set_id, collection_id=col.id, project_id=project, title="Regression"))
        db.add(TraceEvent(project_id=project, event_id="event-1", status="error",
                          trace_id="trace-1", input_text="hello sk-1234567890abcdef",
                          provider="ollama", model="tiny", received_at=datetime.now(timezone.utc)))
        await db.commit()

    async def override():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        yield client, factory, project, other, set_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_sparse_threshold_dedup_cooldown_and_state(env):
    client, factory, project, other, _ = env
    base = f"/api/projects/{project}"
    rule = {"name": "Error spike", "metric": "error_rate", "threshold": 30,
            "min_samples": 3, "observed_minutes": 10, "cooldown_seconds": 60}
    created = await client.post(f"{base}/anomaly-rules", json=rule)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    dry = (await client.post(f"{base}/anomaly-rules/{rid}/dry-run")).json()
    assert dry["status"] == "insufficient_data"
    assert (await client.get(f"/api/projects/{other}/anomaly-rules")).json()["items"] == []
    now = datetime.now(timezone.utc)
    async with factory() as db:
        for i in range(2):
            db.add(TraceEvent(project_id=project, event_id=f"more-{i}", status="error",
                              received_at=now - timedelta(minutes=1)))
        await db.commit()
        result = await scan_due(db, at=now)
        assert result["created"] == 1
        alerts = (await db.execute(select(AnomalyAlert))).scalars().all()
        assert len(alerts) == 1 and alerts[0].classification == "observed"
        aid = alerts[0].id
        r = await db.get(AnomalyRule, rid)
        r.next_check_at = now
        await db.commit()
        again = await scan_due(db, at=now + timedelta(seconds=1))
        assert again["created"] == 0
        assert len((await db.execute(select(AnomalyAlert))).scalars().all()) == 1
    async with factory() as db:
        r = await db.get(AnomalyRule, rid)
        r.next_check_at = now + timedelta(seconds=61)
        await db.commit()
    async with factory() as db:
        later = await scan_due(db, at=now + timedelta(seconds=61))
        assert later["created"] == 0
        assert (await db.get(AnomalyAlert, aid)).occurrences == 2
    changed = await client.post(f"{base}/alerts/{aid}/state", json={"state": "acknowledged", "confirm_incident": True})
    assert changed.json()["classification"] == "incident"
    assert (await client.post(f"{base}/alerts/{aid}/state", json={"state": "resolved"})).status_code == 200
    assert (await client.post(f"{base}/alerts/{aid}/state", json={"state": "acknowledged"})).status_code == 409


@pytest.mark.asyncio
async def test_feedback_privacy_review_provenance_and_versioned_dataset(env):
    client, factory, project, other, set_id = env
    base = f"/api/projects/{project}/feedback/cases"
    req = {"event_id": "event-1", "category": "incorrect_output", "title": "Wrong answer"}
    made = await client.post(base, json=req)
    assert made.status_code == 201, made.text
    case_id = made.json()["id"]
    assert made.json()["prompt_text"] is None
    assert made.json()["source_event_id"] == "event-1"
    assert (await client.post(base, json=req)).status_code == 409
    assert (await client.get(f"/api/projects/{other}/feedback/cases/{case_id}")).status_code == 404
    assert (await client.get(f"{base}/{case_id}?include_bodies=true")).status_code == 403
    assert (await client.post(base, json={**req, "category": "security_concern", "include_captured_input": True})).status_code == 403
    edited = await client.put(f"{base}/{case_id}", json={"title": "Wrong answer", "prompt_text": "Say hello",
        "expected_output": "Hello", "labels": ["regression"], "acceptance_criteria": {"min_similarity": 60}})
    assert edited.status_code == 200, edited.text
    assert edited.json()["prompt_text"] is None
    assert (await client.get(f"{base}/{case_id}", params={"include_bodies": True},
        headers={"X-RedForge-Sensitive-Access": "allow"})).json()["prompt_text"] == "Say hello"
    assert (await client.post(f"{base}/{case_id}/approve", json={"prompt_set_id": set_id})).status_code == 409
    assert (await client.post(f"{base}/{case_id}/state", json={"state": "in_review"})).status_code == 200
    approved = await client.post(f"{base}/{case_id}/approve", json={"prompt_set_id": set_id})
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    assert (await client.put(f"{base}/{case_id}", json={"title": "Changed"})).status_code == 409
    async with factory() as db:
        case = await db.get(FeedbackCase, case_id)
        prompt = await db.get(Prompt, case.evaluation_prompt_id)
        assert prompt.prompt == "Say hello"
        version = (await db.execute(select(PromptVersion).where(PromptVersion.prompt_id == prompt.id))).scalar_one()
        assert version.snapshot["prompt"] == "Say hello"
        dataset = await db.get(Dataset, case.dataset_id)
        assert dataset.current_version == 1
        manifest = (await db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id))).scalar_one()
        assert manifest.records[0]["source_event_id"] == "event-1"
        trace = (await db.execute(select(TraceEvent).where(TraceEvent.event_id == "event-1"))).scalar_one()
        assert trace.input_text == "hello sk-1234567890abcdef"  # unchanged source


@pytest.mark.asyncio
async def test_baseline_cold_start_and_project_isolation(env):
    _, factory, project, other, _ = env
    now = datetime.now(timezone.utc)
    async with factory() as db:
        rule = AnomalyRule(id=str(uuid.uuid4()), project_id=project, name="Rate shift",
            metric="error_rate", threshold=10, baseline_multiplier=2,
            min_samples=1, observed_minutes=10, baseline_minutes=30,
            interval_seconds=60, cooldown_seconds=60, severity="warning", enabled=True)
        db.add(rule)
        db.add(TraceEvent(project_id=other, event_id="other", status="success", received_at=now))
        await db.commit()
        result = await evaluate_rule(db, rule, at=now + timedelta(seconds=1))
        assert result["status"] == "insufficient_data" and "baseline" in result["reason"]


@pytest.mark.asyncio
async def test_provider_dry_run_never_probes_network(env, monkeypatch):
    from app.health.service import health_service
    client, factory, project, _, _ = env
    async def forbidden(_):
        raise AssertionError("dry run made a provider request")
    monkeypatch.setattr(health_service, "get_check", forbidden)
    payload = {"name": "Availability", "metric": "provider_availability", "threshold": 100}
    assert (await client.post(f"/api/projects/{project}/anomaly-rules", json=payload)).status_code == 422
    created = await client.post(f"/api/projects/{project}/anomaly-rules", json={**payload, "min_samples": 1})
    assert created.status_code == 201
    dry = await client.post(f"/api/projects/{project}/anomaly-rules/{created.json()['id']}/dry-run")
    assert dry.json()["status"] == "insufficient_data"
    rule = AnomalyRule(id=str(uuid.uuid4()), project_id=project, name="Provider",
        metric="provider_availability", threshold=100, min_samples=1,
        observed_minutes=1, baseline_minutes=60, interval_seconds=60,
        cooldown_seconds=60, severity="critical", enabled=True)
    async with factory() as db:
        result = await evaluate_rule(db, rule, allow_health_probe=False)
        assert result["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_unapproved_feedback_retention_is_bounded_and_audited(env):
    _, factory, project, _, _ = env
    old = datetime.now(timezone.utc) - timedelta(days=31)
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as db:
        for cid, state in ((first, "draft"), (second, "approved")):
            db.add(FeedbackCase(id=cid, project_id=project, trace_event_id=1,
                source_event_id=f"source-{cid}", fingerprint=uuid.uuid4().hex,
                category="incorrect_output", state=state, title="Sensitive title",
                notes="Sensitive notes", prompt_text="Sensitive prompt", expected_output="Sensitive output",
                labels=["sensitive"], acceptance_criteria={}, created_at=old))
        await db.commit()
        assert await cleanup_expired_feedback(db, batch_size=1) == 1
        draft = await db.get(FeedbackCase, first)
        approved = await db.get(FeedbackCase, second)
        assert draft.state == "archived" and draft.prompt_text is None
        assert draft.title == "Expired feedback case" and draft.labels == []
        assert approved.state == "approved" and approved.prompt_text == "Sensitive prompt"


def test_local_replay_rejects_remote_or_hosted_runtime(monkeypatch):
    from types import SimpleNamespace
    from app.feedback_replay import local_runtime_ready
    from app.config import settings
    from app.runtime import manager
    monkeypatch.setattr(settings, "RUNTIME_PROVIDER", "ollama")
    monkeypatch.setattr(manager, "get_runtime", lambda: SimpleNamespace(provider=SimpleNamespace(
        name="ollama", base_url="https://outside.example")))
    assert not local_runtime_ready()
    monkeypatch.setattr(manager, "get_runtime", lambda: SimpleNamespace(provider=SimpleNamespace(
        name="ollama", base_url="http://127.0.0.1:11434")))
    assert local_runtime_ready()
    monkeypatch.setattr(settings, "RUNTIME_PROVIDER", "openai")
    assert not local_runtime_ready()


@pytest.mark.asyncio
async def test_replay_budget_cancel_and_ungraded_without_ground_truth(env, monkeypatch):
    from app import feedback_replay
    _, factory, project, _, set_id = env
    case_id, prompt_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as db:
        p = Prompt(id=prompt_id, prompt_set_id=set_id, title="Safe test", prompt="Say hello",
                   expected_output="", acceptance_criteria={}, current_version=1, active_version=1)
        db.add(p)
        db.add(PromptVersion(prompt_id=prompt_id, version=1,
                             snapshot={"prompt": "Say hello", "expected_output": "", "acceptance_criteria": {}}))
        db.add(FeedbackCase(id=case_id, project_id=project, trace_event_id=1,
            fingerprint=uuid.uuid4().hex, category="incorrect_output", state="approved",
            title="Case", evaluation_prompt_id=prompt_id, labels=[], acceptance_criteria={}))
        await db.commit()
    monkeypatch.setattr(feedback_replay, "AsyncSessionLocal", factory)
    monkeypatch.setattr(feedback_replay, "local_runtime_ready", lambda: True)
    calls = []
    async def fake_generate(model, prompt, *, options):
        calls.append((model, prompt, options))
        return {"response": "Hello", "latency_ms": 2, "total_tokens": 3}
    monkeypatch.setattr(feedback_replay, "_runtime_generate_rich", fake_generate)
    params = {"case_id": case_id, "environment": "local_evaluation", "candidate_model": "tiny",
              "baseline_model": None, "timeout_seconds": 2, "max_calls": 1}
    job = Job(id=str(uuid.uuid4()), type="feedback_replay", project_id=project, params=params)
    cancelled = await feedback_replay.handle_feedback_replay(job, JobContext(job, is_cancelled=lambda: True))
    assert not cancelled.success and not calls
    invalid = Job(id=str(uuid.uuid4()), type="feedback_replay", project_id=project,
                  params={**params, "environment": "production"})
    assert not (await feedback_replay.handle_feedback_replay(invalid, JobContext(invalid))).success
    result = await feedback_replay.handle_feedback_replay(job, JobContext(job))
    assert result.success and result.data["verdict"] == "ungraded"
    assert result.data["calls"] == 1 and result.data["external_cost_usd"] == 0
    assert calls == [("tiny", "Say hello", {"num_predict": 512})]
    assert "Hello" not in str(result.data)  # response body never enters Job result
    async with factory() as db:
        session = await db.get(WorkbenchSession, result.data["evaluation_session_id"])
        stored = (await db.execute(select(EvaluationResult).where(
            EvaluationResult.session_id == session.id))).scalars().all()
        assert session.project_id == project and session.summary["responses_omitted"]
        assert len(stored) == 1 and stored[0].response == ""
    comparison = Job(id=str(uuid.uuid4()), type="feedback_replay", project_id=project,
                     params={**params, "baseline_model": "baseline", "max_calls": 2})
    compared = await feedback_replay.handle_feedback_replay(comparison, JobContext(comparison))
    assert compared.success and compared.data["similarity_score"] == 100
    assert compared.data["verdict"] == "ungraded"  # comparison is not ground truth
