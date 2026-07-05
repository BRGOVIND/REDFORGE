"""Tests for the Sprint 2 evaluation engine.

Covers: profile loading/validation/override, runtime estimation (incl. history),
deterministic execution-plan generation, the scheduler (plan + session creation,
lifecycle passthrough, retry targeting), cross-platform resource detection, and
the evaluation-engine API.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.attacks.library import seed_attacks
from app.db.database import Base
from app.db.models import TestRun
from app.evaluation_profiles import profile_registry
from app.evaluation_profiles.profile import ALL_CATEGORIES, EvaluationProfile
from app.evaluation_profiles.profile_loader import (
    ProfileLoadError,
    load_profiles,
)
from app.resources.resource_monitor import (
    GpuInfo,
    ResourceSnapshot,
    assess_plan,
    detect_gpu,
    detect_resources,
)
from app.runtime.model_sizes import estimate_model_ram_mb, parse_param_billions
from app.runtime.runtime_estimator import (
    DEFAULT_LATENCY_MS,
    EstimationInputs,
    estimate_runtime,
    gather_latency_stats,
)
from app.scheduler.evaluation_scheduler import EvaluationScheduler
from app.scheduler.plan_builder import PlanBuildError, build_execution_plan
from app.sessions.constants import EventType, SessionStatus
from app.sessions.event_repository import EventRepository
from app.sessions.session_manager import SessionManager


# ---------------------------------------------------------------------------
# DB fixtures (in-memory, shared connection, seeded with the real attack library)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mem_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


# ===========================================================================
# Profiles: loading & validation
# ===========================================================================

def test_all_builtin_profiles_load():
    profiles = load_profiles()
    assert set(profiles) == {
        "quick_scan", "standard", "thorough", "comparative", "exhaustive"
    }


def test_profile_fields_present():
    p = load_profiles()["standard"]
    assert p.display_name == "Standard"
    assert p.evaluator == "llm_judge"
    assert p.judge_model == "llama3.2"
    assert p.mutation.enabled and p.mutation.count == 2
    assert p.mutation_multiplier == 3


def test_registry_lookup_and_list():
    names = [p.name for p in profile_registry.list_profiles()]
    assert "quick_scan" in names
    assert profile_registry.get_profile("quick_scan").display_name == "Quick Scan"
    assert profile_registry.get_profile("nonexistent") is None
    assert profile_registry.has_profile("exhaustive")


def test_llm_judge_requires_judge_model():
    with pytest.raises(ValueError):
        EvaluationProfile(
            name="bad", display_name="B", description="d", purpose="p",
            dataset="attack_library", evaluator="llm_judge",
        )


def test_extra_field_rejected():
    with pytest.raises(ValueError):
        EvaluationProfile(
            name="bad", display_name="B", description="d", purpose="p",
            dataset="attack_library", surprise=123,
        )


def test_all_plus_specific_category_rejected():
    with pytest.raises(ValueError):
        EvaluationProfile(
            name="bad", display_name="B", description="d", purpose="p",
            dataset="attack_library", categories=[ALL_CATEGORIES, "JAILBREAK"],
        )


def test_mutation_disabled_zeroes_count():
    p = EvaluationProfile(
        name="m", display_name="M", description="d", purpose="p",
        dataset="attack_library",
        mutation={"enabled": False, "count": 9, "mode": "adaptive"},
    )
    assert p.mutation.count == 0
    assert p.mutation.mode == "none"
    assert p.mutation_multiplier == 1


def test_profile_override_directory(tmp_path, monkeypatch):
    custom = {
        "name": "custom_scan", "display_name": "Custom", "description": "d",
        "purpose": "p", "dataset": "attack_library", "categories": ["all"],
        "attacks_per_category": 3, "evaluator": "heuristic",
    }
    (tmp_path / "custom_scan.json").write_text(json.dumps(custom), encoding="utf-8")
    monkeypatch.setenv("REDFORGE_PROFILES_DIR", str(tmp_path))

    profiles = load_profiles()
    assert "custom_scan" in profiles
    assert "quick_scan" in profiles  # builtins still present


def test_profile_loader_rejects_invalid_json(tmp_path, monkeypatch):
    (tmp_path / "broken.json").write_text("{ not valid json ", encoding="utf-8")
    monkeypatch.setenv("REDFORGE_PROFILES_DIR", str(tmp_path))
    with pytest.raises(ProfileLoadError):
        load_profiles()


# ===========================================================================
# Runtime estimation
# ===========================================================================

def test_model_size_parsing():
    assert parse_param_billions("llama3:8b") == 8.0
    assert parse_param_billions("qwen2.5:0.5b") == 0.5
    assert parse_param_billions("mystery-model") is None
    assert estimate_model_ram_mb("llama3:70b") > estimate_model_ram_mb("llama3:8b")


def test_estimate_llm_call_accounting():
    est = estimate_runtime(
        EstimationInputs(
            models=["m"], base_attacks_per_model=10, mutation_multiplier=3,
            passes=2, uses_judge=True, judge_model="j",
        )
    )
    # target = 10 * 3 * 2 = 60; judge doubles it => 120
    assert est.breakdown["target_calls"] == 60
    assert est.breakdown["judge_calls"] == 60
    assert est.estimated_llm_calls == 120


def test_estimate_uses_default_latency_without_history():
    est = estimate_runtime(
        EstimationInputs(models=["m"], base_attacks_per_model=10)
    )
    assert est.avg_latency_ms_used == DEFAULT_LATENCY_MS
    assert any("no latency history" in a for a in est.assumptions)


def test_estimate_sharpens_with_history():
    inputs = EstimationInputs(models=["m"], base_attacks_per_model=10)
    slow = estimate_runtime(inputs)
    fast = estimate_runtime(inputs, latency_by_model={"m": 500.0})
    assert fast.estimated_seconds < slow.estimated_seconds
    assert fast.avg_latency_ms_used == 500.0


def test_estimate_adaptive_agent_adds_calls():
    base = estimate_runtime(EstimationInputs(models=["m"], base_attacks_per_model=5))
    agent = estimate_runtime(
        EstimationInputs(models=["m"], base_attacks_per_model=5, adaptive_agent=True)
    )
    assert agent.estimated_llm_calls > base.estimated_llm_calls


@pytest.mark.asyncio
async def test_gather_latency_stats(factory):
    async with factory() as db:
        db.add_all([
            TestRun(model_name="m1", attack_id=1, latency_ms=1000),
            TestRun(model_name="m1", attack_id=2, latency_ms=2000),
            TestRun(model_name="m2", attack_id=1, latency_ms=500),
        ])
        await db.commit()
        stats = await gather_latency_stats(db, ["m1", "m2", "m3"])
    assert stats["m1"] == 1500.0
    assert stats["m2"] == 500.0
    assert "m3" not in stats  # no history


# ===========================================================================
# Execution plan generation
# ===========================================================================

@pytest.mark.asyncio
async def test_plan_is_deterministic(factory):
    p = profile_registry.get_profile("standard")
    async with factory() as db:
        plan_a = await build_execution_plan(p, ["llama3:8b"], db)
    async with factory() as db:
        plan_b = await build_execution_plan(p, ["llama3:8b"], db)
    assert plan_a.deterministic_key == plan_b.deterministic_key
    assert plan_a.model_dump() == plan_b.model_dump()


@pytest.mark.asyncio
async def test_plan_ordering_model_major_then_category(factory):
    p = profile_registry.get_profile("comparative")
    async with factory() as db:
        plan = await build_execution_plan(p, ["a:7b", "b:8b"], db)
    attack_steps = [s for s in plan.steps if s.kind == "attack"]
    # First half of attack steps belong to the first model.
    half = len(attack_steps) // 2
    assert all(s.model == "a:7b" for s in attack_steps[:half])
    assert all(s.model == "b:8b" for s in attack_steps[half:])
    # Leaderboard is the final step for a comparative profile.
    assert plan.steps[-1].kind == "leaderboard"


@pytest.mark.asyncio
async def test_plan_respects_per_category_cap(factory):
    p = profile_registry.get_profile("quick_scan")  # 5 attacks/category
    async with factory() as db:
        plan = await build_execution_plan(p, ["m:8b"], db)
    for step in plan.steps:
        if step.kind == "attack":
            assert step.base_attacks <= 5


@pytest.mark.asyncio
async def test_plan_terminal_steps(factory):
    exhaustive = profile_registry.get_profile("exhaustive")
    async with factory() as db:
        plan = await build_execution_plan(exhaustive, ["m:8b"], db)
    kinds = [s.kind for s in plan.steps]
    assert "agent" in kinds       # adaptive_agent enabled
    assert kinds[-1] == "report"  # generate_report enabled


@pytest.mark.asyncio
async def test_plan_requires_models(factory):
    p = profile_registry.get_profile("quick_scan")
    async with factory() as db:
        with pytest.raises(PlanBuildError):
            await build_execution_plan(p, [], db)


@pytest.mark.asyncio
async def test_plan_rejects_unknown_category(factory):
    bad = EvaluationProfile(
        name="badcat", display_name="B", description="d", purpose="p",
        dataset="attack_library", categories=["NOT_A_CATEGORY"],
    )
    async with factory() as db:
        with pytest.raises(PlanBuildError):
            await build_execution_plan(bad, ["m:8b"], db)


@pytest.mark.asyncio
async def test_single_model_profile_ignores_extra_models(factory):
    p = profile_registry.get_profile("quick_scan")  # multi_model = False
    async with factory() as db:
        plan = await build_execution_plan(p, ["m1:8b", "m2:8b", "m3:8b"], db)
    assert plan.models == ["m1:8b"]


# ===========================================================================
# Scheduler
# ===========================================================================

@pytest_asyncio.fixture
async def scheduler(factory):
    async def fake_gen(model, prompt):
        return ("resp", 5)
    return EvaluationScheduler(SessionManager(factory, generate_fn=fake_gen)), factory


@pytest.mark.asyncio
async def test_scheduler_creates_session_with_plan(scheduler):
    sched, factory = scheduler
    p = profile_registry.get_profile("quick_scan")
    async with factory() as db:
        session, plan = await sched.create_evaluation(p, ["m:8b"], db)

    assert session.selected_tier == "quick_scan"
    assert session.session_metadata["profile"] == "quick_scan"
    assert session.session_metadata["deterministic_key"] == plan.deterministic_key
    assert session.session_metadata["plan"]["profile"] == "quick_scan"
    assert session.selected_categories == plan.categories


@pytest.mark.asyncio
async def test_scheduler_lifecycle_passthrough(scheduler):
    sched, factory = scheduler
    p = profile_registry.get_profile("quick_scan")
    async with factory() as db:
        session, _ = await sched.create_evaluation(p, ["m:8b"], db)

    paused = await sched.pause(session.id)
    assert paused.status == SessionStatus.PAUSED
    cancelled = await sched.cancel(session.id)
    assert cancelled.status == SessionStatus.CANCELLED


@pytest.mark.asyncio
async def test_scheduler_retry_targets(scheduler):
    sched, factory = scheduler
    p = profile_registry.get_profile("quick_scan")
    async with factory() as db:
        session, _ = await sched.create_evaluation(p, ["m:8b"], db)

    # Record verdicts directly, then compute which are eligible for retry.
    async with factory() as db:
        erepo = EventRepository(db)
        await erepo.add(session_id=session.id, event_type=EventType.VERDICT_GENERATED,
                        model_name="m:8b", category="JAILBREAK", attack_name="a1", verdict="PASS")
        await erepo.add(session_id=session.id, event_type=EventType.VERDICT_GENERATED,
                        model_name="m:8b", category="JAILBREAK", attack_name="a2", verdict="FAIL")

    targets = await sched.compute_retry_targets(session.id, retry_on=["FAIL"])
    assert len(targets) == 1
    assert targets[0]["attack_name"] == "a2"
    assert targets[0]["verdict"] == "FAIL"


# ===========================================================================
# Resource detection (cross-platform)
# ===========================================================================

def test_detect_resources_does_not_throw():
    snap = detect_resources()
    assert isinstance(snap, ResourceSnapshot)
    assert snap.platform  # non-empty
    assert snap.source in ("psutil", "stdlib")
    assert snap.cpu_count is None or snap.cpu_count >= 1


def test_detect_gpu_is_cached():
    a = detect_gpu()
    b = detect_gpu()
    assert a is b  # cached instance


def _snapshot(ram_avail, gpu_avail, gpu_total=None, disk_free=100000):
    return ResourceSnapshot(
        platform="Test", source="stdlib",
        ram_total_mb=ram_avail, ram_available_mb=ram_avail,
        cpu_count=8, load_avg_1m=None,
        disk_total_mb=disk_free, disk_free_mb=disk_free,
        gpu=GpuInfo(available=gpu_avail, total_mb=gpu_total),
    )


def test_assess_warns_when_ram_exceeded():
    snap = _snapshot(ram_avail=1000, gpu_avail=True, gpu_total=99999)
    warnings = assess_plan({"estimated_ram_mb": 8000, "estimated_gpu_mb": 100}, snap)
    assert any("exceeds available RAM" in w for w in warnings)


def test_assess_warns_when_no_gpu():
    snap = _snapshot(ram_avail=99999, gpu_avail=False)
    warnings = assess_plan({"estimated_ram_mb": 10, "estimated_gpu_mb": 5000}, snap)
    assert any("No GPU detected" in w for w in warnings)


def test_assess_clean_when_resources_ample():
    snap = _snapshot(ram_avail=64000, gpu_avail=True, gpu_total=48000)
    warnings = assess_plan(
        {"estimated_ram_mb": 5000, "estimated_gpu_mb": 5000, "estimated_disk_mb": 2},
        snap,
    )
    assert warnings == []


def test_assess_is_non_blocking_returns_list():
    snap = _snapshot(ram_avail=1, gpu_avail=False)
    result = assess_plan({"estimated_ram_mb": 999999, "estimated_gpu_mb": 999999}, snap)
    assert isinstance(result, list)  # warnings only, never raises/blocks


# ===========================================================================
# API
# ===========================================================================

@pytest_asyncio.fixture
async def api_client(factory):
    from app.main import app
    from app.db.database import get_db

    db = factory()
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    await db.close()


@pytest.mark.asyncio
async def test_api_list_profiles(api_client):
    resp = await api_client.get("/api/evaluation-profiles")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert names == {"quick_scan", "standard", "thorough", "comparative", "exhaustive"}


@pytest.mark.asyncio
async def test_api_get_profile_and_404(api_client):
    ok = await api_client.get("/api/evaluation-profiles/standard")
    assert ok.status_code == 200
    assert ok.json()["display_name"] == "Standard"

    missing = await api_client.get("/api/evaluation-profiles/ghost")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_api_evaluation_plan(api_client):
    resp = await api_client.post(
        "/api/evaluation-plan",
        json={"profile": "quick_scan", "models": ["gemma:2b"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"] == "quick_scan"
    assert body["estimated_llm_calls"] > 0
    assert body["execution_steps"]
    assert "estimated_ram_mb" in body
    assert "warnings" in body
    assert body["plan"]["deterministic_key"]


@pytest.mark.asyncio
async def test_api_runtime_estimate(api_client):
    resp = await api_client.get(
        "/api/runtime-estimate",
        params={"profile": "standard", "models": ["llama3:8b"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["estimated_time"]["seconds"] >= 0
    assert body["estimated_llm_calls"] > 0


@pytest.mark.asyncio
async def test_api_plan_unknown_profile_404(api_client):
    resp = await api_client.post(
        "/api/evaluation-plan", json={"profile": "nope", "models": ["m"]}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_plan_no_models_400(api_client):
    resp = await api_client.post(
        "/api/evaluation-plan", json={"profile": "quick_scan", "models": []}
    )
    assert resp.status_code == 400
