"""Tests for terminal-line derivation, the terminal endpoint, and heartbeats."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import EvaluationEvent
from app.sessions.constants import EventType
from app.sessions.event_repository import EventRepository
from app.sessions.session_manager import SessionManager
from app.sessions.session_repository import SessionRepository
from app.sessions.terminal import event_to_line, events_to_lines


def _event(event_type: str, **fields) -> EvaluationEvent:
    md = fields.pop("metadata", {})
    e = EvaluationEvent(
        id=fields.pop("id", 1),
        session_id="s",
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
    )
    e.category = fields.pop("category", None)
    e.model_name = fields.pop("model_name", None)
    e.verdict = fields.pop("verdict", None)
    e.latency_ms = fields.pop("latency_ms", None)
    e.attack_name = fields.pop("attack_name", None)
    e.event_metadata = md
    return e


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------

def test_verdict_pass_is_success():
    line = event_to_line(_event(EventType.VERDICT_GENERATED, verdict="PASS", metadata={"reason": "refused"}))
    assert line is not None
    assert line.level == "success"
    assert "PASS" in line.text


def test_verdict_fail_is_failure():
    line = event_to_line(_event(EventType.VERDICT_GENERATED, verdict="FAIL", metadata={"reason": "override"}))
    assert line.level == "failure"
    assert "unsafe" in line.text.lower()


def test_mutation_is_warning():
    line = event_to_line(_event(EventType.MUTATION_APPLIED, metadata={"strategy": "suffix_append"}))
    assert line.level == "warning"
    assert "suffix_append" in line.text


def test_heartbeat_line():
    line = event_to_line(_event(EventType.HEARTBEAT, metadata={"text": "still running…"}))
    assert line.level == "info"
    assert line.text == "still running…"


def test_attack_started_counter():
    line = event_to_line(
        _event(EventType.ATTACK_STARTED, category="PROMPT_INJECTION", metadata={"order": 6}),
        total_tasks=150,
    )
    assert "7/150" in line.text


def test_session_created_and_completed_levels():
    created = event_to_line(_event(EventType.SESSION_CREATED, metadata={"profile": "standard"}))
    assert created.level == "system" and "standard" in created.text
    done = event_to_line(_event(EventType.SESSION_COMPLETED))
    assert done.level == "success"


def test_unknown_event_yields_no_line():
    assert event_to_line(_event("some_internal_event")) is None


def test_events_to_lines_filters_unmapped():
    events = [
        _event(EventType.SESSION_CREATED, id=1, metadata={"profile": "p"}),
        _event("noise", id=2),
        _event(EventType.SESSION_COMPLETED, id=3),
    ]
    lines = events_to_lines(events)
    assert len(lines) == 2
    assert lines[0].id == 1 and lines[1].id == 3


# ---------------------------------------------------------------------------
# Endpoint + heartbeat (need a DB)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def factory(tmp_path):
    # A real on-disk DB (not a shared in-memory connection) so the heartbeat's
    # concurrent session gets its own connection — mirroring production, where
    # the executor holds one connection while the heartbeat task uses another.
    url = f"sqlite+aiosqlite:///{(tmp_path / 'terminal.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _seed_session(factory) -> str:
    async with factory() as db:
        session = await SessionRepository(db).create(
            session_type="batch", selected_models=["m"], selected_categories=["X"], total_tasks=2,
        )
        erepo = EventRepository(db)
        await erepo.add(session_id=session.id, event_type=EventType.SESSION_CREATED,
                        metadata={"profile": "standard"})
        await erepo.add(session_id=session.id, event_type=EventType.ATTACK_STARTED,
                        category="PROMPT_INJECTION", metadata={"order": 0})
        await erepo.add(session_id=session.id, event_type=EventType.VERDICT_GENERATED,
                        verdict="FAIL", metadata={"reason": "broke"})
    return session.id


@pytest_asyncio.fixture
async def client(factory):
    from app.main import app
    from app.api.sessions import get_session_manager

    manager = SessionManager(factory)
    app.dependency_overrides[get_session_manager] = lambda: manager
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, factory
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_terminal_endpoint_returns_lines(client):
    c, factory = client
    sid = await _seed_session(factory)
    resp = await c.get(f"/api/sessions/{sid}/terminal")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cursor"] > 0
    levels = [l["level"] for l in body["lines"]]
    assert "system" in levels and "failure" in levels


@pytest.mark.asyncio
async def test_terminal_cursor_is_incremental(client):
    c, factory = client
    sid = await _seed_session(factory)
    first = (await c.get(f"/api/sessions/{sid}/terminal")).json()
    # After the cursor, there is nothing new.
    second = (await c.get(f"/api/sessions/{sid}/terminal", params={"after_id": first["cursor"]})).json()
    assert second["lines"] == []
    assert second["cursor"] == first["cursor"]


@pytest.mark.asyncio
async def test_terminal_unknown_session_404(client):
    c, _ = client
    resp = await c.get("/api/sessions/nope/terminal")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_emitted_on_slow_generate(factory, monkeypatch):
    """A slow inference emits heartbeat events; a fast one emits none."""
    from app.execution import adaptive_executor as mod

    monkeypatch.setattr(mod, "HEARTBEAT_INTERVAL", 0.05)

    async def slow_gen(model, prompt):
        await asyncio.sleep(0.16)
        return ("ok", 5)

    ex = mod.AdaptiveExecutor(factory, generate_fn=slow_gen)
    sid = await _seed_session(factory)

    text, _ = await ex._generate_with_heartbeat(sid, "m", "prompt")
    assert text == "ok"

    async with factory() as db:
        beats = await EventRepository(db).list_for_session(sid, event_type=EventType.HEARTBEAT)
    assert len(beats) >= 1


@pytest.mark.asyncio
async def test_fast_generate_emits_no_heartbeat(factory):
    from app.execution.adaptive_executor import AdaptiveExecutor

    async def fast_gen(model, prompt):
        return ("ok", 5)

    ex = AdaptiveExecutor(factory, generate_fn=fast_gen)
    sid = await _seed_session(factory)
    await ex._generate_with_heartbeat(sid, "m", "prompt")

    async with factory() as db:
        beats = await EventRepository(db).list_for_session(sid, event_type=EventType.HEARTBEAT)
    assert beats == []
