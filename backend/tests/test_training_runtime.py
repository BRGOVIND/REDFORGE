"""Training Runtime — detection, planning, state durability, and the no-silent-
fallback guarantees.

Nothing here touches the network or installs anything: the hardware probe and the
managed-interpreter probe are both injected, so the full decision matrix is
exercised on a bare CI runner in milliseconds.
"""
from __future__ import annotations

import json

import pytest

from app.training import manager
from app.training_runtime import paths
from app.training_runtime.detector import build_plan
from app.training_runtime.domain import GpuInfo, PackageCheck, RuntimeReport
from app.training_runtime.installer import InstallState
from app.training_runtime.service import TrainingRuntimeService


# --- install planning -------------------------------------------------------

def test_plan_picks_newest_cuda_the_driver_supports():
    plan = build_plan(GpuInfo(available=True, name="RTX 4090", vram_mb=24000, cuda_version="12.6"))
    assert plan.variant == "cu126"
    assert "cu126" in plan.torch_index_url


def test_plan_does_not_exceed_the_driver_cuda():
    """A CUDA 12.1 driver must not be handed cu126 wheels — they will not load."""
    plan = build_plan(GpuInfo(available=True, name="RTX 2060", vram_mb=6000, cuda_version="12.1"))
    assert plan.variant == "cu121"


def test_plan_falls_back_for_ancient_drivers():
    plan = build_plan(GpuInfo(available=True, name="GTX 1080", vram_mb=8000, cuda_version="11.2"))
    assert plan.variant == "cu118"
    assert any("driver is old" in w for w in plan.warnings)


def test_plan_without_gpu_is_cpu_and_warns_honestly():
    plan = build_plan(GpuInfo(available=False))
    assert plan.variant == "cpu"
    assert "cpu" in plan.torch_index_url
    # The user must be told this is impractical rather than discovering it later.
    assert any("slow" in w.lower() for w in plan.warnings)


def test_plan_warns_on_low_vram():
    plan = build_plan(GpuInfo(available=True, name="GTX 1650", vram_mb=4096, cuda_version="12.4"))
    assert any("VRAM" in w for w in plan.warnings)


def test_plan_includes_every_required_package():
    plan = build_plan(GpuInfo(available=True, cuda_version="12.4"))
    for required in ("torch", "transformers", "peft", "unsloth", "trl", "accelerate"):
        assert required in plan.packages


# --- domain -----------------------------------------------------------------

def test_report_ready_only_when_status_is_ready():
    def report(status: str) -> RuntimeReport:
        return RuntimeReport(status=status, root="/tmp", python_executable=None,
                             python_version=None, gpu=GpuInfo(), packages=[])
    assert report("ready").ready is True
    for status in ("absent", "partial", "broken", "installing"):
        assert report(status).ready is False


def test_missing_required_ignores_optional_packages():
    rep = RuntimeReport(
        status="partial", root="/tmp", python_executable=None, python_version=None,
        gpu=GpuInfo(),
        packages=[
            PackageCheck("torch", "PyTorch", True, installed=False),
            PackageCheck("bitsandbytes", "bitsandbytes", False, installed=False),
        ],
    )
    assert rep.missing_required == ["PyTorch"]


# --- install state durability ----------------------------------------------

def test_install_state_survives_and_resumes(tmp_path):
    """The resume guarantee: completed phases persist across process restarts."""
    state = InstallState(tmp_path / "install-state.json")
    state.reset()
    state.complete_phase("environment")
    state.complete_phase("torch")

    reloaded = InstallState(tmp_path / "install-state.json")
    assert reloaded.completed() == {"environment", "torch"}
    assert reloaded.read().get("started_at")


def test_install_state_tolerates_a_corrupt_file(tmp_path):
    """A power failure mid-write must not wedge the installer."""
    path = tmp_path / "install-state.json"
    path.write_text("{ this is not json", encoding="utf-8")
    state = InstallState(path)
    assert state.read() == {}
    assert state.completed() == set()
    state.complete_phase("environment")
    assert state.completed() == {"environment"}


def test_install_state_write_is_atomic(tmp_path):
    state = InstallState(tmp_path / "install-state.json")
    state.write({"a": 1})
    assert json.loads((tmp_path / "install-state.json").read_text())["a"] == 1
    # The temp file must not be left behind.
    assert not (tmp_path / "install-state.tmp").exists()


# --- paths ------------------------------------------------------------------

def test_runtime_root_honours_explicit_override(monkeypatch, tmp_path):
    monkeypatch.setenv("REDFORGE_TRAINING_RUNTIME", str(tmp_path / "custom"))
    assert paths.runtime_root() == tmp_path / "custom"


def test_runtime_root_follows_redforge_home_for_portable(monkeypatch, tmp_path):
    monkeypatch.delenv("REDFORGE_TRAINING_RUNTIME", raising=False)
    monkeypatch.setenv("REDFORGE_HOME", str(tmp_path / "portable"))
    assert paths.runtime_root() == tmp_path / "portable" / "training-runtime"


def test_python_executable_is_inside_the_managed_venv(tmp_path):
    exe = paths.python_executable(tmp_path)
    assert "venv" in exe.parts
    assert exe.name.startswith("python")


# --- service caching --------------------------------------------------------

@pytest.mark.asyncio
async def test_service_caches_and_invalidates(monkeypatch):
    calls = {"n": 0}

    def fake_inspect():
        calls["n"] += 1
        return RuntimeReport(status="absent", root="/tmp", python_executable=None,
                             python_version=None, gpu=GpuInfo(), packages=[])

    monkeypatch.setattr("app.training_runtime.service.inspect_runtime", fake_inspect)
    service = TrainingRuntimeService(ttl=999)

    await service.report()
    await service.report()
    assert calls["n"] == 1

    await service.report(refresh=True)
    assert calls["n"] == 2

    # An install must invalidate, or the UI would keep showing "not installed".
    service.invalidate()
    await service.report()
    assert calls["n"] == 3


# --- no silent fallback (the defect this release fixes) ---------------------

def test_unknown_backend_raises_instead_of_becoming_simulation():
    with pytest.raises(manager.UnknownBackendError) as exc:
        manager.get_provider("totally-made-up")
    assert "totally-made-up" in str(exc.value)
    assert exc.value.available == manager.known_backends()


def test_the_default_backend_constant_is_gone():
    """A constant always equal to "simulation", one letter from the auto-detecting
    default_backend(), was a trap for the next caller."""
    assert not hasattr(manager, "DEFAULT_BACKEND")


def test_managed_provider_is_registered():
    assert "managed" in manager.known_backends()


def test_auto_order_prefers_real_backends_over_simulation():
    order = manager._AUTO_ORDER
    assert order.index("simulation") == len(order) - 1
    for real in ("unsloth", "managed"):
        assert order.index(real) < order.index("simulation")


def test_every_registered_backend_can_be_constructed():
    for name in manager.known_backends():
        provider = manager.get_provider(name)
        ok, reason = provider.is_available()
        assert isinstance(ok, bool)
        assert isinstance(reason, str) and reason
