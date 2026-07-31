"""Environment / dependency detection.

The probe is injected, so these assert the *logic* (severity, remedies, readiness,
caching) rather than whatever happens to be installed on the machine running the
suite — the same test result on a bare CI runner and a loaded dev box.
"""
from __future__ import annotations

import pytest

from app.environment.detector import ProbeResult, detect_sync
from app.environment.domain import Dependency, EnvironmentReport, Remedy
from app.environment.service import EnvironmentService


def probe_none(_executables, _version_args):
    return ProbeResult(found=False)


def probe_all(_executables, _version_args):
    return ProbeResult(found=True, version="1.2.3", path="/usr/bin/tool")


def probe_only(keys_present: set[str]):
    """Present iff the first executable name is in `keys_present`."""
    def probe(executables, _version_args):
        if executables and executables[0] in keys_present:
            return ProbeResult(found=True, version="9.9", path=f"/usr/bin/{executables[0]}")
        return ProbeResult(found=False)
    return probe


# --- domain -----------------------------------------------------------------

def test_blocking_only_when_required_and_missing():
    required_missing = Dependency("k", "K", "required", "p", found=False)
    required_found = Dependency("k", "K", "required", "p", found=True)
    recommended_missing = Dependency("k", "K", "recommended", "p", found=False)

    assert required_missing.blocking is True
    assert required_found.blocking is False
    # A missing *recommended* tool must never block the wizard.
    assert recommended_missing.blocking is False


def test_report_ready_ignores_non_required():
    report = EnvironmentReport(
        platform="Linux",
        dependencies=[
            Dependency("a", "A", "recommended", "p", found=False),
            Dependency("b", "B", "optional", "p", found=False),
        ],
    )
    assert report.ready is True
    counts = report.to_dict()["counts"]
    assert counts["missing_recommended"] == 1
    assert counts["missing_optional"] == 1


def test_report_not_ready_when_required_missing():
    report = EnvironmentReport(
        platform="Linux",
        dependencies=[Dependency("a", "A", "required", "p", found=False)],
    )
    assert report.ready is False


# --- detection --------------------------------------------------------------

def test_nothing_installed_is_still_ready():
    """The desktop build bundles its backend — a bare machine is not 'broken'."""
    report = detect_sync(probe=probe_none, system="Linux")
    assert report.ready is True
    assert report.to_dict()["counts"]["missing_required"] == 0


def test_every_dependency_is_reported_with_a_purpose():
    report = detect_sync(probe=probe_none, system="Linux")
    keys = {d.key for d in report.dependencies}
    # Exactly the set the brief asks RedForge to detect.
    assert keys == {"python", "cuda", "git", "ollama", "lmstudio", "llamacpp", "node"}
    for dep in report.dependencies:
        assert dep.purpose, f"{dep.key} must explain why RedForge wants it"
        assert dep.severity in ("required", "recommended", "optional")


def test_missing_dependencies_carry_an_actionable_remedy():
    for system in ("Windows", "Darwin", "Linux"):
        report = detect_sync(probe=probe_none, system=system)
        for dep in report.dependencies:
            assert dep.remedy.url, f"{dep.key} on {system} has no install URL"


def test_windows_offers_winget_one_liners():
    report = detect_sync(probe=probe_none, system="Windows")
    by_key = {d.key: d for d in report.dependencies}
    assert by_key["ollama"].remedy.manager == "winget"
    assert "winget install" in by_key["ollama"].remedy.command


def test_detected_tool_reports_version_and_path():
    report = detect_sync(probe=probe_all, system="Linux")
    ollama = next(d for d in report.dependencies if d.key == "ollama")
    assert ollama.found is True
    assert ollama.version == "1.2.3"
    assert ollama.path == "/usr/bin/tool"
    assert "1.2.3" in ollama.detail


def test_partial_environment_counts_correctly():
    report = detect_sync(probe=probe_only({"ollama", "git"}), system="Linux")
    found = {d.key for d in report.dependencies if d.found}
    # python falls back to the running interpreter, so it is always present here.
    assert {"ollama", "git"} <= found
    assert "cuda" not in found
    assert report.ready is True


def test_python_falls_back_to_the_running_interpreter():
    """Even with nothing on PATH, the interpreter running the backend counts."""
    report = detect_sync(probe=probe_none, system="Linux")
    python = next(d for d in report.dependencies if d.key == "python")
    assert python.found is True
    assert python.version


def test_ollama_is_the_recommended_runtime():
    report = detect_sync(probe=probe_none, system="Linux")
    ollama = next(d for d in report.dependencies if d.key == "ollama")
    assert ollama.severity == "recommended"


# --- service ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_caches_then_refreshes(monkeypatch):
    calls = {"n": 0}

    async def fake_detect(_probe=None):
        calls["n"] += 1
        return EnvironmentReport(platform="Linux", dependencies=[])

    monkeypatch.setattr("app.environment.service.detect", fake_detect)

    service = EnvironmentService(ttl=999)
    await service.report()
    await service.report()
    assert calls["n"] == 1, "second call within the TTL must be served from cache"

    await service.report(refresh=True)
    assert calls["n"] == 2, "refresh=True must bypass the cache"

    service.invalidate()
    await service.report()
    assert calls["n"] == 3


def test_remedy_serializes_empty_fields():
    assert Remedy().to_dict() == {"url": "", "command": "", "manager": ""}
