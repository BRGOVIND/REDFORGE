"""Model profiling with per-session caching.

A model is profiled once per session. Repeated requests for the same
(session, model) return the cached :class:`ModelProfile` instead of re-hitting
Ollama and the database — "no duplicate profiling".
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.profiler.capability_detector import fetch_model_metadata
from app.profiler.profile_builder import ModelProfile, build_model_profile

# (model_name) -> raw Ollama /api/show dict (or None when offline/not installed)
MetadataFetcher = Callable[[str], Awaitable[Optional[dict]]]


class ModelProfiler:
    def __init__(self, metadata_fetcher: Optional[MetadataFetcher] = None) -> None:
        # Injectable so tests need no live Ollama. Defaults to the real client.
        self._fetch = metadata_fetcher or fetch_model_metadata
        # Keyed by (session_id, model_name); session_id may be None for ad-hoc.
        self._cache: dict[tuple[Optional[str], str], ModelProfile] = {}

    async def get_profile(
        self,
        model_name: str,
        db: AsyncSession,
        *,
        session_id: Optional[str] = None,
        refresh: bool = False,
    ) -> ModelProfile:
        key = (session_id, model_name)
        if not refresh and key in self._cache:
            return self._cache[key]

        ollama_show = await self._fetch(model_name)
        profile = await build_model_profile(
            model_name,
            db,
            ollama_show=ollama_show,
            installed_locally=bool(ollama_show),
        )
        self._cache[key] = profile
        return profile

    def cached(self, model_name: str, session_id: Optional[str] = None) -> Optional[ModelProfile]:
        return self._cache.get((session_id, model_name))

    def clear(self) -> None:
        self._cache.clear()
