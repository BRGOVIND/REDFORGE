"""Environment service — the seam the API depends on.

Detection is cheap but not free (it shells out), and the answer changes rarely, so
results are cached for a short TTL. The wizard polls this while the user installs
Ollama in another window, hence a modest TTL and an explicit refresh.
"""
from __future__ import annotations

import time

from .detector import detect
from .domain import EnvironmentReport

CACHE_TTL_S = 15.0


class EnvironmentService:
    def __init__(self, ttl: float = CACHE_TTL_S) -> None:
        self._ttl = ttl
        self._cached: EnvironmentReport | None = None
        self._cached_at = 0.0

    async def report(self, refresh: bool = False) -> EnvironmentReport:
        now = time.monotonic()
        fresh = self._cached is not None and (now - self._cached_at) < self._ttl
        if fresh and not refresh:
            return self._cached  # type: ignore[return-value]
        report = await detect()
        self._cached = report
        self._cached_at = now
        return report

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0


environment_service = EnvironmentService()
