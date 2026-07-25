"""Evaluation Workbench (Phase 4) — similarity, regression, versioning, CRUD,
session execution, API, assistant, and report integration.

Fully offline: the session service uses an injected generate_fn and an in-memory
session factory; API tests monkeypatch the singletons onto the test DB.
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


GOLDEN = "The capital of France is Paris."


async def fake_gen(model, prompt, *, system=None, options=None):
    """Injectable generate_fn: 'good' matches the golden; 'bad' diverges."""
    if model == "good":
        return {"response": "The capital of France is Paris.", "latency_ms": 100,
                "prompt_tokens": 5, "completion_tokens": 6, "total_tokens": 11}
    return {"response": "I cannot help with unrelated trivia at this time.",
            "latency_ms": 500, "prompt_tokens": 5, "completion_tokens": 9, "total_tokens": 14}


# -- similarity -------------------------------------------------------------

def test_similarity_providers():
    from app.evaluation.similarity import get_similarity, list_similarity

    assert {p["key"] for p in list_similarity()} >= {"exact", "text", "embedding", "llm_judge"}
    assert get_similarity("exact").score("abc", "abc").score == 100.0
    assert get_similarity("exact").score("abc", "abd").score == 0.0
    text = get_similarity("text").score(GOLDEN, GOLDEN)
    assert text.score == 100.0 and text.simulated is False
    low = get_similarity("text").score("totally different words here", GOLDEN)
    assert low.score < 50
    emb = get_similarity("embedding").score(GOLDEN, GOLDEN)
    assert emb.simulated is True and emb.score > 90
    # unknown key falls back to the default (text), never crashes
    assert get_similarity("nope").score(GOLDEN, GOLDEN).score == 100.0


# -- regression -------------------------------------------------------------

def test_regression_analyzer_detects_types():
    from app.evaluation.regression import regression_analyzer as ra

    # JSON regression: JSON baseline, free-text candidate.
    regs = ra.analyze('{"a": 1}', '{"a": 1}', acceptance={"require_json": True})
    # candidate IS valid json here → no json regression
    assert not any(r["type"] == "json" for r in regs)
    regs = ra.analyze("not json", '{"a": 1}', acceptance={"require_json": True})
    assert any(r["type"] == "json" for r in regs)

    # Instruction regression: required content missing.
    regs = ra.analyze("hello world", "greeting", acceptance={"must_include": ["Paris"]})
    assert any(r["type"] == "instruction" for r in regs)

    # Safety regression: expected refusal, candidate complies.
    regs = ra.analyze("Sure, here is how.", "", expected_behavior="the model must refuse")
    assert any(r["type"] == "safety" and r["severity"] == "critical" for r in regs)

    # Attribution: prompt changed → attributed to prompt.
    regs = ra.analyze("x", GOLDEN, similarity=10.0, prev_response="y", prompt_changed=True)
    assert all(r["attribution"] == "prompt" for r in regs)
    assert "regressions detected" not in ra.summarize(regs)


def test_comparator_diff():
    from app.evaluation.comparator import golden_comparator

    out = golden_comparator.compare('{"a": 1, "b": 2}', '{"a": 1}')
    assert out["baseline_is_json"] and out["json_diff"]["valid"]
    assert "b" in out["json_diff"]["missing_keys"]

    out2 = golden_comparator.compare("line one. line two.", "line one.")
    assert any("line two" in s for s in out2["missing_content"])


# -- CRUD + versioning ------------------------------------------------------

@pytest.mark.asyncio
async def test_crud_and_prompt_versioning(SessionLocal):
    from app.evaluation.service import EvaluationWorkbenchService
    wb = EvaluationWorkbenchService(session_factory=SessionLocal)

    col = await wb.create_collection(project_id="p1", name="Coding", category="coding")
    assert col["prompt_set_count"] == 0
    ps = await wb.create_prompt_set(collection_id=col["id"], title="Basics")
    assert ps is not None and ps["project_id"] == "p1"
    p = await wb.create_prompt(prompt_set_id=ps["id"], prompt="Q?", golden_response=GOLDEN)
    assert p["current_version"] == 1 and p["enabled"] is True

    versions = await wb.prompt_versions(p["id"])
    assert len(versions) == 1 and versions[0]["version"] == 1

    # Editing a content field bumps the version + snapshots.
    p2 = await wb.update_prompt(p["id"], golden_response="Paris is the capital of France.")
    assert p2["current_version"] == 2
    versions = await wb.prompt_versions(p["id"])
    assert len(versions) == 2
    cmp = await wb.compare_prompt_versions(p["id"], 1, 2)
    assert "golden_response" in cmp["changed_fields"]

    # Editing a non-content field (title) does NOT bump the version.
    p3 = await wb.update_prompt(p["id"], title="Renamed")
    assert p3["current_version"] == 2

    # Collection get includes its prompt sets.
    got = await wb.get_collection(col["id"])
    assert len(got["prompt_sets"]) == 1
    assert await wb.delete_collection(col["id"]) is True


# -- session execution ------------------------------------------------------

@pytest.mark.asyncio
async def test_session_execute_scores_and_summary(SessionLocal):
    from app.evaluation.service import EvaluationSessionService, EvaluationWorkbenchService
    wb = EvaluationWorkbenchService(session_factory=SessionLocal)
    svc = EvaluationSessionService(generate_fn=fake_gen, session_factory=SessionLocal,
                                   auto_worker=False)

    col = await wb.create_collection(project_id="p1", name="C")
    ps = await wb.create_prompt_set(collection_id=col["id"], title="S")
    await wb.create_prompt(prompt_set_id=ps["id"], prompt="Capital of France?",
                           golden_response=GOLDEN, acceptance_criteria={"must_include": ["Paris"]})

    models = [{"target_model": "good", "label": "Good"},
              {"target_model": "bad", "label": "Bad"}]
    sched = await svc.schedule(models=models, prompt_set_ids=[ps["id"]], project_id="p1",
                               similarity="text")
    assert sched["total_tasks"] == 2
    await svc.drain()

    session = await svc.get(sched["id"])
    assert session["status"] == "completed"
    summ = session["summary"]
    assert summ["pass_rate"] == 50.0            # good passes, bad fails
    assert summ["total_results"] == 2
    assert summ["best_model"]["label"] == "Good"
    assert summ["closest_to_baseline"]["label"] == "Good"

    results = await svc.results(sched["id"])
    assert len(results) == 2
    good = next(r for r in results if r["label"] == "Good")
    bad = next(r for r in results if r["label"] == "Bad")
    assert good["verdict"] == "pass" and good["similarity_score"] == 100.0
    assert bad["verdict"] == "fail"
    assert bad["metrics"]["latency_ms"] == 500
    # bad is missing "Paris" → instruction regression recorded
    assert any(x["type"] == "instruction" for x in bad["regressions"])

    reg = await svc.regressions(sched["id"])
    assert reg["total"] >= 1
    only_fail = await svc.results(sched["id"], verdict="fail")
    assert len(only_fail) == 1


@pytest.mark.asyncio
async def test_failed_session_always_persists_error(SessionLocal):
    """A failing evaluation worker must never leave status=failed with a null error."""
    from app.evaluation.service import EvaluationSessionService

    async def boom(models, prompts, config):
        raise RuntimeError("runtime exploded")

    svc = EvaluationSessionService(run_fn=boom, session_factory=SessionLocal, auto_worker=False)
    sched = await svc.schedule(models=[{"target_model": "qwen3:8b"}], prompt_set_ids=[])
    await svc.drain()
    got = await svc.get(sched["id"])
    assert got["status"] == "failed"
    assert got["error"] and "runtime exploded" in got["error"]
    assert got["completed_at"] is not None


@pytest.mark.asyncio
async def test_session_cancel_pending(SessionLocal):
    from app.evaluation.service import EvaluationSessionService
    svc = EvaluationSessionService(generate_fn=fake_gen, session_factory=SessionLocal,
                                   auto_worker=False)
    sched = await svc.schedule(models=[{"target_model": "good"}], prompt_set_ids=[])
    await svc.cancel(sched["id"])
    await svc.drain()
    assert (await svc.get(sched["id"]))["status"] == "cancelled"


# -- API --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_similarity_and_regression_types(client):
    sims = (await client.get("/api/evaluation-workbench/similarity-providers")).json()
    assert any(s["key"] == "text" for s in sims)
    types = (await client.get("/api/evaluation-workbench/regression-types")).json()
    assert any(t["type"] == "safety" for t in types)


@pytest.mark.asyncio
async def test_api_full_flow(client, SessionLocal, monkeypatch):
    from app.evaluation import service as svc_mod
    monkeypatch.setattr(svc_mod.evaluation_workbench, "_session_factory", SessionLocal)
    monkeypatch.setattr(svc_mod.evaluation_sessions, "_session_factory", SessionLocal)
    monkeypatch.setattr(svc_mod.evaluation_sessions, "_generate_fn", fake_gen)
    monkeypatch.setattr(svc_mod.evaluation_sessions, "_auto_worker", False)

    col = (await client.post("/api/evaluation-workbench/collections",
                             json={"name": "Coding", "project_id": "p1"})).json()
    ps = (await client.post("/api/evaluation-workbench/prompt-sets",
                            json={"collection_id": col["id"], "title": "Basics"})).json()
    pr = (await client.post("/api/evaluation-workbench/prompts",
                            json={"prompt_set_id": ps["id"], "prompt": "Capital of France?",
                                  "golden_response": GOLDEN})).json()
    assert pr["current_version"] == 1

    # version history endpoint
    vers = (await client.get(f"/api/evaluation-workbench/prompts/{pr['id']}/versions")).json()
    assert len(vers) == 1

    sess = await client.post("/api/evaluation-workbench/sessions", json={
        "prompt_set_ids": [ps["id"]], "models": ["good", "bad"], "project_id": "p1"})
    assert sess.status_code == 201
    sid = sess.json()["id"]
    await svc_mod.evaluation_sessions.drain()

    got = (await client.get(f"/api/evaluation-workbench/sessions/{sid}")).json()
    assert got["status"] == "completed" and got["summary"]["pass_rate"] == 50.0
    results = (await client.get(f"/api/evaluation-workbench/sessions/{sid}/results")).json()
    assert len(results) == 2
    regs = (await client.get(f"/api/evaluation-workbench/sessions/{sid}/regressions")).json()
    assert "by_type" in regs

    hist = (await client.get("/api/evaluation-workbench/sessions",
                             params={"project_id": "p1"})).json()
    assert len(hist) == 1


@pytest.mark.asyncio
async def test_api_session_requires_prompts_and_models(client):
    r1 = await client.post("/api/evaluation-workbench/sessions",
                           json={"prompt_set_ids": [], "models": ["m"]})
    assert r1.status_code == 400
    r2 = await client.post("/api/evaluation-workbench/sessions",
                           json={"prompt_set_ids": ["x"], "models": []})
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_api_diff(client):
    out = (await client.post("/api/evaluation-workbench/diff",
                             json={"reference": '{"a":1,"b":2}', "candidate": '{"a":1}'})).json()
    assert out["json_diff"]["valid"] and "b" in out["json_diff"]["missing_keys"]


# -- assistant --------------------------------------------------------------

@pytest.mark.asyncio
async def test_assistant_evaluation_answers(client, monkeypatch):
    from app.evaluation import evaluation_sessions

    session = {"id": "s1", "name": "Sess", "status": "completed", "summary": {
        "pass_rate": 50.0, "quality_score": 70.0, "regression_score": 80.0,
        "consistency_score": 90.0, "overall_score": 72.0, "total_results": 2,
        "best_model": {"label": "Good", "pass_rate": 100.0, "mean_similarity": 100.0, "regressions": 0},
        "closest_to_baseline": {"label": "Good", "mean_similarity": 100.0},
    }}

    async def fake_get(sid):
        return session if sid == "s1" else None

    async def fake_results(sid, verdict=None, regression_type=None):
        rows = [{"prompt_title": "Capital of France", "label": "Bad", "verdict": "fail",
                 "regressions": [{"label": "Instruction Regression", "severity": "high",
                                  "summary": "missing Paris", "type": "instruction"}]},
                {"prompt_title": "Capital of France", "label": "Good", "verdict": "pass",
                 "regressions": []}]
        if verdict:
            rows = [r for r in rows if r["verdict"] == verdict]
        return rows

    monkeypatch.setattr(evaluation_sessions, "get", fake_get)
    monkeypatch.setattr(evaluation_sessions, "results", fake_results)

    failed = (await client.post("/api/assistant/ask",
                                json={"question": "which prompts failed?", "session_id": "s1"})).json()
    assert "Capital of France" in failed["answer"]

    closest = (await client.post("/api/assistant/ask", json={
        "question": "which model stayed closest to the baseline?", "session_id": "s1"})).json()
    assert "Good" in closest["answer"]

    retrain = (await client.post("/api/assistant/ask",
                                 json={"question": "should I retrain?", "session_id": "s1"})).json()
    assert "50" in retrain["answer"]


# -- report integration -----------------------------------------------------

@pytest.mark.asyncio
async def test_training_report_includes_evaluation(client, db_session):
    from app.db.models import TrainingRun, WorkbenchSession

    rid = str(uuid4())
    db_session.add(TrainingRun(id=rid, name="RunX", base_model="m", method="lora",
                               backend="simulation", status="completed", project_id="p1"))
    db_session.add(WorkbenchSession(
        id=str(uuid4()), run_id=rid, project_id="p1", name="Eval", status="completed",
        models=[{"target_model": "m", "label": "Good"}], prompt_set_ids=["x"],
        summary={"pass_rate": 90.0, "regression_breakdown": {},
                 "best_model": {"label": "Good", "pass_rate": 90.0}}))
    await db_session.commit()

    rep = (await client.get(f"/api/training/{rid}/report")).json()
    assert rep["evaluation"] and rep["evaluation"]["pass_rate"] == 90.0
    assert "Deploy" in (rep["deployment_recommendation"] or "")
