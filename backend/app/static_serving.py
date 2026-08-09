"""Serve the built frontend from the backend — the production single-process model.

In production there is exactly ONE process: the FastAPI backend serves the API
*and* the compiled React app (and the docs). No Node.js, no Vite server. In
development the frontend still runs under Vite with hot reload and proxies
``/api`` here; this module only activates when a built frontend is found.

Static directory resolution (first hit wins):
  1. ``REDFORGE_STATIC_DIR`` env var
  2. ``backend/app/static``            (bundled into a packaged release)
  3. ``<repo>/frontend/dist``          (running from source after `npm run build`)

Caching — why this matters more than it looks
---------------------------------------------
The desktop app always loads the same origin, ``http://127.0.0.1:8760``, and
Electron's HTTP cache lives in the user's profile, so it SURVIVES app upgrades.
An earlier version of this module sent ``Last-Modified``/``ETag`` but no
``Cache-Control``. Browsers then apply *heuristic freshness* (RFC 9111 §4.2.2):
roughly 10% of the document's age, with no revalidation. So a freshly installed
build would boot the PREVIOUS version's ``index.html`` and entry bundle out of
disk cache, and every code-split chunk that old shell asked for — named by a
content hash that no longer exists — would 404. The app opened fine (its shell
was cached) and then failed the moment you navigated to a route whose chunk had
never been cached. That is the bug this policy exists to prevent:

  * ``/assets/*`` are content-hashed by Vite, so the filename IS the version.
    They are immutable and cached for a year.
  * ``index.html`` and every unhashed file must be revalidated on every load.
    ``no-cache`` still allows a cheap 304 via ETag; what it forbids is the blind
    reuse that pinned users to a dead build.
"""
from __future__ import annotations

import os
import posixpath
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.logging_config import get_logger

logger = get_logger("static")

_HERE = Path(__file__).resolve().parent  # backend/app

# Hashed build output: the filename changes whenever the content does.
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
# Everything else: always ask, even if the answer is usually "304 Not Modified".
REVALIDATE_CACHE_CONTROL = "no-cache, must-revalidate"

# A request for one of these is a request for a BUILD ARTEFACT, never for a
# client-side route. Answering it with index.html would turn a missing chunk into
# a confusing MIME-type error somewhere deep in the app instead of an honest 404.
ASSET_SUFFIXES = frozenset({
    ".js", ".mjs", ".cjs", ".css", ".map", ".json", ".webmanifest", ".wasm",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".mp3", ".wav", ".txt", ".xml",
})


class _ImmutableStaticFiles(StaticFiles):
    """StaticFiles for content-hashed output — safe to cache forever."""

    def file_response(self, *args, **kwargs) -> FileResponse:  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        return response


def looks_like_asset(path: str) -> bool:
    """True when the path names a build artefact rather than a client route."""
    return posixpath.splitext(path)[1].lower() in ASSET_SUFFIXES


def resolve_static_dir() -> Optional[Path]:
    candidates: list[Path] = []
    env = os.environ.get("REDFORGE_STATIC_DIR")
    if env:
        candidates.append(Path(env))
    candidates.append(_HERE / "static")                      # bundled release
    candidates.append(_HERE.parent.parent / "frontend" / "dist")  # from source
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    return None


def mount_frontend(app: FastAPI) -> bool:
    """Mount the SPA if a build exists. Returns True when mounted.

    Must be called AFTER all API routers are registered so ``/api/*`` and the
    OpenAPI routes take precedence over the catch-all.
    """
    static_dir = resolve_static_dir()

    # Optionally serve the docs folder as static files (harmless if absent).
    docs_dir = _HERE.parent.parent / "docs"
    if docs_dir.is_dir():
        app.mount("/documentation", StaticFiles(directory=str(docs_dir)), name="documentation")

    if static_dir is None:
        logger.info("no frontend build found; serving API only (dev mode uses Vite)")

        @app.get("/", include_in_schema=False)
        async def _api_root() -> dict:
            return {"name": "RedForge API", "version": app.version, "status": "online"}

        return False

    logger.info("serving frontend from %s", static_dir)
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", _ImmutableStaticFiles(directory=str(assets)), name="assets")
    else:
        # No assets directory means a broken or half-staged build. Say so with a
        # 404 rather than letting the catch-all answer every chunk request with
        # index.html, which surfaces as an inscrutable MIME-type error.
        logger.error("frontend build at %s has no assets/ directory", static_dir)

        @app.get("/assets/{_asset_path:path}", include_in_schema=False)
        async def _missing_assets(_asset_path: str) -> FileResponse:
            raise HTTPException(status_code=404, detail="frontend assets are not available")

    index_file = static_dir / "index.html"

    # SPA catch-all: real files are served; client-side routes (/setup, /live/:id,
    # …) return index.html so refresh works. Never shadows the API — unknown /api
    # paths get a proper JSON 404 — and never disguises a missing build artefact
    # as HTML.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path in ("openapi.json", "docs", "redoc", "healthz"):
            raise HTTPException(status_code=404, detail="Not found")
        # Resolve BOTH sides so ``..`` / symlinks can never escape the static root,
        # regardless of how ``static_dir`` was configured (e.g. a relative env var).
        root = static_dir.resolve()
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            # Unhashed (favicon, manifest, …) — must revalidate, same reasoning
            # as index.html. Hashed output is served by the /assets mount above.
            return FileResponse(candidate, headers={"Cache-Control": REVALIDATE_CACHE_CONTROL})
        if looks_like_asset(full_path):
            # A build artefact that does not exist. Returning the SPA here is how a
            # stale cached shell used to fail with "Failed to fetch dynamically
            # imported module" instead of something diagnosable.
            raise HTTPException(status_code=404, detail=f"asset not found: /{full_path}")
        return FileResponse(index_file, headers={"Cache-Control": REVALIDATE_CACHE_CONTROL})

    return True
