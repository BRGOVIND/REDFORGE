"""TTL cache for model metadata (/api/tags and /api/show).

Model lists and capabilities change rarely, so caching them avoids hammering the
provider on every dashboard refresh, health check, and profiling call. Entries
expire after ``MODEL_CACHE_TTL`` and can be invalidated explicitly (e.g. after a
pull).
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable, Optional

from app.config import settings


class ModelCache:
    def __init__(self, ttl: float | None = None) -> None:
        self.ttl = ttl if ttl is not None else settings.MODEL_CACHE_TTL
        self._tags: Optional[tuple[float, list[str]]] = None
        self._show: dict[str, tuple[float, Optional[dict]]] = {}

    def _fresh(self, ts: float) -> bool:
        return (time.monotonic() - ts) < self.ttl

    async def get_tags(self, fetch: Callable[[], Awaitable[list[str]]]) -> list[str]:
        if self._tags and self._fresh(self._tags[0]):
            return self._tags[1]
        value = await fetch()
        self._tags = (time.monotonic(), value)
        return value

    async def get_show(
        self, model: str, fetch: Callable[[], Awaitable[Optional[dict]]]
    ) -> Optional[dict]:
        cached = self._show.get(model)
        if cached and self._fresh(cached[0]):
            return cached[1]
        value = await fetch()
        self._show[model] = (time.monotonic(), value)
        return value

    def invalidate(self, model: Optional[str] = None) -> None:
        """Drop cached data — all of it, or just one model's show entry."""
        if model is None:
            self._tags = None
            self._show.clear()
        else:
            self._show.pop(model, None)
