"""Phase 2: immutable prompt workflow and server-enforced trace privacy."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.db.models import EvaluationCollection, GovernanceAuditEvent, Project, Prompt, PromptSet, PromptVersion, TraceEvent
from app.main import app
from app.observability_privacy import cleanup_expired


@pytest.fixture
async def phase2_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    project_a, project_b = str(uuid.uuid4()), str(uuid.uuid4())
    set_id = str(uuid.uuid4())
    async with factory() as db:
        db.add_all([
            Project(id=project_a, name="A", models=[], datasets=[], settings={}),
            Project(id=project_b, name="B", models=[], datasets=[], settings={}),
            EvaluationCollection(id=str(uuid.uuid4()), project_id=project_a, name="Prompts"),
        ])
        await db.flush()
        col = (await db.execute(select(EvaluationCollection))).scalars().first()
        db.add(PromptSet(id=set_id, collection_id=col.id, project_id=project_a, title="Set"))
        await db.commit()

    async def override():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        yield client, factory, project_a, project_b, set_id
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_publish_diff_rollback_render_import_and_isolation(phase2_env):
    client, factory, project, other, set_id = phase2_env
    base = f"/api/v1/projects/{project}/prompt-registry"
    first = {"title": "Answer", "prompt": "Hello {{ name }}", "variables_schema": [{"name": "name"}],
             "description": "A greeting", "tags": ["greeting"]}
    created = await client.post(base, json={"prompt_set_id": set_id, "definition": first, "author": "Ada"})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["current_version"] == 0
    assert (await client.post(f"{base}/{pid}/render", json={"variables": {"name": "Jo"}})).status_code == 409
    published = await client.post(f"{base}/{pid}/publish", json={"note": "initial", "author": "Ada"})
    assert published.status_code == 200, published.text
    assert published.json()["active_version"] == 1
    assert (await client.post(f"{base}/{pid}/render", json={"variables": {}})).status_code == 422
    assert (await client.post(f"{base}/{pid}/render", json={"variables": {"name": 3}})).status_code == 422
    rendered = await client.post(f"{base}/{pid}/render", json={"variables": {"name": "Jo"}})
    assert rendered.json()["prompt"] == "Hello Jo"
    assert (await client.get(f"/api/v1/projects/{other}/prompt-registry/{pid}")).status_code == 404
    second = {**first, "prompt": "Hi {{ name }}"}
    assert (await client.put(f"{base}/{pid}/draft", json={"definition": second, "author": "Ada"})).status_code == 200
    # Published v1 remains unchanged while draft is edited.
    assert (await client.post(f"{base}/{pid}/render", json={"variables": {"name": "Jo"}})).json()["prompt"] == "Hello Jo"
    assert (await client.post(f"{base}/{pid}/publish", json={"note": "shorter"})).json()["current_version"] == 2
    diff = (await client.get(f"{base}/{pid}/compare?a=1&b=2")).json()
    assert diff["diff"]["prompt"] == {"a": "Hello {{ name }}", "b": "Hi {{ name }}"}
    assert diff["changed_fields"] == ["prompt"]
    assert (await client.post(f"{base}/{pid}/activate/1")).json()["active_version"] == 1
    assert (await client.post(f"{base}/{pid}/render", json={"variables": {"name": "Jo"}})).json()["prompt"] == "Hello Jo"
    listed = (await client.get(base, params={"tag": "greeting"})).json()
    assert [x["id"] for x in listed["items"]] == [pid]
    assert (await client.get(f"{base}/{pid}/export")).status_code == 403
    exported = (await client.get(f"{base}/{pid}/export",
        headers={"X-RedForge-Sensitive-Access": "allow"})).json()
    assert exported["format"] == "redforge.prompt/1" and len(exported["versions"]) == 2
    imported_copy = await client.post(f"{base}/import", json={"prompt_set_id": set_id,
        "definition": {**exported, "id": str(uuid.uuid4())}})
    assert imported_copy.status_code == 201 and imported_copy.json()["current_version"] == 2
    collision = await client.post(f"{base}/import", json={"prompt_set_id": set_id, "definition": exported})
    assert collision.status_code == 409
    invalid_versions = await client.post(f"{base}/import", json={"prompt_set_id": set_id,
        "definition": {**exported, "id": str(uuid.uuid4()), "versions": [{**exported["versions"][0], "version": 2}]}})
    assert invalid_versions.status_code == 422
    imported = await client.post(f"{base}/import", json={"prompt_set_id": set_id,
        "definition": exported, "confirm_existing": True})
    assert imported.status_code == 201 and imported.json()["current_version"] == 3
    assert (await client.delete(f"{base}/{pid}")).status_code == 403
    assert (await client.delete(f"{base}/{pid}",
        headers={"X-RedForge-Confirm-Action": "archive"})).status_code == 200
    assert (await client.post(f"{base}/{pid}/publish", json={})).status_code == 409
    async with factory() as db:
        versions = (await db.execute(select(PromptVersion).where(PromptVersion.prompt_id == pid)
                                     .order_by(PromptVersion.version))).scalars().all()
        assert [v.snapshot["prompt"] for v in versions] == ["Hello {{ name }}", "Hi {{ name }}", "Hello {{ name }}"]
        actions = (await db.execute(select(GovernanceAuditEvent.action).where(GovernanceAuditEvent.project_id == project))).scalars().all()
        assert {"prompt.published", "prompt.activated", "prompt.imported", "prompt.archived"} <= set(actions)
    malicious = await client.post(base, json={"prompt_set_id": set_id, "definition": {
        "title": "Unsafe", "prompt": '{{ __import__("os").system("echo bad") }}'}})
    assert malicious.status_code == 422


@pytest.mark.asyncio
async def test_workbench_freezes_version_and_validates_variables(phase2_env):
    from app.evaluation.service import EvaluationSessionService
    client, factory, project, _, set_id = phase2_env
    base = f"/api/v1/projects/{project}/prompt-registry"
    definition = {"title": "Greeting", "prompt": "First {{ name }}", "variables_schema": [{"name": "name"}]}
    pid = (await client.post(base, json={"prompt_set_id": set_id, "definition": definition})).json()["id"]
    await client.post(f"{base}/{pid}/publish", json={})
    await client.put(f"{base}/{pid}/draft", json={"definition": {**definition, "prompt": "Second {{ name }}"}})
    await client.post(f"{base}/{pid}/publish", json={})
    seen = []
    async def generate(model, prompt, *, system=None, options=None):
        seen.append(prompt)
        return {"response": prompt}
    svc = EvaluationSessionService(generate_fn=generate, session_factory=factory, auto_worker=False)
    with pytest.raises(ValueError, match="Missing variable"):
        await svc.schedule(models=[{"target_model": "test"}], prompt_set_ids=[set_id], project_id=project)
    scheduled = await svc.schedule(models=[{"target_model": "test"}], prompt_set_ids=[set_id], project_id=project,
        config={"prompt_variables": {pid: {"name": "Jo"}}})
    await client.post(f"{base}/{pid}/activate/1")
    async with factory() as db:
        row = await db.get(Prompt, pid)
        row.enabled = 0
        await db.commit()
    later = (await client.post(base, json={"prompt_set_id": set_id,
        "definition": {"title": "Later", "prompt": "Should not run"}})).json()["id"]
    await client.post(f"{base}/{later}/publish", json={})
    await svc.drain()
    results = await svc.results(scheduled["id"])
    assert seen == ["Second Jo"] and results[0]["prompt_version"] == 2
    event_id = str(uuid.uuid4())
    token = (await client.post(f"/api/projects/{project}/trace-tokens")).json()["token"]
    await client.post("/api/v1/traces/events", headers={"Authorization": "Bearer " + token}, json={"events": [{
        "event_id": event_id, "status": "success", "prompt_template_id": pid, "prompt_version_id": "2"
    }]})
    links = (await client.get(f"{base}/{pid}/links")).json()
    assert links["traces"][0]["event_id"] == event_id
    assert links["evaluations"][0]["version"] == 2


@pytest.mark.asyncio
async def test_empty_scheduled_run_does_not_pick_up_later_prompts(phase2_env):
    from app.evaluation.service import EvaluationSessionService

    client, factory, project, _, set_id = phase2_env
    seen = []
    async def generate(model, prompt, *, system=None, options=None):
        seen.append(prompt)
        return {"response": prompt}
    service = EvaluationSessionService(generate_fn=generate, session_factory=factory, auto_worker=False)
    scheduled = await service.schedule(models=[{"target_model": "test"}],
        prompt_set_ids=[set_id], project_id=project)
    base = f"/api/v1/projects/{project}/prompt-registry"
    prompt_id = (await client.post(base, json={"prompt_set_id": set_id,
        "definition": {"title": "Later", "prompt": "New prompt"}})).json()["id"]
    await client.post(f"{base}/{prompt_id}/publish", json={})
    await service.drain()
    assert seen == [] and await service.results(scheduled["id"]) == []


@pytest.mark.asyncio
async def test_privacy_capture_modes_redaction_retention_and_access(phase2_env):
    client, factory, project, other, _ = phase2_env
    issued = (await client.post(f"/api/projects/{project}/trace-tokens")).json()
    token = {"Authorization": "Bearer " + issued["token"]}
    endpoint = "/api/v1/traces/events"
    event_id = str(uuid.uuid4())
    payload = {"events": [{"event_id": event_id, "status": "error", "model": "m",
        "input_text": "hello user@example.com", "output_text": "Bearer supersecret", "error_detail": "sk-abcdef1234567890",
        "attributes": {"safe": {"nested": "user@example.com", "api_key": "secret"}, "authorization": "bad"}}]}
    assert (await client.post(endpoint, json=payload, headers=token)).json()["accepted"] == 1
    detail_url = f"/api/projects/{project}/traces/{event_id}"
    assert (await client.get(detail_url)).json()["input_text"] is None
    revealed = (await client.get(detail_url, params={"include_bodies": True},
                                 headers={"X-RedForge-Sensitive-Access": "allow"})).json()
    assert revealed["input_text"] is None and revealed["output_text"] is None
    assert revealed["attributes"] == {} and revealed["error_detail"] is None
    policy = {"capture_input": True, "capture_output": True, "capture_metadata": True,
              "capture_errors": True, "metadata_allowlist": ["safe.nested"], "retention_days": 1}
    assert (await client.put(f"/api/projects/{project}/trace-privacy", json=policy)).status_code == 200
    event_id_2 = str(uuid.uuid4())
    payload["events"][0]["event_id"] = event_id_2
    assert (await client.post(endpoint, json=payload, headers=token)).json()["accepted"] == 1
    revealed = (await client.get(f"/api/projects/{project}/traces/{event_id_2}", params={"include_bodies": True},
                                 headers={"X-RedForge-Sensitive-Access": "allow"})).json()
    assert "user@example.com" not in revealed["input_text"]
    assert "supersecret" not in revealed["output_text"]
    assert "abcdef" not in revealed["error_detail"]
    assert "api_key" not in revealed["attributes"]["safe"]
    assert "user@example.com" not in str(revealed["attributes"])
    assert (await client.get(f"/api/projects/{other}/traces/{event_id_2}")).status_code == 404
    async with factory() as db:
        row = (await db.execute(select(TraceEvent).where(TraceEvent.event_id == event_id_2))).scalar_one()
        row.received_at = datetime.now(timezone.utc) - timedelta(days=3)
        await db.commit()
        assert await cleanup_expired(db, batch_size=1) == 1
    assert (await client.get(f"/api/projects/{project}/traces/{event_id_2}")).status_code == 404
    assert (await client.put(f"/api/projects/{project}/trace-privacy", json={"telemetry_enabled": False})).status_code == 200
    payload["events"][0]["event_id"] = str(uuid.uuid4())
    disabled = (await client.post(endpoint, json=payload, headers=token)).json()
    assert disabled["accepted"] == 0 and disabled["dropped"] == 1


def test_privacy_filter_fail_closed_and_payload_bounds(monkeypatch):
    import app.observability_privacy as privacy
    policy = privacy.PrivacySettings(capture_input=True, capture_metadata=True,
        metadata_allowlist=["safe"], max_payload_bytes=64)
    event = {"input_text": "é" * 100, "attributes": {"safe": "x" * 100}}
    clean = privacy.filter_event(event, policy)
    assert len(clean["input_text"].encode("utf-8")) <= 64
    assert clean["attributes"] == {}
    monkeypatch.setattr(privacy, "_scrub", lambda *args, **kwargs: 1 / 0)
    assert privacy.filter_event(event, policy) is None


def test_sdk_independent_capture_controls():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
    from redforge.observability import Tracer
    tracer = Tracer(token="rft_test", capture_input=True, capture_output=False,
                    capture_metadata=True, capture_errors=False, metadata_allowlist={"safe"})
    events = []
    tracer._enqueue = events.append
    try:
        tracer.observe(lambda **kw: (_ for _ in ()).throw(RuntimeError("secret failure")),
                       prompt="hello", trace_metadata={"safe": "yes", "password": "bad"})
    except RuntimeError:
        pass
    assert events[0]["input_text"] == "hello"
    assert "output_text" not in events[0] and "error_detail" not in events[0]
    assert events[0]["attributes"] == {"safe": "yes"}


@pytest.mark.asyncio
async def test_legacy_snapshots_do_not_show_false_diffs(phase2_env):
    client, factory, project, _, set_id = phase2_env
    base = f"/api/v1/projects/{project}/prompt-registry"
    created = await client.post(base, json={"prompt_set_id": set_id,
        "definition": {"title": "Legacy", "prompt": "Before"}})
    pid = created.json()["id"]
    await client.post(f"{base}/{pid}/publish", json={})
    await client.put(f"{base}/{pid}/draft", json={"definition": {"title": "Legacy", "prompt": "After"}})
    await client.post(f"{base}/{pid}/publish", json={})
    async with factory() as db:
        old = (await db.execute(select(PromptVersion).where(
            PromptVersion.prompt_id == pid, PromptVersion.version == 1))).scalar_one()
        old.snapshot = {key: value for key, value in old.snapshot.items()
                        if key not in {"description", "variables_schema", "enabled"}}
        await db.commit()
    compared = (await client.get(f"{base}/{pid}/compare?a=1&b=2")).json()
    assert compared["changed_fields"] == ["prompt"]
