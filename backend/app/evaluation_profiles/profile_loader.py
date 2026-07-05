"""Loads evaluation profiles from JSON on disk.

Built-in profiles ship as JSON in ``data/``. Operators can add or override
profiles by pointing the ``REDFORGE_PROFILES_DIR`` environment variable at a
directory of additional ``*.json`` files (a file whose ``name`` matches a
built-in overrides it). Everything is validated through the Pydantic schema, so
a malformed profile fails loudly at load time rather than mid-evaluation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from app.evaluation_profiles.profile import EvaluationProfile

# Directory of built-in profile JSON, resolved relative to this file so it works
# regardless of the current working directory or platform.
BUILTIN_DIR = Path(__file__).resolve().parent / "data"

ENV_OVERRIDE_DIR = "REDFORGE_PROFILES_DIR"


class ProfileLoadError(ValueError):
    """Raised when a profile file is missing, unreadable, or invalid."""


def _load_file(path: Path) -> EvaluationProfile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileLoadError(f"{path.name}: invalid JSON ({exc})") from exc
    try:
        return EvaluationProfile(**raw)
    except Exception as exc:  # pydantic ValidationError or ValueError
        raise ProfileLoadError(f"{path.name}: {exc}") from exc


def _override_dir() -> Path | None:
    value = os.environ.get(ENV_OVERRIDE_DIR)
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_dir() else None


def load_profiles() -> dict[str, EvaluationProfile]:
    """Return every discoverable profile keyed by ``name``.

    Built-ins load first; override-directory files with a matching ``name``
    replace them. The profile's ``name`` field (not the filename) is the key.
    """
    profiles: dict[str, EvaluationProfile] = {}

    search_dirs: list[Path] = [BUILTIN_DIR]
    override = _override_dir()
    if override is not None:
        search_dirs.append(override)

    for directory in search_dirs:
        for path in sorted(directory.glob("*.json")):
            profile = _load_file(path)
            profiles[profile.name] = profile

    if not profiles:
        raise ProfileLoadError(
            f"no evaluation profiles found in {BUILTIN_DIR}"
        )
    return profiles
