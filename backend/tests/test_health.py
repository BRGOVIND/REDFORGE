"""Tests for the centralized System Health Engine."""
from __future__ import annotations

from typing import AsyncIterator, Optional

import pytest
from httpx import ASGITransport, AsyncClient

from app.health import health_service
from app.health.models import HealthCheck, aggregate
from app.runtime.client import Provider
from app.runtime.responses import GenerationResult


class _FastProvider(Provider):
    """A reachable in-memory provider so health runs don't hit a real localhost
    port (which can stall to the connect timeout on some machines)."""

    name = "fasthealth"
    label = "FastHealth"
    base_url = "http://fast"

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        return GenerationResult(model, "ok", 1)

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        yield {"response": "ok", "done": True}

    async def health(self) -> bool:
        return True

    async def list_models_raw(self) -> list[dict]:
        return [{"name": "fast-model"}]

    async def show_model(self, model: str) -> Optional[dict]:
        return None


@pytest.fixture(autouse=True)
def _fast_default_provider():
    from app.config import settings
    from app.runtime import manager

    original = settings.RUNTIME_PROVIDER
    manager.register_provider("fasthealth", _FastProvider)
    settings.RUNTIME_PROVIDER = "fasthealth"
    manager.reset_runtime()
    yield
    settings.RUNTIME_PROVIDER = original
    manager.reset_runtime()
    manager._PROVIDERS.pop("fasthealth", None)

VALID_STATUS = {"healthy", "warning", "error"}
VALID_SEVERITY = {"critical", "high", "medium", "low", "info"}
CORE_IDS = {
    "os", "architecture", "python_version", "runtime_providers", "provider_health",
    "installed_models", "cpu", "ram", "disk", "gpu", "cuda", "ports", "backend_status",
    "frontend_status", "database", "permissions",
}


@pytest.mark.asyncio
async def test_run_returns_structured_report():
    report = await health_service.run()
    ids = {c.id for c in report.checks}
    assert CORE_IDS <= ids
    assert "network" not in ids  # optional, off by default
    for c in report.checks:
        assert c.status in VALID_STATUS
        assert c.severity in VALID_SEVERITY
        assert c.name and c.message
        assert isinstance(c.metadata, dict)  # never a plain string
    assert report.status in VALID_STATUS
    assert isinstance(report.ready, bool)
    assert report.summary.total == len(report.checks)
    assert report.summary.healthy + report.summary.warning + report.summary.error == report.summary.total


@pytest.mark.asyncio
async def test_python_check_healthy_and_critical():
    report = await health_service.run()
    py = next(c for c in report.checks if c.id == "python_version")
    assert py.status == "healthy"      # the suite runs on 3.11+
    assert py.severity == "critical"
    assert py.name == "Python"


@pytest.mark.asyncio
async def test_os_check_always_healthy():
    c = await health_service.get_check("os")
    assert c is not None
    assert c.id == "os" and c.status == "healthy"
    assert "system" in c.metadata


@pytest.mark.asyncio
async def test_get_check_unknown_is_none():
    assert await health_service.get_check("does-not-exist") is None


def test_aggregate_readiness_and_status():
    ok = HealthCheck(id="a", name="A", status="healthy", severity="high", message="x")
    warn = HealthCheck(id="b", name="B", status="warning", severity="high", message="x")
    err_low = HealthCheck(id="c", name="C", status="error", severity="low", message="x")
    err_high = HealthCheck(id="d", name="D", status="error", severity="high", message="x")

    status, ready, summary = aggregate([ok, warn])
    assert status == "warning" and ready is True and summary.total == 2

    status, ready, _ = aggregate([ok, err_low])
    assert status == "error" and ready is True      # low-severity error doesn't block

    status, ready, _ = aggregate([ok, err_high])
    assert status == "error" and ready is False     # high-severity error blocks


@pytest.mark.asyncio
async def test_network_check_opt_in():
    report = await health_service.run(include_network=True)
    ids = {c.id for c in report.checks}
    assert "network" in ids


@pytest.mark.asyncio
async def test_health_api_endpoints():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        full = await client.get("/api/health")
        one = await client.get("/api/health/python_version")
        missing = await client.get("/api/health/nope")

    assert full.status_code == 200
    body = full.json()
    for key in ("status", "ready", "generated_at", "summary", "checks"):
        assert key in body
    assert body["summary"]["total"] == len(body["checks"])

    assert one.status_code == 200
    assert one.json()["id"] == "python_version"

    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_system_checks_embeds_health_report():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        default = await client.get("/api/system/checks")
        embedded = await client.get("/api/system/checks", params={"include_health": True})
    # Cheap poll by default: no engine run embedded.
    assert default.status_code == 200 and default.json()["health"] is None
    # Opt-in embeds the full engine report.
    body = embedded.json()
    assert "checks" in body and "ready" in body
    assert body["health"] is not None
    assert "checks" in body["health"] and "summary" in body["health"]
