"""Version resolution for the CLI — standard library only.

The repo-root ``VERSION`` file is the single source of truth. This module never
carries a hardcoded version string; every other CLI module imports from here.

Resolution order:
  1. ``REDFORGE_HOME/VERSION`` when the env var is set (packaged installs).
  2. The nearest ``VERSION`` walking up from this file (source tree *and*
     release layout, where ``cli/`` sits next to ``backend/``).
  3. Installed distribution metadata (``pip install redforge``), where no
     ``VERSION`` file ships alongside the package.
  4. ``0.0.0`` — an unresolvable build, never a stale number.
"""
from __future__ import annotations

import os
from pathlib import Path

UNKNOWN = "0.0.0"


def _read(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _from_tree() -> str | None:
    home = os.environ.get("REDFORGE_HOME")
    if home:
        found = _read(Path(home) / "VERSION")
        if found:
            return found
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        found = _read(candidate / "VERSION")
        if found:
            return found
    return None


def _from_metadata() -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    for dist in ("redforge", "redforge-cli"):
        try:
            return version(dist)
        except PackageNotFoundError:
            continue
        except Exception:  # noqa: BLE001 - metadata must never break the CLI
            return None
    return None


def read_version() -> str:
    return _from_tree() or _from_metadata() or UNKNOWN


__version__ = read_version()
