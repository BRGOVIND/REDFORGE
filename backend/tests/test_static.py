"""Tests for production single-process serving (backend serves the built SPA)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.static_serving import resolve_static_dir


@pytest.mark.asyncio
async def test_healthz_always_available():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"


@pytest.mark.asyncio
async def test_unknown_api_path_is_json_404_not_spa():
    """The SPA catch-all must never shadow the API — unknown /api paths 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/definitely-not-a-real-endpoint")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_spa_serves_index_for_client_routes():
    """When a build exists, client-side routes return index.html so refresh works."""
    if resolve_static_dir() is None:
        pytest.skip("no frontend build present (dev without `npm run build`)")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        root = await c.get("/")
        setup = await c.get("/setup")  # a client-side route, not a backend route
    assert root.status_code == 200
    assert "text/html" in root.headers.get("content-type", "")
    assert setup.status_code == 200
    assert "text/html" in setup.headers.get("content-type", "")
