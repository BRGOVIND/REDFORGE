"""Filesystem layout resolution for the CLI.

Works both from source (the repo) and from a packaged release, where the CLI
sits alongside ``backend/``. ``REDFORGE_HOME`` overrides the root; runtime files
(pid/log) go to a writable home directory.
"""
from __future__ import annotations

import os
from pathlib import Path

# cli/redforge/paths.py -> cli/redforge -> cli -> <root>  (source / release layout)
_INTREE = Path(__file__).resolve().parent.parent.parent


def _looks_like_root(p: Path) -> bool:
    return (p / "backend").is_dir() and (p / "cli").is_dir() and (p / "VERSION").is_file()


def root() -> Path:
    """Locate the RedForge installation.

    1. ``REDFORGE_HOME`` env var, if set.
    2. In-tree layout (running from source or a release: cli/ is next to backend/).
    3. Walk up from the current directory (covers a pip-installed CLI invoked from
       inside a checkout — the package itself lives in site-packages).
    """
    env = os.environ.get("REDFORGE_HOME")
    if env:
        return Path(env).resolve()
    if (_INTREE / "backend").is_dir():
        return _INTREE
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if _looks_like_root(candidate):
            return candidate
    return _INTREE


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
    """A writable directory for pid/log/venv/state files."""
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


# ---------------------------------------------------------------------------
# Dedicated virtual environment (created by `redforge install`)
# ---------------------------------------------------------------------------

def venv_dir() -> Path:
    """Where `redforge install` places the backend virtual environment."""
    return runtime_home() / "venv"


def venv_python(venv: Path | None = None) -> Path:
    """Path to the interpreter inside a venv (cross-platform)."""
    base = venv or venv_dir()
    if os.name == "nt":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def backend_python() -> str:
    """Interpreter used to run the backend (uvicorn, health engine, pip).

    Prefers the dedicated venv created by `redforge install`; falls back to the
    current interpreter (source checkouts / developers who installed deps
    globally). This is the single resolution point — nothing hardcodes a python.
    """
    import sys

    vp = venv_python()
    return str(vp) if vp.is_file() else sys.executable


def state_file() -> Path:
    """Records the last successful install (venv path, version, timestamp)."""
    return runtime_home() / "install.json"


def requirements_file() -> Path:
    return backend_dir() / "requirements.txt"
