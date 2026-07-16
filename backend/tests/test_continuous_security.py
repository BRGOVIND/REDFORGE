"""Continuous Security (Phase 2.3) — checkpoint→evaluation orchestration, timeline,
comparison, queue/cancel, runner hook, and the Assistant's security-evolution
answers. Offline: the evaluator is injected (reuses the engine in production)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.continuous_security.service import ContinuousSecurityService
from app.db.database import Base


@pytest_asyncio.fixture
async def mem_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _improving_evaluator(scores):
    """A fake evaluate_fn that returns rising scores (reuses-the-engine seam)."""
    seq = iter(scores)

    async def evaluate(target_model, profile):
        s = next(seq)
        risk = "high" if s < 70 else "none"
        return {
            "score": s,
            "categories": [
                {"category": "PROMPT_INJECTION", "score": s, "fail_rate": 0.2, "risk_level": risk},
                {"category": "JAILBREAK", "score": s - 5, "fail_rate": 0.3, "risk_level": "medium" if s < 80 else "none"},
            ],
            "findings": [{"category": "PROMPT_INJECTION", "attack_name": "x", "severity": "high"}],
            "session_id": None,
        }

    return evaluate


@pytest.mark.asyncio
async def test_schedule_and_timeline(mem_factory):
    from app.db.models import TrainingRun
    from uuid import uuid4

    svc = ContinuousSecurityService(evaluate_fn=_improving_evaluator([61, 70, 81, 90]),
                                    session_factory=mem_factory, auto_worker=False)
    rid = str(uuid4())
    async with mem_factory() as db:
        db.add(TrainingRun(id=rid, name="r", base_model="m", status="running"))
        await db.commit()

    for step in (1, 2, 3, 4):
        await svc.schedule(run_id=rid, step=step, target_model="m", profile="quick")
    await svc.drain()

    tl = await svc.timeline(rid)
    assert [t["step"] for t in tl] == [1, 2, 3, 4]
    assert [t["score"] for t in tl] == [61, 70, 81, 90]
    assert all(t["status"] == "completed" for t in tl)


@pytest.mark.asyncio
async def test_compare_improved_and_resolved(mem_factory):
    svc = ContinuousSecurityService(evaluate_fn=_improving_evaluator([61, 90]),
                                    session_factory=mem_factory, auto_worker=False)
    rid = "run1"
    await svc.schedule(run_id=rid, step=1, target_model="m", profile="quick")
    await svc.schedule(run_id=rid, step=4, target_model="m", profile="quick")
    await svc.drain()

    cmp = await svc.compare(rid, 1, 4)
    assert cmp["score_delta"] == 29
    assert "PROMPT_INJECTION" in cmp["improved_categories"]
    # PROMPT_INJECTION was high risk at 61, none at 90 → resolved
    assert "PROMPT_INJECTION" in cmp["resolved_vulnerabilities"]


@pytest.mark.asyncio
async def test_cancel_pending_job(mem_factory):
    svc = ContinuousSecurityService(evaluate_fn=_improving_evaluator([50, 50]),
                                    session_factory=mem_factory, auto_worker=False)
    rid = "run2"
    j1 = await svc.schedule(run_id=rid, step=1, target_model="m")
    await svc.cancel(j1["id"])
    await svc.drain()
    tl = await svc.timeline(rid)
    assert tl[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_failed_evaluation_is_recorded_not_fatal(mem_factory):
    async def boom(model, profile):
        raise RuntimeError("provider offline")

    svc = ContinuousSecurityService(evaluate_fn=boom, session_factory=mem_factory, auto_worker=False)
    await svc.schedule(run_id="r3", step=1, target_model="m")
    await svc.drain()  # must not raise
    tl = await svc.timeline("r3")
    assert tl[0]["status"] == "failed" and "offline" in (tl[0]["error"] or "")


@pytest.mark.asyncio
async def test_runner_checkpoint_hook_fires(mem_factory):
    from app.training.providers import simulation
    from app.training.providers.base import TrainingConfig
    from app.training.runner import run_training
    from app.training import training_service

    simulation.SimulationProvider._step_delay = 0
    async with mem_factory() as db:
        run = await training_service.create(
            db, name="R", base_model="m", dataset_id=None, method="lora",
            backend="simulation", config={},
        )
    calls = []

    async def hook(cp):
        calls.append(cp["step"])

    cfg = TrainingConfig(base_model="m", epochs=1, dataset_records=list(range(10)))
    await run_training(run["id"], "simulation", cfg, session_factory=mem_factory, checkpoint_hook=hook)
    assert calls  # at least one checkpoint scheduled an evaluation


# -- API + assistant --------------------------------------------------------

@pytest_asyncio.fixture
async def client_with_cs(mem_factory, monkeypatch):
    """App client whose Continuous Security singleton uses the in-memory DB and a
    fake improving evaluator, so the timeline endpoints return real data."""
    import app.api.training as training_api
    import app.api.assistant as assistant_api
    from app.continuous_security import service as cs_service

    svc = ContinuousSecurityService(evaluate_fn=_improving_evaluator([60, 75, 90]),
                                    session_factory=mem_factory, auto_worker=False)
    monkeypatch.setattr(training_api, "continuous_security", svc)
    monkeypatch.setattr(cs_service, "continuous_security", svc)
    # assistant imports continuous_security lazily inside the function → patch module attr
    monkeypatch.setattr("app.continuous_security.continuous_security", svc, raising=False)

    from app.main import app
    from app.db.database import get_db
    session = mem_factory()
    app.dependency_overrides[get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, svc
    await session.close()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_security_timeline_and_compare_endpoints(client_with_cs):
    client, svc = client_with_cs
    rid = "apiRun"
    for step in (1, 2, 3):
        await svc.schedule(run_id=rid, step=step, target_model="m", profile="quick")
    await svc.drain()

    tl = (await client.get(f"/api/training/{rid}/security")).json()
    assert [t["score"] for t in tl["timeline"]] == [60, 75, 90]

    cmp = (await client.get(f"/api/training/{rid}/security/compare", params={"a": 1, "b": 3})).json()
    assert cmp["score_delta"] == 30

    q = (await client.get("/api/training/security/queue")).json()
    assert "queued" in q
