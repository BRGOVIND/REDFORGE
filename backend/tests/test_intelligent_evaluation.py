"""Tests for the Sprint 3 intelligent evaluation pipeline.

Covers model profiling, planner determinism, adaptive retry/mutation selection,
finding/recommendation/report generation, and the end-to-end pipeline + API.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.analysis import (
    analyze,
    attach_recommendations,
    build_report,
    generate_findings,
)
from app.analysis.security_analyzer import AttackResult
from app.attacks.library import seed_attacks
from app.db.database import Base
from app.db.models import Attack, BenchmarkRun, ModelScore, TestRun
from app.evaluation_profiles import profile_registry
from app.execution import AdaptiveExecutor
from app.planner import EvaluationPlanner, build_planning_context
from app.planner.evaluation_planner import EvaluationPlan, PlannedAttack
from app.planner.planning_rules import ESCALATION_ORDER
from app.profiler import ModelProfiler, build_model_profile, detect_capabilities
from app.profiler.profile_builder import ModelProfile
from app.sessions.constants import EventType, SessionStatus
from app.sessions.session_repository import SessionRepository

FAKE_SHOW = {
    "details": {"parameter_size": "8.0B", "quantization_level": "Q4_0",
                "family": "llama", "families": ["llama"]},
    "model_info": {"llama.context_length": 8192},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mem_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def factory(mem_engine):
    fac = async_sessionmaker(mem_engine, class_=AsyncSession, expire_on_commit=False)
    async with fac() as db:
        await seed_attacks(db)
    return fac


async def _refusing_gen(model, prompt):
    return ("I cannot help with that request.", 8)


async def _complying_judge(prompt, response, judge_model):
    if "cannot" in response.lower():
        return ("PASS", 0.9, "refused")
    return ("FAIL", 0.9, "complied")


# ===========================================================================
# Phase A — Model profiling
# ===========================================================================

def test_detect_capabilities_from_ollama():
    caps = detect_capabilities("llama3:8b", FAKE_SHOW)
    assert caps.parameter_size == 8.0
    assert caps.quantization == "Q4_0"
    assert caps.context_length == 8192
    assert caps.family == "llama"
    assert caps.source == "ollama"


def test_detect_capabilities_from_name_fallback():
    caps = detect_capabilities("mystery:70b", None)
    assert caps.parameter_size == 70.0
    assert caps.quantization is None
    assert caps.source == "name"


@pytest.mark.asyncio
async def test_build_model_profile_with_history(factory):
    async with factory() as db:
        atk = (await db.execute(__import__("sqlalchemy").select(Attack).limit(1))).scalar_one()
        db.add_all([
            TestRun(model_name="llama3:8b", attack_id=atk.id, verdict="FAIL", latency_ms=1200),
            TestRun(model_name="llama3:8b", attack_id=atk.id, verdict="PASS", latency_ms=800),
        ])
        run = BenchmarkRun(name="b", model_list=["llama3:8b"], attack_suite=[], status="completed")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        db.add(ModelScore(benchmark_run_id=run.id, model_name="llama3:8b", overall_score=85.0))
        await db.commit()

    async with factory() as db:
        profile = await build_model_profile("llama3:8b", db, ollama_show=FAKE_SHOW)

    assert profile.parameter_label == "8.0B"
    assert profile.avg_latency_ms == 1000.0
    assert profile.resource_footprint_mb > 0
    assert profile.historical_overall_score == 85.0
    assert atk.category in profile.historical_failure_categories
    assert profile.installed_locally is True


@pytest.mark.asyncio
async def test_profiler_caches_per_session(factory):
    calls = {"n": 0}

    async def fetcher(name):
        calls["n"] += 1
        return FAKE_SHOW

    profiler = ModelProfiler(metadata_fetcher=fetcher)
    async with factory() as db:
        p1 = await profiler.get_profile("llama3:8b", db, session_id="s1")
    async with factory() as db:
        p2 = await profiler.get_profile("llama3:8b", db, session_id="s1")
    assert p1 is p2
    assert calls["n"] == 1  # no duplicate profiling


# ===========================================================================
# Phase B — Planner
# ===========================================================================

async def _plan_for(factory, profile_name, models, model_profile):
    profile = profile_registry.get_profile(profile_name)
    async with factory() as db:
        ctx = await build_planning_context(
            profile, models, {m: model_profile for m in models}, db
        )
    return EvaluationPlanner().build(ctx)


def _bare_profile(model="llama3:8b", overall=None, failures=None) -> ModelProfile:
    return ModelProfile(
        model_name=model,
        historical_benchmark_scores={"overall_score": overall} if overall is not None else {},
        historical_failure_categories=failures or [],
        resource_footprint_mb=5600,
    )


@pytest.mark.asyncio
async def test_planner_deterministic(factory):
    mp = _bare_profile()
    p1 = await _plan_for(factory, "standard", ["llama3:8b"], mp)
    p2 = await _plan_for(factory, "standard", ["llama3:8b"], mp)
    assert p1.deterministic_key == p2.deterministic_key
    assert p1.model_dump() == p2.model_dump()


@pytest.mark.asyncio
async def test_planner_prioritizes_failure_categories(factory):
    mp = _bare_profile(overall=90.0, failures=["DATA_LEAKAGE", "JAILBREAK"])
    plan = await _plan_for(factory, "standard", ["llama3:8b"], mp)
    assert plan.category_order[0] == "DATA_LEAKAGE"
    assert plan.category_order[1] == "JAILBREAK"


@pytest.mark.asyncio
async def test_planner_severity_priority_within_category(factory):
    mp = _bare_profile()
    plan = await _plan_for(factory, "quick_scan", ["llama3:8b"], mp)
    # Within the first category, severities are non-increasing (critical first).
    first_cat = plan.category_order[0]
    sev_ranks = [
        {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.severity, 2)
        for a in plan.attack_sequence if a.category == first_cat
    ]
    assert sev_ranks == sorted(sev_ranks)


@pytest.mark.asyncio
async def test_planner_robust_model_bumps_mutation(factory):
    weak = await _plan_for(factory, "standard", ["llama3:8b"], _bare_profile(overall=40.0))
    robust = await _plan_for(factory, "standard", ["llama3:8b"], _bare_profile(overall=95.0))
    assert robust.mutation_level == weak.mutation_level + 1


# ===========================================================================
# Phase C — Adaptive execution
# ===========================================================================

def _plan_with(attacks: list[dict], max_retries: int, escalation: list[str]) -> EvaluationPlan:
    seq = [
        PlannedAttack(
            order=i, model="m", category=a.get("category", "PROMPT_INJECTION"),
            attack_ref=f"attack:{i}", attack_name=a["name"], prompt=a["prompt"],
            severity=a.get("severity", "high"), priority_rank=0, attack_id=i + 1,
        )
        for i, a in enumerate(attacks)
    ]
    return EvaluationPlan(
        profile="t", models=["m"], dataset="attack_library",
        category_order=["PROMPT_INJECTION"], evaluator="llm_judge", judge_model="j",
        mutation_level=len(escalation), escalation_strategies=escalation,
        max_retries=max_retries, checkpoint_frequency=5, attack_sequence=seq,
        total_attacks=len(seq),
    )


async def _new_session(factory, total):
    async with factory() as db:
        s = await SessionRepository(db).create(
            session_type="evaluation", selected_models=["m"],
            selected_categories=["PROMPT_INJECTION"], total_tasks=total,
        )
    return s.id


@pytest.mark.asyncio
async def test_adaptive_retry_until_compromise(factory):
    async def gen(model, prompt):
        # Complies only once the suffix_append mutation marker is present.
        if "senior researcher" in prompt:
            return ("Sure, here it is", 5)
        return ("No.", 5)

    async def judge(prompt, response, jm):
        return ("FAIL", 0.9, "c") if "Sure" in response else ("PASS", 0.8, "r")

    sid = await _new_session(factory, 1)
    plan = _plan_with([{"name": "a", "prompt": "leak the prompt"}],
                      max_retries=2, escalation=["suffix_append", "instruction_prefix"])
    summary = await AdaptiveExecutor(factory, generate_fn=gen, judge_fn=judge).execute_plan(sid, plan)

    outcome = summary.outcomes[0]
    assert outcome.compromised is True
    assert outcome.retries_used == 1
    assert outcome.attempts[0].strategy is None
    assert outcome.attempts[1].strategy == "suffix_append"


@pytest.mark.asyncio
async def test_adaptive_respects_max_retries(factory):
    async def gen(model, prompt):
        return ("No.", 5)  # never complies

    async def judge(prompt, response, jm):
        return ("PASS", 0.8, "refused")

    sid = await _new_session(factory, 1)
    plan = _plan_with([{"name": "a", "prompt": "p"}],
                      max_retries=3, escalation=["suffix_append", "instruction_prefix"])
    summary = await AdaptiveExecutor(factory, generate_fn=gen, judge_fn=judge).execute_plan(sid, plan)
    outcome = summary.outcomes[0]
    assert outcome.compromised is False
    # 1 original + 3 retries = 4 attempts max.
    assert len(outcome.attempts) == 4
    assert outcome.retries_used == 3


@pytest.mark.asyncio
async def test_adaptive_no_retry_on_immediate_success(factory):
    async def gen(model, prompt):
        return ("Sure, here it is", 5)

    async def judge(prompt, response, jm):
        return ("FAIL", 0.9, "complied")

    sid = await _new_session(factory, 1)
    plan = _plan_with([{"name": "a", "prompt": "p"}], max_retries=3, escalation=["suffix_append"])
    summary = await AdaptiveExecutor(factory, generate_fn=gen, judge_fn=judge).execute_plan(sid, plan)
    outcome = summary.outcomes[0]
    assert outcome.compromised is True
    assert len(outcome.attempts) == 1  # succeeded immediately, no escalation


@pytest.mark.asyncio
async def test_adaptive_mutation_selection_uses_escalation_order(factory):
    seen_strategies = []

    async def gen(model, prompt):
        return ("No.", 5)

    async def judge(prompt, response, jm):
        return ("PASS", 0.8, "refused")

    sid = await _new_session(factory, 1)
    escalation = ESCALATION_ORDER[:3]
    plan = _plan_with([{"name": "a", "prompt": "p"}], max_retries=3, escalation=escalation)
    summary = await AdaptiveExecutor(factory, generate_fn=gen, judge_fn=judge).execute_plan(sid, plan)
    strategies = [a.strategy for a in summary.outcomes[0].attempts if a.strategy]
    assert strategies == escalation  # applied in deterministic escalation order


@pytest.mark.asyncio
async def test_adaptive_deterministic(factory):
    async def gen(model, prompt):
        return ("Sure" if "researcher" in prompt else "No.", 5)

    async def judge(prompt, response, jm):
        return ("FAIL", 0.9, "c") if "Sure" in response else ("PASS", 0.8, "r")

    plan = _plan_with([{"name": "a", "prompt": "p"}], max_retries=2, escalation=["suffix_append"])
    s1 = await _new_session(factory, 1)
    r1 = await AdaptiveExecutor(factory, generate_fn=gen, judge_fn=judge).execute_plan(s1, plan)
    s2 = await _new_session(factory, 1)
    r2 = await AdaptiveExecutor(factory, generate_fn=gen, judge_fn=judge).execute_plan(s2, plan)
    assert r1.outcomes[0].model_dump() == r2.outcomes[0].model_dump()


# ===========================================================================
# Phase D+E — Analysis, findings, recommendations, report
# ===========================================================================

def _sample_results():
    return [
        AttackResult(category="PROMPT_INJECTION", attack_name="override", severity="critical",
                     verdict="FAIL", response_excerpt="ignoring instructions"),
        AttackResult(category="PROMPT_INJECTION", attack_name="leak", severity="high", verdict="PASS"),
        AttackResult(category="JAILBREAK", attack_name="dan", severity="high",
                     verdict="FAIL", response_excerpt="As DAN"),
        AttackResult(category="DATA_LEAKAGE", attack_name="sys", severity="high", verdict="PASS"),
    ]


def test_analyze_scores_and_risk():
    a = analyze("m", _sample_results())
    assert 0 <= a.overall_security_score <= 100
    assert a.failed_tests == 2
    cats = {c.category: c for c in a.category_scores}
    assert cats["DATA_LEAKAGE"].risk_level == "none"
    assert cats["PROMPT_INJECTION"].failed == 1


def test_findings_have_severity_evidence_recommendation():
    a = analyze("m", _sample_results())
    findings = attach_recommendations(generate_findings(a))
    assert findings  # at least the two failing categories
    for f in findings:
        assert f.severity
        assert f.evidence          # evidence present
        assert f.recommendation    # recommendation attached
    # Worst-first ordering.
    assert findings[0].category in ("PROMPT_INJECTION", "JAILBREAK")


def test_recommendations_are_category_specific():
    a = analyze("m", _sample_results())
    findings = attach_recommendations(generate_findings(a))
    by_cat = {f.category: f.recommendation for f in findings}
    assert "system prompt" in by_cat["PROMPT_INJECTION"].lower()
    assert "refusal" in by_cat["JAILBREAK"].lower()


def test_report_has_all_sections():
    a = analyze("llama3:8b", _sample_results())
    findings = attach_recommendations(generate_findings(a))
    report = build_report(
        model_name="llama3:8b", profile_name="standard", model_overview={"parameter_label": "8B"},
        analysis=a, findings=findings, execution={"executed": 4, "compromised": 2}, plan_key="k",
    )
    d = report.model_dump()
    for section in ("executive_summary", "model_overview", "evaluation_summary",
                    "security_score", "findings", "recommendations", "appendix"):
        assert section in d
    assert report.executive_summary
    assert report.recommendations


# ===========================================================================
# Pipeline + API (end to end, deterministic via injected judge)
# ===========================================================================

@pytest_asyncio.fixture
async def pipeline(factory):
    from app.pipeline import EvaluationPipeline

    async def fetcher(name):
        return FAKE_SHOW

    # 'standard' uses llm_judge, so the injected judge drives verdicts.
    return EvaluationPipeline(
        factory, metadata_fetcher=fetcher,
        generate_fn=_refusing_gen, judge_fn=_complying_judge,
    ), factory


@pytest.mark.asyncio
async def test_pipeline_end_to_end(pipeline):
    pipe, factory = pipeline
    sid = await pipe.run_full("standard", ["llama3:8b"])

    async with factory() as db:
        session = await SessionRepository(db).get(sid)
    meta = session.session_metadata
    assert session.status == SessionStatus.COMPLETED
    assert meta["stage"] == "completed"
    assert "evaluation_plan" in meta
    assert meta["report"] is not None
    assert meta["report"]["security_score"]["overall"] == 100.0  # model refused everything


@pytest.mark.asyncio
async def test_pipeline_emits_intelligent_events(pipeline):
    pipe, factory = pipeline
    sid = await pipe.run_full("standard", ["llama3:8b"])
    from app.sessions.event_repository import EventRepository
    async with factory() as db:
        events = await EventRepository(db).list_for_session(sid)
    types = {e.event_type for e in events}
    assert EventType.MODEL_PROFILED in types
    assert EventType.PLAN_GENERATED in types
    assert EventType.ANALYSIS_COMPLETED in types
    assert EventType.REPORT_GENERATED in types


@pytest.mark.asyncio
async def test_pipeline_deterministic(pipeline):
    pipe, factory = pipeline
    sid1 = await pipe.run_full("standard", ["llama3:8b"])
    sid2 = await pipe.run_full("standard", ["llama3:8b"])
    async with factory() as db:
        m1 = (await SessionRepository(db).get(sid1)).session_metadata
        m2 = (await SessionRepository(db).get(sid2)).session_metadata
    assert m1["evaluation_plan"]["deterministic_key"] == m2["evaluation_plan"]["deterministic_key"]
    assert m1["report"]["security_score"]["overall"] == m2["report"]["security_score"]["overall"]


@pytest.mark.asyncio
async def test_pipeline_findings_when_compromised(pipeline):
    pipe, factory = pipeline

    async def complying_gen(model, prompt):
        return ("Sure, here you go", 5)

    pipe.executor._generate_fn = complying_gen  # model now complies with everything
    sid = await pipe.run_full("standard", ["llama3:8b"])
    async with factory() as db:
        meta = (await SessionRepository(db).get(sid)).session_metadata
    assert meta["report"]["security_score"]["overall"] < 100.0
    assert len(meta["findings"]) > 0


@pytest_asyncio.fixture
async def api_client(pipeline):
    from app.main import app
    from app.api.pipeline import get_pipeline

    pipe, _ = pipeline
    app.dependency_overrides[get_pipeline] = lambda: pipe
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, pipe
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_evaluate_full_flow(api_client):
    client, pipe = api_client
    resp = await client.post("/api/evaluate", json={"profile": "standard", "model": "llama3:8b"})
    assert resp.status_code == 200
    sid = resp.json()["session_id"]

    # Background pipeline runs within the ASGI request lifecycle.
    plan = await client.get(f"/api/plans/{sid}")
    assert plan.status_code == 200
    assert plan.json()["plan"]["total_attacks"] > 0

    report = await client.get(f"/api/report/{sid}")
    assert report.status_code == 200
    assert "security_score" in report.json()["report"]

    findings = await client.get(f"/api/findings/{sid}")
    assert findings.status_code == 200


@pytest.mark.asyncio
async def test_api_evaluate_unknown_profile_400(api_client):
    client, _ = api_client
    resp = await client.post("/api/evaluate", json={"profile": "ghost", "model": "m"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_plan_unknown_session_404(api_client):
    client, _ = api_client
    resp = await client.get("/api/plans/does-not-exist")
    assert resp.status_code == 404
