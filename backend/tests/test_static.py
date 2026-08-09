"""Tests for production single-process serving (backend serves the built SPA)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.static_serving import (
    IMMUTABLE_CACHE_CONTROL,
    mount_frontend,
    resolve_static_dir,
)


# A minimal but realistic build: an index.html naming a hashed entry bundle, and
# that bundle naming a lazily imported route chunk.
_ENTRY = "index-AAAAAAAA.js"
_CHUNK = "NewEvaluationPage-BBBBBBBB.js"


@pytest.fixture()
def built_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A FastAPI app serving a synthetic frontend build from a temp directory."""
    root = tmp_path / "static"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(
        f'<!doctype html><script type="module" src="/assets/{_ENTRY}"></script>',
        encoding="utf-8",
    )
    (root / "assets" / _ENTRY).write_text(f'import("./{_CHUNK}");', encoding="utf-8")
    (root / "assets" / _CHUNK).write_text("export default 1;", encoding="utf-8")
    (root / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")

    monkeypatch.setenv("REDFORGE_STATIC_DIR", str(root))
    fresh = FastAPI()
    assert mount_frontend(fresh) is True
    return fresh


def _client(target: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=target), base_url="http://test")


@pytest.mark.asyncio
async def test_index_is_never_cached_without_revalidation(built_app):
    """The regression that shipped in 2.0.3.

    With no Cache-Control, browsers apply heuristic freshness (10% of the
    document's age) and reuse the shell across an upgrade. The new backend is
    then asked for the previous build's code-split chunks, which no longer
    exist, and every lazy route dies with 'Failed to fetch dynamically imported
    module'. The shell must always be revalidated.
    """
    async with _client(built_app) as c:
        resp = await c.get("/")
    assert resp.status_code == 200
    cache_control = resp.headers.get("cache-control", "")
    assert "no-cache" in cache_control, f"index.html must revalidate, got {cache_control!r}"


@pytest.mark.asyncio
async def test_client_route_shell_is_also_revalidated(built_app):
    async with _client(built_app) as c:
        resp = await c.get("/training")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "no-cache" in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_unhashed_root_file_is_revalidated(built_app):
    async with _client(built_app) as c:
        resp = await c.get("/favicon.ico")
    assert resp.status_code == 200
    assert "no-cache" in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_hashed_chunks_are_immutable_and_javascript(built_app):
    """Content-hashed output is safe to cache forever — the name is the version."""
    async with _client(built_app) as c:
        resp = await c.get(f"/assets/{_CHUNK}")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == IMMUTABLE_CACHE_CONTROL
    assert "javascript" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_missing_chunk_is_404_not_the_spa(built_app):
    """A missing asset must be diagnosable, never disguised as HTML."""
    async with _client(built_app) as c:
        resp = await c.get("/assets/NewEvaluationPage-Ce21fyz1.js")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_missing_asset_outside_assets_dir_is_404_not_the_spa(built_app):
    """The catch-all used to answer /anything.js with index.html."""
    async with _client(built_app) as c:
        for path in ("/nonexistent.js", "/styles/gone.css", "/img/missing.png"):
            resp = await c.get(path)
            assert resp.status_code == 404, f"{path} returned {resp.status_code}"
            assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_client_routes_with_dots_still_reach_the_spa(built_app):
    """Only known asset extensions 404 — project names may contain dots."""
    async with _client(built_app) as c:
        resp = await c.get("/projects/my.project.v2")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_missing_assets_directory_does_not_serve_html_for_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A half-staged build must fail loudly rather than return HTML for every chunk."""
    root = tmp_path / "broken"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setenv("REDFORGE_STATIC_DIR", str(root))
    fresh = FastAPI()
    assert mount_frontend(fresh) is True
    async with _client(fresh) as c:
        resp = await c.get(f"/assets/{_CHUNK}")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


def _write_build(root: Path, entry: str, chunk: str) -> None:
    """Lay down one complete build: index.html -> entry -> one lazy route chunk."""
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for stale in assets.iterdir():
        stale.unlink()
    (root / "index.html").write_text(
        f'<!doctype html><script type="module" src="/assets/{entry}"></script>',
        encoding="utf-8",
    )
    (assets / entry).write_text(f'import("./{chunk}");', encoding="utf-8")
    (assets / chunk).write_text("export default 1;", encoding="utf-8")


@pytest.mark.asyncio
async def test_upgrade_from_one_build_to_another_serves_only_the_new_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The 2.0.3 -> 2.0.4 scenario, end to end at the HTTP layer.

    Version A ships index.html referencing chunk A. The user upgrades in place to
    version B, whose index.html references chunk B. What broke 2.0.3 was the
    browser reusing A's shell against B's backend, so it kept asking for chunk A
    — which no longer exists.

    Three properties together make that impossible:
      * the shell is served `no-cache`, so it is revalidated on every load;
      * its ETag changes with the content, so revalidation yields B, not a 304;
      * A's chunk is gone and says so with a 404 instead of returning HTML.
    """
    root = tmp_path / "static"
    _write_build(root, "index-AAAAAAAA.js", "NewEvaluationPage-AAAAAAAA.js")
    monkeypatch.setenv("REDFORGE_STATIC_DIR", str(root))

    version_a = FastAPI()
    assert mount_frontend(version_a) is True
    async with _client(version_a) as c:
        shell_a = await c.get("/")
        chunk_a = await c.get("/assets/NewEvaluationPage-AAAAAAAA.js")
    assert shell_a.status_code == 200
    assert "index-AAAAAAAA.js" in shell_a.text
    assert chunk_a.status_code == 200
    etag_a = shell_a.headers.get("etag")
    assert etag_a, "the shell must carry an ETag so revalidation is cheap"
    assert "no-cache" in shell_a.headers.get("cache-control", "")

    # --- the upgrade: same install path, entirely new build ------------------
    _write_build(root, "index-BBBBBBBB.js", "NewEvaluationPage-BBBBBBBB.js")

    version_b = FastAPI()
    assert mount_frontend(version_b) is True
    async with _client(version_b) as c:
        shell_b = await c.get("/")
        revalidated = await c.get("/", headers={"If-None-Match": etag_a})
        old_chunk = await c.get("/assets/NewEvaluationPage-AAAAAAAA.js")
        new_chunk = await c.get("/assets/NewEvaluationPage-BBBBBBBB.js")

    assert "index-BBBBBBBB.js" in shell_b.text, "the upgraded backend must serve the new shell"
    assert "index-AAAAAAAA.js" not in shell_b.text
    assert "no-cache" in shell_b.headers.get("cache-control", "")
    # A browser holding version A's shell revalidates and is given version B,
    # rather than being told its stale copy is still good.
    assert revalidated.status_code == 200, "a stale ETag must not be answered with 304"
    assert "index-BBBBBBBB.js" in revalidated.text

    assert old_chunk.status_code == 404, "the previous build's chunk must be gone, and say so"
    assert "text/html" not in old_chunk.headers.get("content-type", "")
    assert new_chunk.status_code == 200
    assert "javascript" in new_chunk.headers["content-type"]
    assert new_chunk.headers.get("cache-control") == IMMUTABLE_CACHE_CONTROL


def test_bundled_build_has_no_dangling_chunk_references():
    """Whatever build is present must be internally consistent.

    Runs against backend/app/static or frontend/dist — the same check the release
    pipeline applies to every copy it makes.
    """
    import sys

    static_dir = resolve_static_dir()
    if static_dir is None:
        pytest.skip("no frontend build present (dev without `npm run build`)")
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    from verify_frontend_assets import check as check_graph

    problems, _ = check_graph(static_dir)
    assert problems == [], "\n".join(problems)


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
