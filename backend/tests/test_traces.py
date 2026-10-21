"""Trace ingestion, privacy, project boundaries, pagination, and SDK behavior."""
import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.api import traces
from app.db.database import AsyncSessionLocal
from app.db.models import TraceEvent, TraceToken

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli"))
from redforge.observability import Tracer  # noqa: E402


@pytest.mark.asyncio
async def test_ingestion_auth_privacy_isolation_and_pagination():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        p1 = (await client.post("/api/projects", json={"name": "Trace A"})).json()["id"]
        p2 = (await client.post("/api/projects", json={"name": "Trace B"})).json()["id"]
        issued = (await client.post(f"/api/projects/{p1}/trace-tokens")).json()
        assert issued["token"].startswith("rft_")
        assert "token" not in (await client.get(f"/api/projects/{p1}/trace-tokens")).json()[0]
        payload = {"events": [{"event_id": str(uuid.uuid4()), "status": "success", "provider": "openai", "model": "test",
                              "trace_id": "trace-1", "conversation_id": "conversation-1", "tenant_id": "tenant-a",
                              "input_text": "Bearer secretvalue", "attributes": {"api_key": "bad", "safe": "yes"}}]}
        url = "/api/v1/traces/events"
        assert (await client.post(url, json=payload)).status_code == 401
        headers = {"Authorization": "Bearer " + issued["token"]}
        assert (await client.put(f"/api/projects/{p1}/trace-privacy", json={
            "capture_input": True, "capture_metadata": True, "metadata_allowlist": ["safe"]
        })).status_code == 200
        first = await client.post(url, json=payload, headers=headers)
        assert first.status_code == 202, first.text
        assert first.json() == {"accepted": 1, "duplicates": 0, "dropped": 0}
        duplicate = await client.post(url, json=payload, headers=headers)
        assert duplicate.json() == {"accepted": 0, "duplicates": 1, "dropped": 0}
        assert (await client.post(url, json={"events": [{"event_id": "x", "status": "bogus"}]}, headers=headers)).status_code == 422
        assert (await client.post(url, content=b"x" * 131073, headers=headers)).status_code == 413
        own = (await client.get(f"/api/projects/{p1}/traces", params={"trace_id": "trace-1"})).json()
        assert len(own["items"]) == 1
        assert own["next_cursor"] is None
        assert (await client.get(f"/api/projects/{p2}/traces")).json()["items"] == []
        event_id = payload["events"][0]["event_id"]
        assert (await client.get(f"/api/projects/{p2}/traces/{event_id}")).status_code == 404
        assert (await client.get(f"/api/projects/{p1}/traces/{event_id}")).json()["input_text"] is None
        assert (await client.get(f"/api/projects/{p1}/traces/{event_id}?include_bodies=true")).status_code == 403
        detail = (await client.get(f"/api/projects/{p1}/traces/{event_id}?include_bodies=true",
                                   headers={"X-RedForge-Sensitive-Access": "allow"})).json()
        assert "secretvalue" not in detail["input_text"]
        assert "api_key" not in detail["attributes"]
        assert detail["attributes"]["safe"] == "yes"
        for n in range(3):
            await client.post(url, json={"events": [{"event_id": f"page-{n}-{uuid.uuid4()}", "status": "error", "provider": "anthropic"}]}, headers=headers)
        page = (await client.get(f"/api/projects/{p1}/traces", params={"limit": 2, "status": "error"})).json()
        assert len(page["items"]) == 2 and page["next_cursor"]
        older = (await client.get(f"/api/projects/{p1}/traces", params={"limit": 2, "status": "error", "before_id": page["next_cursor"]})).json()
        assert len(older["items"]) == 1
        assert {x["event_id"] for x in page["items"]}.isdisjoint(x["event_id"] for x in older["items"])
        assert (await client.delete(f"/api/projects/{p1}/trace-tokens/{issued['id']}")).status_code == 204
        assert (await client.post(url, json=payload, headers=headers)).status_code == 401
        assert (await client.delete(f"/api/projects/{p1}")).status_code == 200
        async with AsyncSessionLocal() as db:
            assert (await db.execute(select(TraceEvent).where(TraceEvent.project_id == p1))).scalars().first() is None
            assert (await db.execute(select(TraceToken).where(TraceToken.project_id == p1))).scalars().first() is None


@pytest.mark.asyncio
async def test_tenant_scope_and_rate_limit(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        project = (await client.post("/api/projects", json={"name": "Tenant Trace"})).json()["id"]
        issued = (await client.post(f"/api/projects/{project}/trace-tokens?tenant_id=tenant-a")).json()
        headers = {"Authorization": "Bearer " + issued["token"]}
        url = "/api/v1/traces/events"
        wrong = {"events": [{"event_id": str(uuid.uuid4()), "status": "success", "tenant_id": "tenant-b"}]}
        assert (await client.post(url, json=wrong, headers=headers)).status_code == 403
        monkeypatch.setattr(traces, "RATE_PER_MINUTE", 1)
        traces._rate.clear()
        first_id = str(uuid.uuid4())
        assert (await client.post(url, json={"events": [{"event_id": first_id, "status": "success"}]}, headers=headers)).status_code == 202
        detail = (await client.get(f"/api/projects/{project}/traces/{first_id}")).json()
        assert detail["tenant_id"] == "tenant-a"
        limited = await client.post(url, json={"events": [{"event_id": str(uuid.uuid4()), "status": "success"}]}, headers=headers)
        assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"
        traces._rate.clear()


def test_sdk_sync_wrappers_stream_privacy_and_noop():
    tracer = Tracer(token="rft_test", enabled=True, capture_content=False, metadata_allowlist={"safe"})
    events = []
    tracer._enqueue = events.append
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5), choices=[SimpleNamespace(finish_reason="stop")])
    class Client:
        chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))
    with tracer.context(trace_id="trace-a", tenant_id="tenant-a"):
        assert tracer.wrap(Client(), "openai").chat.completions.create(model="test", messages=[{"role": "user", "content": "private"}]) is response
    assert events[0]["input_tokens"] == 3 and events[0]["output_tokens"] == 5
    assert events[0]["trace_id"] == "trace-a" and "input_text" not in events[0]
    class Anthropic:
        messages = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(usage=SimpleNamespace(input_tokens=4, output_tokens=6)))
    assert tracer.wrap(Anthropic(), "anthropic").messages.create(model="claude", messages=[]).usage.output_tokens == 6
    assert events[-1]["provider"] == "anthropic" and events[-1]["model"] == "claude"
    class Gemini:
        models = SimpleNamespace(generate_content=lambda **kwargs: {"usage_metadata": {"prompt_token_count": 7, "candidates_token_count": 8}})
    assert tracer.wrap(Gemini(), "gemini").models.generate_content(model="gemini", contents="hello")["usage_metadata"]["prompt_token_count"] == 7
    assert events[-1]["input_tokens"] == 7 and events[-1]["output_tokens"] == 8
    assert tracer.observe(lambda: 7, provider="local", trace_metadata={"safe": "ok", "secret": "bad"}) == 7
    assert events[-1]["attributes"] == {"safe": "ok"}
    def chunks(**kwargs):
        yield SimpleNamespace(usage=None)
        yield SimpleNamespace(usage=SimpleNamespace(input_tokens=2, output_tokens=4))
    result = tracer.observe(chunks, provider="gemini", streaming=True)
    assert len(list(result)) == 2 and events[-1]["output_tokens"] == 4
    def broken_chunks():
        yield "first"
        raise TimeoutError("provider stream stalled")
    with pytest.raises(TimeoutError):
        list(tracer.observe(broken_chunks, streaming=True))
    assert events[-1]["status"] == "error" and events[-1]["error_category"] == "TimeoutError"
    assert events[-1]["timed_out"] is True
    disabled = Tracer(enabled=False)
    assert disabled.observe(lambda: "unchanged") == "unchanged"
    assert len(events) == 6


@pytest.mark.asyncio
async def test_sdk_async_exceptions_sampling_and_queue_overflow():
    tracer = Tracer(token="rft_test", sample_rate=1, queue_size=1, retries=0, timeout=0.01)
    events = []
    tracer._enqueue = events.append
    async def provider(**kwargs):
        return {"usage": {"input_tokens": 1, "output_tokens": 2}}
    assert await tracer.observe(provider, provider="anthropic", model="m") == {"usage": {"input_tokens": 1, "output_tokens": 2}}
    assert events[0]["usage_source"] == "provider"
    def fail():
        raise ValueError("bad")
    with pytest.raises(ValueError, match="bad"):
        tracer.observe(fail)
    assert events[-1]["error_category"] == "ValueError"
    failing_transport = Tracer(token="rft_test")
    failing_transport._enqueue = lambda event: 1 / 0
    with pytest.raises(ValueError, match="bad"):
        failing_transport.observe(fail)
    assert failing_transport.dropped == 1
    silent = Tracer(token="rft_test", sample_rate=0)
    silent._enqueue = events.append
    assert silent.observe(lambda: 9) == 9 and len(events) == 2
    full = Tracer(token="rft_test", queue_size=1)
    full._queue.put_nowait({"event_id": "first"})
    full._enqueue({"event_id": "second"})
    assert full.dropped == 1


@pytest.mark.asyncio
async def test_sdk_async_stream_content_limits_and_server_down():
    tracer = Tracer(token="rft_test", capture_content=True, max_payload=12, retries=0, timeout=0.01)
    events = []
    tracer._enqueue = events.append
    async def stream(**kwargs):
        async def chunks():
            yield {"text": "one"}
            yield {"text": "two", "usage": {"input_tokens": 1, "output_tokens": 2}}
        return chunks()
    wrapped = tracer.wrap(SimpleNamespace(models=SimpleNamespace(generate_content_stream=stream)), "gemini")
    result = await wrapped.models.generate_content_stream(model="gemini", contents="abcdefghijklmnop")
    assert [chunk["text"] async for chunk in result] == ["one", "two"]
    assert events[0]["input_tokens"] == 1
    assert len(events[0]["input_text"]) <= 12
    # Worker failures never propagate to the model-call path.
    down = Tracer(endpoint="http://127.0.0.1:1", token="rft_test", timeout=0.01, retries=0)
    assert down.observe(lambda: "model result") == "model result"
    assert down.flush(timeout=2)
