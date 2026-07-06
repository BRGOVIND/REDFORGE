"""Serve the built frontend from the backend — the production single-process model.

In production there is exactly ONE process: the FastAPI backend serves the API
*and* the compiled React app (and the docs). No Node.js, no Vite server. In
development the frontend still runs under Vite with hot reload and proxies
``/api`` here; this module only activates when a built frontend is found.

Static directory resolution (first hit wins):
  1. ``REDFORGE_STATIC_DIR`` env var
  2. ``backend/app/static``            (bundled into a packaged release)
  3. ``<repo>/frontend/dist``          (running from source after `npm run build`)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.logging_config import get_logger

logger = get_logger("static")

_HERE = Path(__file__).resolve().parent  # backend/app


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
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    index_file = static_dir / "index.html"

    # SPA catch-all: real files are served; everything else returns index.html so
    # client-side routes (/setup, /live/:id, …) work on refresh. Never shadows the
    # API — unknown /api paths get a proper JSON 404.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path in ("openapi.json", "docs", "redoc", "healthz"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = static_dir / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(static_dir):
            return FileResponse(candidate)
        return FileResponse(index_file)

    return True
