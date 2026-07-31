"""Training-runtime service — the seam the API and providers depend on.

Inspection spawns a subprocess (importing torch is slow), so results are cached
for a short TTL with an explicit refresh. The Training Lab polls this while an
install runs, hence a modest TTL.
"""
from __future__ import annotations

import asyncio
import time

from .detector import inspect_runtime
from .domain import RuntimeReport

CACHE_TTL_S = 20.0


class TrainingRuntimeService:
    def __init__(self, ttl: float = CACHE_TTL_S) -> None:
        self._ttl = ttl
        self._cached: RuntimeReport | None = None
        self._cached_at = 0.0

    def report_sync(self, refresh: bool = False) -> RuntimeReport:
        """Blocking. Used by providers, which are already off the event loop."""
        now = time.monotonic()
        if self._cached is not None and not refresh and (now - self._cached_at) < self._ttl:
            return self._cached
        report = inspect_runtime()
        self._cached = report
        self._cached_at = now
        return report

    async def report(self, refresh: bool = False) -> RuntimeReport:
        now = time.monotonic()
        if self._cached is not None and not refresh and (now - self._cached_at) < self._ttl:
            return self._cached
        report = await asyncio.to_thread(inspect_runtime)
        self._cached = report
        self._cached_at = now
        return report

    def invalidate(self) -> None:
        """Called after an install/uninstall so the next read is authoritative."""
        self._cached = None
        self._cached_at = 0.0


runtime_service = TrainingRuntimeService()
