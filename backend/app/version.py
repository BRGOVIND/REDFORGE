"""Version resolution for the backend.

The repo-root ``VERSION`` file is the single source of truth. In a packaged
release ``backend/`` sits directly beneath the staging root, so walking up from
this module finds the same file. No version literal lives in the backend.
"""
from __future__ import annotations

import os
from pathlib import Path

UNKNOWN = "0.0.0"


def read_version() -> str:
    # The desktop shell knows its own version authoritatively (electron-builder
    # bakes it into the app bundle) and passes it down. This also covers frozen
    # builds, where the upward search below leaves the repo entirely.
    injected = os.environ.get("REDFORGE_VERSION", "").strip()
    if injected:
        return injected

    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        try:
            text = (candidate / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return UNKNOWN


__version__ = read_version()
