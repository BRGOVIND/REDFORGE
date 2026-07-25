"""Frozen backend entry point for the desktop app (bundled by PyInstaller).

Runs the SAME single-process backend the CLI runs — FastAPI serving the API + the
bundled frontend — so the desktop shell just supervises this binary. Host/port come
from the environment the Electron supervisor sets. No Uvicorn CLI, no reload.

Note: the heavy ML stack (torch/unsloth) is intentionally NOT bundled — it is lazily
imported and only needed for real GPU training (experimental). The desktop app runs
the simulation-first workflow out of the box and degrades honestly if the ML stack is
absent, keeping the installer small.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    host = os.environ.get("REDFORGE_HOST", "127.0.0.1")
    port = int(os.environ.get("REDFORGE_PORT", "8760"))
    # When frozen, the bundled static frontend sits next to this binary.
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        static = os.path.join(base, "app", "static")
        if os.path.isdir(static):
            os.environ.setdefault("REDFORGE_STATIC_DIR", static)

    import uvicorn  # imported here so PyInstaller picks it up
    from app.main import app  # noqa: F401  (ensures the app graph is bundled)

    uvicorn.run("app.main:app", host=host, port=port, log_level="info", workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
