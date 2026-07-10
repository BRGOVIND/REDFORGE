"""Onboarding recommender + model-pull tracker. Deterministic; no hardware or
network access (resources and providers are passed in / faked)."""
from __future__ import annotations

import asyncio

import pytest

from app.onboarding import recommender
from app.resources.resource_monitor import GpuInfo, ResourceSnapshot


def _snapshot(ram_avail=None, gpu=None) -> ResourceSnapshot:
    return ResourceSnapshot(
        platform="Linux", source="test",
        ram_total_mb=ram_avail, ram_available_mb=ram_avail,
        cpu_count=8, load_avg_1m=None, disk_total_mb=None, disk_free_mb=None,
        gpu=gpu or GpuInfo(available=False),
    )


# -- runtime recommendation -------------------------------------------------

def _p(name, online, label=None):
    return {"name": name, "label": label or name, "health": {"online": online}}


def test_recommends_running_local_provider():
    infos = [_p("ollama", True), _p("lmstudio", False)]
    rec = recommender.recommend_runtime(infos, default="ollama")
    assert rec["provider"] == "ollama"
    assert rec["state"] == "running"


def test_prefers_ollama_when_multiple_running():
    infos = [_p("vllm", True), _p("ollama", True)]
    rec = recommender.recommend_runtime(infos, default="ollama")
    assert rec["provider"] == "ollama"  # preference order, not list order


def test_recommends_registered_when_none_running():
    infos = [_p("ollama", False)]
    rec = recommender.recommend_runtime(infos, default="ollama")
    assert rec["provider"] == "ollama"
    assert rec["state"] == "not_running"
    assert rec["action"]


def test_missing_runtime_when_no_local_provider():
    rec = recommender.recommend_runtime([_p("openai", False)], default="ollama")
    assert rec["state"] == "missing"


# -- model recommendation ---------------------------------------------------

def test_low_ram_only_fits_small_models():
    rec = recommender.recommend_models(budget_mb=4000, budget_source="system RAM")
    fitting = [m for m in rec["models"] if m["fits"]]
    assert fitting, "at least a tiny model should fit"
    # 70B must never be recommended on 4 GB.
    assert all(m["params_b"] < 70 for m in fitting)
    assert rec["recommended"] is not None


def test_high_vram_fits_large_models():
    rec = recommender.recommend_models(budget_mb=48000, budget_source="vram")
    names = {m["name"]: m for m in rec["models"]}
    assert names["llama3.3:70b"]["fits"] is True
    assert rec["recommended"] == "llama3.3:70b"  # largest fitting


def test_recommended_is_largest_fitting():
    rec = recommender.recommend_models(budget_mb=12000, budget_source="system RAM")
    rec_name = rec["recommended"]
    rec_entry = next(m for m in rec["models"] if m["name"] == rec_name)
    # Nothing larger than the recommended model should also fit.
    larger_fitting = [m for m in rec["models"] if m["params_b"] > rec_entry["params_b"] and m["fits"]]
    assert not larger_fitting


def test_unknown_budget_marks_all_fit():
    rec = recommender.recommend_models(budget_mb=None, budget_source="unknown")
    assert all(m["fits"] for m in rec["models"])


def test_memory_budget_prefers_vram():
    snap = _snapshot(ram_avail=16000, gpu=GpuInfo(available=True, total_mb=8000, backend="cuda"))
    budget, source = recommender._memory_budget_mb(snap)
    assert budget == 8000 and source == "vram"


def test_memory_budget_falls_back_to_ram():
    snap = _snapshot(ram_avail=16000)
    budget, source = recommender._memory_budget_mb(snap)
    assert budget == 16000 and source == "system RAM"


# -- pull tracker -----------------------------------------------------------

@pytest.mark.asyncio
async def test_pull_tracker_tracks_progress(monkeypatch):
    from app.api import onboarding as ob

    class FakeProvider:
        name = "ollama"
        supports_pull = True

        async def pull_model(self, model):
            yield {"status": "pulling", "completed": 50 * 1024 * 1024, "total": 100 * 1024 * 1024}
            yield {"status": "success"}

    class FakeRuntime:
        provider = FakeProvider()

    monkeypatch.setattr(ob, "get_runtime", lambda: FakeRuntime())

    tracker = ob._PullTracker()
    state = tracker.start("llama3.2:1b")
    assert state["status"] == "starting"
    await tracker._tasks["llama3.2:1b"]  # let it finish

    final = tracker.snapshot("llama3.2:1b")
    assert final["done"] is True
    assert final["error"] is None
    assert final["percent"] == 100.0


@pytest.mark.asyncio
async def test_pull_tracker_records_error(monkeypatch):
    from app.api import onboarding as ob
    from app.runtime.errors import ModelNotFound

    class FakeProvider:
        name = "ollama"
        supports_pull = True

        async def pull_model(self, model):
            raise ModelNotFound("no such model")
            yield  # pragma: no cover

    class FakeRuntime:
        provider = FakeProvider()

    monkeypatch.setattr(ob, "get_runtime", lambda: FakeRuntime())
    tracker = ob._PullTracker()
    tracker.start("bogus")
    await tracker._tasks["bogus"]
    snap = tracker.snapshot("bogus")
    assert snap["done"] is True
    assert snap["error"]
