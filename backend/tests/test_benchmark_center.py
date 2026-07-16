"""Benchmark Center (Phase 3) — suites, queue service, API, assistant, report.

All offline: suites use a fake generate_fn, the service uses an injected run_fn
and in-memory session factory, and the singleton is monkeypatched for API tests.
"""
from __future__ import annotations

from uuid import uuid4

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
async def db_session(SessionLocal):
    s = SessionLocal()
    yield s
    await s.close()


@pytest_asyncio.fixture
async def client(SessionLocal, db_session):
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _fake_gen(model, prompt, options=None):
    return "one two three four five six"


async def _fake_run(model, suites, config):
    scores = {s: 80.0 for s in suites}
    metrics = {s: {"simulated": s not in ("performance", "security")} for s in suites}
    if "performance" in suites:
        metrics["performance"] = {"tokens_per_sec": 50.0, "avg_latency_ms": 200.0,
                                  "first_token_latency_ms": 180.0, "gpu": "TestGPU",
                                  "vram_free_mb": 4000, "ram_available_mb": 16000}
    return {"scores": scores, "metrics": metrics, "overall_score": 80.0}


# -- suite registry ---------------------------------------------------------

def test_registry_lists_all_dimensions():
    from app.benchmarks import list_suites, get_suite, valid_suites
    keys = {s["key"] for s in list_suites()}
    assert {"performance", "reasoning", "instruction_following",
            "hallucination", "context", "security"} <= keys
    assert get_suite("performance") is not None
    assert get_suite("nope") is None
    assert valid_suites([]) == ["performance", "security"]      # defaults
    assert valid_suites(["performance", "bogus"]) == ["performance"]


# -- suites (direct) --------------------------------------------------------

@pytest.mark.asyncio
async def test_performance_suite_measures_real_metrics():
    from app.benchmarks.suites import PerformanceSuite, SuiteContext
    ctx = SuiteContext(model="m", generate_fn=_fake_gen,
                       resources={"cpu_count": 8, "gpu": {"name": "X", "total_mb": 8000, "free_mb": 4000}})
    res = await PerformanceSuite().run(ctx)
    assert res.simulated is False
    assert res.score is not None
    assert res.metrics["tokens_per_sec"] is not None
    assert res.metrics["avg_latency_ms"] is not None
    assert res.metrics["gpu"] == "X" and res.metrics["vram_total_mb"] == 8000


@pytest.mark.asyncio
async def test_reasoning_suite_architecture_fallback():
    from app.benchmarks.suites import ReasoningSuite, SuiteContext
    ctx = SuiteContext(model="llama", generate_fn=_fake_gen)
    res = await ReasoningSuite().run(ctx)
    assert res.simulated is True               # no dataset attached
    assert 0 <= res.score <= 100
    # deterministic per model
    res2 = await ReasoningSuite().run(SuiteContext(model="llama", generate_fn=_fake_gen))
    assert res.score == res2.score


@pytest.mark.asyncio
async def test_security_suite_reuses_engine_via_injection():
    from app.benchmarks.suites import SecuritySuite, SuiteContext

    async def fake_eval(model, profile):
        return {"score": 72.0, "categories": [{"category": "JAILBREAK", "score": 72}], "findings": []}
    ctx = SuiteContext(model="m", generate_fn=_fake_gen, config={"evaluate_fn": fake_eval})
    res = await SecuritySuite().run(ctx)
    assert res.score == 72.0 and res.simulated is False


# -- queue service (direct, injected run_fn) --------------------------------

@pytest.mark.asyncio
async def test_service_schedule_drain_and_reads(SessionLocal):
    from app.benchmarks.service import BenchmarkService
    svc = BenchmarkService(run_fn=_fake_run, session_factory=SessionLocal, auto_worker=False)

    a = await svc.schedule(target_model="base:8b", suites=["performance", "security"],
                           project_id="p1", label="Base")
    b = await svc.schedule(target_model="ckpt:8b", suites=["performance", "security"],
                           project_id="p1", registry_id="ckpt-x-step-4", run_id="run1", label="Checkpoint 4")
    assert svc.queue_status()["queued"] == 2
    await svc.drain()

    hist = await svc.history(project_id="p1")
    assert len(hist) == 2 and all(h["status"] == "completed" for h in hist)

    board = await svc.leaderboard(project_id="p1")
    assert board and board[0]["rank_score"] == 80.0

    cmp = await svc.compare([a["id"], b["id"]])
    assert set(cmp["suites"]) == {"performance", "security"}
    assert len(cmp["models"]) == 2

    tr = await svc.trends(project_id="p1")
    assert "base:8b" in tr["series"] and "ckpt:8b" in tr["series"]


@pytest.mark.asyncio
async def test_service_cancel_pending(SessionLocal):
    from app.benchmarks.service import BenchmarkService
    svc = BenchmarkService(run_fn=_fake_run, session_factory=SessionLocal, auto_worker=False)
    job = await svc.schedule(target_model="m", suites=["performance"])
    await svc.cancel(job["id"])
    await svc.drain()
    got = await svc.get(job["id"])
    assert got["status"] == "cancelled"


# -- API --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_suites(client):
    suites = (await client.get("/api/benchmark-center/suites")).json()
    assert any(s["key"] == "performance" and s["real"] for s in suites)


@pytest.mark.asyncio
async def test_api_schedule_and_read(client, SessionLocal, monkeypatch):
    from app.benchmarks import service as svc_mod
    monkeypatch.setattr(svc_mod.benchmark_center, "_run_fn", _fake_run)
    monkeypatch.setattr(svc_mod.benchmark_center, "_session_factory", SessionLocal)
    monkeypatch.setattr(svc_mod.benchmark_center, "_auto_worker", False)

    resp = await client.post("/api/benchmark-center", json={
        "models": ["base:8b", "other:8b"], "suites": ["performance", "security"], "project_id": "p1"})
    assert resp.status_code == 201
    assert resp.json()["count"] == 2

    await svc_mod.benchmark_center.drain()

    hist = (await client.get("/api/benchmark-center", params={"project_id": "p1"})).json()
    assert len(hist) == 2
    board = (await client.get("/api/benchmark-center/leaderboard", params={"project_id": "p1"})).json()
    assert len(board) == 2
    rid = hist[0]["id"]
    one = (await client.get(f"/api/benchmark-center/{rid}")).json()
    assert one["id"] == rid
    assert (await client.get("/api/benchmark-center/nope")).status_code == 404


@pytest.mark.asyncio
async def test_api_schedule_requires_targets(client):
    resp = await client.post("/api/benchmark-center", json={"suites": ["performance"]})
    assert resp.status_code == 400


# -- assistant --------------------------------------------------------------

@pytest.mark.asyncio
async def test_assistant_fastest_and_best(client, monkeypatch):
    from app.benchmarks import benchmark_center

    async def fake_history(*, project_id=None, run_id=None, model=None, limit=200):
        return [
            {"id": "1", "label": "Base", "target_model": "base", "status": "completed",
             "overall_score": 70.0, "suites": ["performance"], "created_at": "2026-01-01T00:00:00",
             "metrics": {"performance": {"tokens_per_sec": 30.0, "avg_latency_ms": 300.0,
                                          "first_token_latency_ms": 250.0}}},
            {"id": "2", "label": "Checkpoint 4", "target_model": "ckpt", "status": "completed",
             "overall_score": 88.0, "suites": ["performance"], "created_at": "2026-02-01T00:00:00",
             "metrics": {"performance": {"tokens_per_sec": 60.0, "avg_latency_ms": 150.0,
                                          "first_token_latency_ms": 120.0, "gpu": "RTX",
                                          "vram_free_mb": 5000, "ram_available_mb": 20000}}},
        ]
    monkeypatch.setattr(benchmark_center, "history", fake_history)

    fast = (await client.post("/api/assistant/ask", json={"question": "which model is fastest?"})).json()
    assert "Checkpoint 4" in fast["answer"] and "60" in fast["answer"]

    best = (await client.post("/api/assistant/ask",
                              json={"question": "which checkpoint performs best?"})).json()
    assert "Checkpoint 4" in best["answer"] and "88" in best["answer"]

    lat = (await client.post("/api/assistant/ask",
                             json={"question": "why did latency increase?"})).json()
    assert "latency" in lat["answer"].lower()

    matters = (await client.post("/api/assistant/ask",
                                 json={"question": "which benchmark matters most?"})).json()
    assert "Security" in matters["answer"]


# -- report integration -----------------------------------------------------

@pytest.mark.asyncio
async def test_training_report_includes_benchmarks(client, db_session):
    from app.db.models import BenchmarkResult, TrainingRun

    rid = str(uuid4())
    db_session.add(TrainingRun(id=rid, name="RunX", base_model="m", method="lora",
                               backend="simulation", status="completed"))
    db_session.add(BenchmarkResult(id=str(uuid4()), run_id=rid, target_model="m",
                                   label="Checkpoint 4", status="completed", overall_score=85.0,
                                   suites=["performance", "security"],
                                   scores={"performance": 90.0, "security": 80.0}, metrics={}))
    await db_session.commit()

    rep = (await client.get(f"/api/training/{rid}/report")).json()
    assert rep["benchmarks"] and rep["benchmarks"][0]["overall_score"] == 85.0
    assert rep["best_benchmark"]["label"] == "Checkpoint 4"
