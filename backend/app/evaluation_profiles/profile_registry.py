"""In-process cache and lookup for evaluation profiles.

Profiles rarely change during a run, so they are loaded once and cached. Call
``reload()`` to pick up edits (e.g. after adding a file to the override
directory) without restarting the backend.
"""
from __future__ import annotations

from threading import Lock
from typing import Optional

from app.evaluation_profiles.profile import EvaluationProfile
from app.evaluation_profiles.profile_loader import load_profiles

_cache: Optional[dict[str, EvaluationProfile]] = None
_lock = Lock()


def _ensure_loaded() -> dict[str, EvaluationProfile]:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = load_profiles()
    return _cache


def reload() -> dict[str, EvaluationProfile]:
    """Force a fresh load from disk and return the new cache."""
    global _cache
    with _lock:
        _cache = load_profiles()
    return _cache


def list_profiles() -> list[EvaluationProfile]:
    """All profiles, ordered by display name for stable presentation."""
    return sorted(_ensure_loaded().values(), key=lambda p: p.display_name)


def get_profile(name: str) -> Optional[EvaluationProfile]:
    return _ensure_loaded().get(name)


def has_profile(name: str) -> bool:
    return name in _ensure_loaded()
