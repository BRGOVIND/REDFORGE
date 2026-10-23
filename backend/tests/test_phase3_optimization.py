"""Phase 3 comparisons, opt-in routing, explicit prices and bounded accounting."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import routing
from app.config import settings
from app.anomaly_monitor import scan_due
from app.cost_control import calculated_cost
from app.db.database import Base, get_db
from app.db.models import (EvaluationCollection, ModelPrice, Project, Prompt, PromptSet,
                           PromptVersion, TraceEvent)
from app.evaluation import evaluation_sessions
from app.evaluation.versioning import snapshot_of
from app.main import app


@pytest.fixture(autouse=True)
def connected_profile(monkeypatch):
    """Existing hosted-routing cases cover explicitly connected deployments."""
    monkeypatch.setattr(settings, "NETWORK_PROFILE", "connected")


@pytest.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project, other = str(uuid.uuid4()), str(uuid.uuid4())
    collection, prompt_set, prompt_id = (str(uuid.uuid4()) for _ in range(3))
    async with factory() as db:
        db.add_all([Project(id=project, name="Phase 3", models=[], datasets=[], settings={}),
                    Project(id=other, name="Other", models=[], datasets=[], settings={}),
                    EvaluationCollection(id=collection, project_id=project, name="Checks"),
                    PromptSet(id=prompt_set, collection_id=collection, project_id=project, title="Small dataset")])
        prompt = Prompt(id=prompt_id, prompt_set_id=prompt_set, title="Greeting",
                        prompt="Say hello", expected_output="hello", enabled=1,
                        current_version=1, active_version=1)
        db.add(prompt)
        db.add(PromptVersion(prompt_id=prompt_id, version=1, snapshot=snapshot_of(prompt),
                             content_hash="a" * 64))
        await db.commit()

    async def override():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    old_factory = evaluation_sessions._session_factory
    old_auto = evaluation_sessions._auto_worker
    old_generate = evaluation_sessions._generate_fn
    evaluation_sessions._session_factory = factory
    evaluation_sessions._auto_worker = False
    evaluation_sessions._queue.clear()
    evaluation_sessions._cancelled.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        yield client, factory, project, other, prompt_set
    app.dependency_overrides.clear()
    evaluation_sessions._session_factory = old_factory
    evaluation_sessions._auto_worker = old_auto
    evaluation_sessions._generate_fn = old_generate
    evaluation_sessions._queue.clear()
    evaluation_sessions._cancelled.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_versioned_price_trace_cost_and_deduplicated_usage(env):
    client, factory, project, other, _ = env
    base = f"/api/projects/{project}/costs"
    now = datetime.now(timezone.utc)
    payload = {"provider": "openai", "model": "example-1", "effective_at": (now - timedelta(days=2)).isoformat(),
               "source": "operator-verified price sheet", "input_usd_per_million": 2,
               "output_usd_per_million": 8, "cached_input_usd_per_million": 1}
    first = await client.post(f"{base}/prices", json=payload)
    assert first.status_code == 201, first.text
    second = await client.post(f"{base}/prices", json={**payload,
        "effective_at": (now - timedelta(days=1)).isoformat(), "output_usd_per_million": 10})
    assert second.status_code == 201 and second.json()["version"] == 2
    assert (await client.get(f"/api/projects/{other}/costs/prices")).json() == []
    token = (await client.post(f"/api/projects/{project}/trace-tokens")).json()["token"]
    events = {"events": [{"event_id": f"cost-{n}", "request_id": "one-logical-call", "status": "success",
        "provider": "openai", "model": "example-1", "input_tokens": 1000,
        "cached_input_tokens": 200, "output_tokens": 100,
        "usage_source": "provider", "started_at": now.isoformat()} for n in (1, 2)]}
    ingested = await client.post("/api/v1/traces/events", json=events,
                                 headers={"Authorization": f"Bearer {token}"})
    assert ingested.status_code == 202, ingested.text
    async with factory() as db:
        stored = (await db.execute(select(TraceEvent).where(TraceEvent.project_id == project))).scalars().all()
        assert len(stored) == 2
        assert stored[0].pricing_record_id == second.json()["id"]
        assert stored[0].cost_source == "configured"
        assert stored[0].cost_usd == pytest.approx((800 * 2 + 200 * 1 + 100 * 10) / 1_000_000)
    usage = await client.get(f"{base}/usage", params={"group_by": "model",
        "start": (now - timedelta(days=1)).isoformat(),
        "end": (now + timedelta(days=1)).isoformat()})
    assert usage.status_code == 200, usage.text
    assert usage.json()["rows"][0]["calls"] == 1
    assert usage.json()["rows"][0]["cost_usd"] == pytest.approx(stored[0].cost_usd)
    assert (await client.get(f"{base}/usage", params={"start": (now - timedelta(days=200)).isoformat()})).status_code == 422
    budget = await client.put(f"{base}/budget", json={"period": "daily", "soft_limit_usd": 0.001})
    assert budget.status_code == 200, budget.text
    async with factory() as db:
        alert = await scan_due(db)
        assert alert["created"] == 1
    assert (await client.get(f"/api/projects/{project}/alerts")).status_code == 200


@pytest.mark.asyncio
async def test_plan_is_frozen_project_scoped_and_progressive(env):
    client, factory, project, other, prompt_set = env
    async def fake_generate(model, prompt, *, system=None, options=None):
        return {"response": "hello", "latency_ms": 12, "prompt_tokens": 3, "completion_tokens": 2}
    evaluation_sessions._generate_fn = fake_generate
    base = f"/api/projects/{project}/comparisons"
    payload = {"name": "Local compare", "prompt_set_id": prompt_set,
               "candidates": [{"provider": "ollama", "model": "small-a"},
                              {"provider": "ollama", "model": "small-b"}],
               "concurrency_limit": 2}
    bad = await client.post(base, json={**payload, "candidates": [payload["candidates"][0]]})
    assert bad.status_code == 422
    created = await client.post(base, json=payload)
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    assert created.json()["snapshot"]["dataset"]["prompts"]
    assert (await client.get(f"/api/projects/{other}/comparisons/{plan_id}")).status_code == 404
    started = await client.post(f"{base}/{plan_id}/start", json={})
    assert started.status_code == 200, started.text
    assert (await client.post(f"{base}/{plan_id}/start", json={})).status_code == 409
    await evaluation_sessions.drain()
    plan = (await client.get(f"{base}/{plan_id}")).json()
    assert plan["status"] == "completed" and plan["progress"] == {"completed": 2, "total": 2}
    results = (await client.get(f"{base}/{plan_id}/results")).json()["results"]
    assert len(results) == 2 and {r["provider"] for r in results} == {"ollama"}
    assert all(r["verdict"] == "pass" for r in results)
    exported = await client.get(f"{base}/{plan_id}/results?format=csv")
    assert exported.status_code == 200 and "small-a" in exported.text


@pytest.mark.asyncio
async def test_routing_disabled_fixed_and_remote_guard(env, monkeypatch):
    client, factory, project, other, _ = env
    base = f"/api/projects/{project}/routing"
    assert (await client.post(f"{base}/execute", json={"prompt": "hello"})).status_code == 409
    created = await client.post(f"{base}/policies", json={"name": "Local first", "mode": "fixed",
        "candidates": [{"provider": "ollama", "model": "small"}]})
    assert created.status_code == 201, created.text
    policy_id = created.json()["id"]
    assert (await client.put(f"/api/projects/{other}/routing/active/{policy_id}")).status_code == 404
    assert (await client.put(f"{base}/active/{policy_id}")).status_code == 200
    async def generated(*args, **kwargs):
        return SimpleNamespace(text="hello", prompt_eval_count=2, eval_count=3,
            cached_input_tokens=None, reasoning_tokens=None)
    monkeypatch.setattr(routing, "get_runtime_for", lambda name: SimpleNamespace(generate=generated))
    response = await client.post(f"{base}/execute", json={"prompt": "hello"})
    assert response.status_code == 200, response.text
    assert response.json()["output"] == "hello"
    assert response.json()["attempts"][0]["provider"] == "ollama"
    async with factory() as db:
        rows = (await db.execute(select(TraceEvent).where(TraceEvent.project_id == project))).scalars().all()
        assert len(rows) == 1 and rows[0].input_text is None
    assert (await client.delete(f"{base}/active")).status_code == 200
    assert (await client.post(f"{base}/execute", json={"prompt": "hello"})).status_code == 409
    remote = await client.post(f"{base}/policies", json={"name": "Remote", "mode": "fixed",
        "candidates": [{"provider": "openai", "model": "example-1"}], "remote_enabled": True,
        "max_estimated_cost_usd": 1})
    assert remote.status_code == 201, remote.text
    assert (await client.put(f"{base}/active/{remote.json()['id']}")).status_code == 200
    assert (await client.post(f"{base}/execute", json={"prompt": "sensitive"})).status_code == 409
    assert (await client.put(f"/api/projects/{project}/costs/budget", json={
        "period": "monthly", "soft_limit_usd": 1, "hard_limit_usd": 2})).status_code == 200
    blocked = await client.post(f"{base}/execute", json={"prompt": "sensitive",
        "allow_remote": True, "confirm_sensitive_remote": True})
    assert blocked.status_code == 409 and "Hard budget" in blocked.text


@pytest.mark.asyncio
async def test_ordered_fallback_preserves_first_failure(env, monkeypatch):
    client, _, project, _, _ = env
    base = f"/api/projects/{project}/routing"
    created = await client.post(f"{base}/policies", json={"name": "Fallback", "mode": "fallback",
        "candidates": [{"provider": "ollama", "model": "first"},
                       {"provider": "lmstudio", "model": "second"}], "max_attempts": 2})
    assert created.status_code == 201, created.text
    await client.put(f"{base}/active/{created.json()['id']}")
    async def generate(model, prompt, **kwargs):
        if model == "first":
            raise RuntimeError("first failed")
        return SimpleNamespace(text="second worked", prompt_eval_count=3, eval_count=4,
                               cached_input_tokens=None, reasoning_tokens=None)
    monkeypatch.setattr(routing, "get_runtime_for", lambda name: SimpleNamespace(generate=generate))
    response = await client.post(f"{base}/execute", json={"prompt": "hello"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output"] == "second worked"
    assert body["original_error"] == "RuntimeError: first failed"
    assert [a["status"] for a in body["attempts"]] == ["error", "success"]


@pytest.mark.asyncio
async def test_threshold_route_requires_recent_measured_evidence(env, monkeypatch):
    client, factory, project, _, _ = env
    base = f"/api/projects/{project}/routing"
    created = await client.post(f"{base}/policies", json={"name": "Measured local", "mode": "threshold",
        "candidates": [{"provider": "ollama", "model": "small"}],
        "max_observed_latency_ms": 100, "min_samples": 5})
    assert created.status_code == 201, created.text
    await client.put(f"{base}/active/{created.json()['id']}")
    empty = await client.post(f"{base}/execute", json={"prompt": "hello"})
    assert empty.status_code == 409 and "enough recent measured evidence" in empty.text
    async with factory() as db:
        db.add_all([TraceEvent(project_id=project, event_id=f"measured-{n}",
            received_at=datetime.now(timezone.utc) - timedelta(minutes=1), provider="ollama", model="small",
            status="success", duration_ms=12) for n in range(5)])
        await db.commit()
        metrics = await routing.recent_candidate_metrics(db, project, "ollama", "small")
        assert metrics["sample_count"] == 5, metrics
    async def generated(*args, **kwargs):
        return SimpleNamespace(text="measured", prompt_eval_count=2, eval_count=2,
            cached_input_tokens=None, reasoning_tokens=None)
    monkeypatch.setattr(routing, "get_runtime_for", lambda name: SimpleNamespace(generate=generated))
    response = await client.post(f"{base}/execute", json={"prompt": "hello"})
    assert response.status_code == 200, response.text
    assert response.json()["evidence"][0]["metrics"]["sample_count"] == 5
    assert response.json()["evidence"][0]["eligible"] is True


def test_cost_categories_are_not_double_counted():
    price = SimpleNamespace(rates={"input": 2, "output": 8, "cached_input": 1, "reasoning": 10})
    cost = calculated_cost({"input_tokens": 100, "cached_input_tokens": 20,
                            "output_tokens": 50, "reasoning_tokens": 10}, price)
    assert cost == pytest.approx((80 * 2 + 20 * 1 + 40 * 8 + 10 * 10) / 1_000_000)
    assert calculated_cost({"input_tokens": 10, "output_tokens": None}, price) is None
