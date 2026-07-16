"""Recommendation Engine (Phase 2.4) — pure engine, context assembly from local
metadata, persistence + accept/reject, API, and the recommendation-aware
Assistant. Offline."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.recommendations.engine import ModelContext, recommend


# -- pure engine ------------------------------------------------------------

def test_engine_recommends_for_weak_model():
    ctx = ModelContext(
        target_model="llama3.1:8b",
        security_score=55,
        categories=[
            {"category": "PROMPT_INJECTION", "score": 40, "risk_level": "high"},
            {"category": "JAILBREAK", "score": 50, "risk_level": "high"},
        ],
        total_tests=40,
    )
    r = recommend(ctx)
    assert len(r["weaknesses"]) == 2
    assert r["strategy"]["method"] == "lora"          # 8B → LoRA
    assert r["hyperparameters"]["rank"] == 32          # 2 high-severity → rank 32
    assert r["hyperparameters"]["alpha"] == 64
    assert r["prediction"]["expected_security_gain"] > 0
    assert "estimate" in r["prediction"]["disclaimer"].lower()
    # safety datasets suggested for injection/jailbreak
    names = [d["name"] for d in r["datasets"]["public"]]
    assert any("HH" in n or "OpenAssistant" in n for n in names)


def test_engine_large_model_picks_qlora():
    r = recommend(ModelContext(target_model="llama3.3:70b", security_score=60,
                               categories=[{"category": "JAILBREAK", "score": 50, "risk_level": "high"}]))
    assert r["strategy"]["method"] == "qlora"


def test_engine_lowers_lr_when_prior_training_did_not_improve():
    r = recommend(ModelContext(
        target_model="m", security_score=60,
        categories=[{"category": "JAILBREAK", "score": 50, "risk_level": "high"}],
        last_training={"learning_rate": 0.0004, "warmup_steps": 10},
        score_trend=-2.0,  # got worse
    ))
    assert r["hyperparameters"]["learning_rate"] == 0.0002  # halved
    assert r["hyperparameters"]["warmup_steps"] >= 20


def test_engine_no_weakness_recommends_broader_attacks():
    r = recommend(ModelContext(target_model="m", security_score=95, categories=[], total_tests=10))
    assert r["weaknesses"] == []
    assert r["attacks"]["recommend_more"] is True


# -- service + API ----------------------------------------------------------

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


async def _seed_run_with_security(db):
    """A training run + a completed checkpoint-security result to analyze."""
    from uuid import uuid4
    from app.db.models import CheckpointSecurity, TrainingRun

    rid = str(uuid4())
    db.add(TrainingRun(id=rid, name="r", base_model="llama3.1:8b", status="completed",
                       config={"learning_rate": 0.0004, "method": "lora"}))
    db.add(CheckpointSecurity(
        id=str(uuid4()), run_id=rid, step=4, target_model="llama3.1:8b",
        profile="quick", status="completed", score=58.0,
        categories=[{"category": "JAILBREAK", "score": 45, "risk_level": "high"},
                    {"category": "PROMPT_INJECTION", "score": 60, "risk_level": "medium"}],
        findings=[],
    ))
    await db.commit()
    return rid


@pytest.mark.asyncio
async def test_analyze_from_run_persists_and_lists(client, db_session):
    rid = await _seed_run_with_security(db_session)
    resp = await client.post("/api/recommendations/analyze",
                             json={"target_model": "llama3.1:8b", "run_id": rid})
    assert resp.status_code == 200
    rec = resp.json()
    assert rec["status"] == "proposed"
    assert rec["payload"]["weaknesses"]        # weaknesses derived from stored security
    assert rec["payload"]["strategy"]["method"] == "lora"

    listed = (await client.get("/api/recommendations")).json()
    assert any(r["id"] == rec["id"] for r in listed)


@pytest.mark.asyncio
async def test_accept_reject_history(client, db_session):
    rid = await _seed_run_with_security(db_session)
    rec = (await client.post("/api/recommendations/analyze",
                             json={"target_model": "llama3.1:8b", "run_id": rid})).json()
    accepted = (await client.post(f"/api/recommendations/{rec['id']}/decision",
                                  json={"status": "accepted"})).json()
    assert accepted["status"] == "accepted" and accepted["decided_at"]
    assert (await client.post("/api/recommendations/nope/decision",
                              json={"status": "rejected"})).status_code == 404


@pytest.mark.asyncio
async def test_analyze_without_persist(client):
    r = (await client.post("/api/recommendations/analyze",
                           json={"target_model": "m", "persist": False})).json()
    assert "payload" in r and "id" not in r


# -- assistant --------------------------------------------------------------

@pytest.mark.asyncio
async def test_assistant_answers_from_recommendation(client, db_session):
    rid = await _seed_run_with_security(db_session)
    rec = (await client.post("/api/recommendations/analyze",
                             json={"target_model": "llama3.1:8b", "run_id": rid})).json()
    r = (await client.post("/api/assistant/ask", json={
        "question": "how much improvement should I expect?",
        "recommendation_id": rec["id"],
    })).json()
    assert "security" in r["answer"].lower()
    assert r["sources"][0]["title"].startswith("Recommendation")
