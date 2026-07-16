"""Phase 2.5 — Runtime Registry, checkpoint runtime linkage, prediction feedback,
report composition, and assistant checkpoint/accuracy answers. Offline."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fac = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = fac()
    yield session
    await session.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# -- Runtime Registry -------------------------------------------------------

@pytest.mark.asyncio
async def test_registry_registers_with_fallback(db_session):
    from app.runtime_registry import runtime_registry
    rec = await runtime_registry.register_checkpoint(
        db_session, run_id="run-abcdef12", step=4, base_model="llama3.1:8b", provider="ollama",
    )
    assert rec["id"] == "ckpt-run-abcd-step-4"
    assert rec["fallback"] is True                 # no adapter host yet → base model
    assert rec["runtime_model"] == "llama3.1:8b"   # resolves to base
    # idempotent per (run, step)
    again = await runtime_registry.register_checkpoint(
        db_session, run_id="run-abcdef12", step=4, base_model="llama3.1:8b", provider="ollama")
    assert again["id"] == rec["id"]
    resolved = await runtime_registry.resolve(db_session, rec["id"])
    assert resolved == "llama3.1:8b"


@pytest.mark.asyncio
async def test_registry_api_list_and_get(client):
    reg = (await client.post("/api/registry", json={
        "run_id": "r1", "step": 2, "base_model": "m", "provider": "ollama"})).json()
    assert reg["provider"] == "ollama"
    listed = (await client.get("/api/registry", params={"run_id": "r1"})).json()
    assert any(x["id"] == reg["id"] for x in listed)
    got = (await client.get(f"/api/registry/{reg['id']}")).json()
    assert got["id"] == reg["id"]
    assert (await client.get("/api/registry/nope")).status_code == 404


# -- checkpoint security stores runtime linkage -----------------------------

@pytest.mark.asyncio
async def test_checkpoint_security_records_runtime_id(db_session):
    from app.continuous_security.service import ContinuousSecurityService

    def fac():
        return db_session
    svc = ContinuousSecurityService(
        evaluate_fn=lambda m, p: _fake_eval(m, p), session_factory=lambda: _Ctx(db_session),
        auto_worker=False,
    )
    await svc.schedule(run_id="r", step=1, target_model="m", runtime_id="ckpt-r-step-1", provider="ollama")
    await svc.drain()
    tl = await svc.timeline("r")
    assert tl[0]["runtime_id"] == "ckpt-r-step-1" and tl[0]["provider"] == "ollama"


class _Ctx:
    def __init__(self, s): self._s = s
    async def __aenter__(self): return self._s
    async def __aexit__(self, *a): return False


async def _fake_eval(model, profile):
    return {"score": 70, "categories": [], "findings": [], "session_id": None}


# -- prediction feedback ----------------------------------------------------

@pytest.mark.asyncio
async def test_prediction_feedback_accuracy(client, db_session):
    from app.db.models import CheckpointSecurity, Recommendation, TrainingRun

    rid = str(uuid4())
    db_session.add(TrainingRun(id=rid, name="r", base_model="m", status="completed"))
    # actual gain 60 -> 78 = +18
    for step, score in ((1, 60.0), (4, 78.0)):
        db_session.add(CheckpointSecurity(id=str(uuid4()), run_id=rid, step=step, target_model="m",
                                          profile="quick", status="completed", score=score, categories=[]))
    rec = Recommendation(id=str(uuid4()), run_id=rid, target_model="m", status="accepted",
                         payload={"prediction": {"expected_security_gain": 20, "confidence": 0.6}})
    db_session.add(rec)
    await db_session.commit()

    out = (await client.post(f"/api/recommendations/{rec.id}/feedback",
                             json={"applied_run_id": rid})).json()
    o = out["outcome"]
    assert o["actual_security_gain"] == 18.0 and o["predicted_security_gain"] == 20
    assert 0 <= o["recommendation_accuracy"] <= 1
    assert out["status"] == "applied"

    summ = (await client.get("/api/recommendations/accuracy")).json()
    assert summ["count"] == 1 and summ["mean_accuracy"] is not None


# -- report composition -----------------------------------------------------

@pytest.mark.asyncio
async def test_training_report_composes_existing_data(client, db_session):
    from app.db.models import CheckpointSecurity, RegisteredModel, TrainingRun

    rid = str(uuid4())
    db_session.add(TrainingRun(id=rid, name="RunX", base_model="m", method="lora",
                               backend="simulation", status="completed",
                               config={"epochs": 3}, metrics={"final_loss": 0.4}))
    for step, score in ((1, 60.0), (4, 80.0)):
        db_session.add(CheckpointSecurity(id=str(uuid4()), run_id=rid, step=step, target_model="m",
                                          profile="quick", status="completed", score=score,
                                          categories=[{"category": "JAILBREAK", "score": score, "risk_level": "none"}]))
    db_session.add(RegisteredModel(id="ckpt-x-step-4", run_id=rid, label="Checkpoint 4",
                                   step=4, base_model="m", provider="ollama", runtime_model="m",
                                   fallback=1, status="registered"))
    await db_session.commit()

    rep = (await client.get(f"/api/training/{rid}/report")).json()
    assert rep["training_summary"]["name"] == "RunX"
    assert rep["checkpoint_comparison"]["delta"] == 20.0
    assert rep["final_models"][0]["label"] == "Checkpoint 4"
    assert "executive_summary" in rep and "final_configuration" in rep
    assert (await client.get("/api/training/nope/report")).status_code == 404


# -- assistant --------------------------------------------------------------

@pytest.mark.asyncio
async def test_assistant_best_checkpoint(client, db_session, monkeypatch):
    from app.continuous_security import continuous_security
    async def fake_timeline(run_id):
        return [{"step": 1, "score": 60}, {"step": 2, "score": 85}, {"step": 3, "score": 80}]
    monkeypatch.setattr(continuous_security, "timeline", fake_timeline)
    monkeypatch.setattr("app.api.assistant.continuous_security", continuous_security, raising=False)

    r = (await client.post("/api/assistant/ask",
                           json={"question": "which checkpoint is best?", "run_id": "r"})).json()
    assert "step 2" in r["answer"].lower() or "step 2" in r["answer"]


@pytest.mark.asyncio
async def test_assistant_biggest_improvement(client, db_session):
    from app.db.models import Recommendation

    db_session.add(Recommendation(
        id=str(uuid4()), target_model="llama3.1:8b", status="applied",
        payload={"prediction": {"expected_security_gain": 15}},
        outcome={"actual_security_gain": 18.0, "predicted_security_gain": 15,
                 "recommendation_accuracy": 0.83},
    ))
    await db_session.commit()

    r = (await client.post("/api/assistant/ask",
                           json={"question": "which recommendation produced the biggest improvement?"})).json()
    assert "llama3.1:8b" in r["answer"]
    assert "18" in r["answer"]
