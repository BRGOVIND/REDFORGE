"""Regression coverage for the standardized error envelope and config."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings


def _envelope_ok(body: dict) -> bool:
    return (
        body.get("success") is False
        and isinstance(body.get("error"), dict)
        and "code" in body["error"]
        and "message" in body["error"]
        and "details" in body["error"]
    )


@pytest.mark.asyncio
async def test_404_uses_structured_envelope():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/sessions/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert _envelope_ok(body)
    assert body["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_422_validation_envelope():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/evaluate", json={})  # missing required 'profile'
    assert resp.status_code == 422
    body = resp.json()
    assert _envelope_ok(body)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]  # field errors present


@pytest.mark.asyncio
async def test_unhandled_exception_is_safe_and_logged():
    """The 500 handler returns a generic message — never the raw exception."""
    from app.errors import _unhandled_exception_handler

    class _Req:
        method = "GET"

        class url:
            path = "/boom"

    resp = await _unhandled_exception_handler(_Req(), ValueError("secret internal detail"))
    assert resp.status_code == 500
    import json

    body = json.loads(resp.body)
    assert _envelope_ok(body)
    assert "secret internal detail" not in json.dumps(body)  # no leak
    assert body["error"]["code"] == "internal_error"


def test_config_defaults_are_stable():
    # These defaults are relied upon across the codebase; lock them.
    assert settings.OLLAMA_BASE_URL.endswith(":11434")
    assert settings.OLLAMA_TIMEOUT == 60.0
    assert settings.HEARTBEAT_INTERVAL == 4.0
    assert settings.DEFAULT_LATENCY_MS == 4000.0
    assert settings.ROBUST_SCORE_THRESHOLD == 80.0


def test_config_env_override(monkeypatch):
    import importlib
    import app.config as config

    monkeypatch.setenv("REDFORGE_HEARTBEAT_INTERVAL", "1.5")
    monkeypatch.setenv("REDFORGE_OLLAMA_URL", "http://example:1234")
    reloaded = importlib.reload(config)
    assert reloaded.settings.HEARTBEAT_INTERVAL == 1.5
    assert reloaded.settings.OLLAMA_BASE_URL == "http://example:1234"
    # Restore module state for other tests.
    monkeypatch.undo()
    importlib.reload(config)
