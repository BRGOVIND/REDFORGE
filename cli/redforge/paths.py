"""Filesystem layout resolution for the CLI.

Works both from source (the repo) and from a packaged release, where the CLI
sits alongside ``backend/``. ``REDFORGE_HOME`` overrides the root; runtime files
(pid/log) go to a writable home directory.
"""
from __future__ import annotations

import os
from pathlib import Path

# cli/redforge/paths.py -> cli/redforge -> cli -> <root>
_ROOT = Path(__file__).resolve().parent.parent.parent


def root() -> Path:
    env = os.environ.get("REDFORGE_HOME")
    return Path(env).resolve() if env else _ROOT


def backend_dir() -> Path:
    return root() / "backend"


def frontend_dir() -> Path:
    return root() / "frontend"


def datasets_dir() -> Path:
    return root() / "datasets"


def static_dir() -> Path | None:
    """Where the built frontend lives, if present."""
    for c in (backend_dir() / "app" / "static", frontend_dir() / "dist"):
        if (c / "index.html").is_file():
            return c
    return None


def db_path() -> Path:
    return backend_dir() / "redforge.db"


def runtime_home() -> Path:
    """A writable directory for pid/log files."""
    base = root()
    try:
        (base / ".redforge").mkdir(exist_ok=True)
        return base / ".redforge"
    except OSError:
        home = Path.home() / ".redforge"
        home.mkdir(exist_ok=True)
        return home


def pid_file() -> Path:
    return runtime_home() / "redforge.pid"


def log_file() -> Path:
    return runtime_home() / "redforge.log"
