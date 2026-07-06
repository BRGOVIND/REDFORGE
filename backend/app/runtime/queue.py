"""Lightweight per-model execution queue.

Local models can't serve many generations at once, so the runtime serializes
work per model (default concurrency 1). Concurrency is configurable and the
queue is per-model, so multiple local models can run in parallel while each is
protected from being hammered.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from app.config import settings
from app.runtime.metrics import metrics


class GenerationQueue:
    def __init__(self, concurrency: int | None = None) -> None:
        self.concurrency = concurrency or settings.RUNTIME_CONCURRENCY
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._waiting = 0

    def _sem(self, model: str) -> asyncio.Semaphore:
        sem = self._sems.get(model)
        if sem is None:
            sem = asyncio.Semaphore(self.concurrency)
            self._sems[model] = sem
        return sem

    @asynccontextmanager
    async def slot(self, model: str):
        """Acquire a generation slot for ``model`` (FIFO per model)."""
        sem = self._sem(model)
        self._waiting += 1
        metrics.set_queue_length(self._waiting)
        try:
            await sem.acquire()
        finally:
            self._waiting = max(0, self._waiting - 1)
            metrics.set_queue_length(self._waiting)
        try:
            yield
        finally:
            sem.release()
