"""One cancellation primitive for the whole platform.

Evaluation, benchmark, judge, mutation, and the agent all use ``CancellationToken``
— there is no per-feature cancellation logic. A token can be awaited (so a
generation races it) or polled. The ``CancelRegistry`` lets an API endpoint
cancel an in-flight request by id.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.runtime.errors import CancelledGeneration


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledGeneration("generation was cancelled")

    async def wait(self) -> None:
        await self._event.wait()


class CancelRegistry:
    """Maps request ids to their cancellation tokens."""

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}

    def register(self, request_id: str, token: Optional[CancellationToken] = None) -> CancellationToken:
        token = token or CancellationToken()
        self._tokens[request_id] = token
        return token

    def cancel(self, request_id: str) -> bool:
        token = self._tokens.get(request_id)
        if token is None:
            return False
        token.cancel()
        return True

    def discard(self, request_id: str) -> None:
        self._tokens.pop(request_id, None)

    @property
    def active_ids(self) -> list[str]:
        return list(self._tokens)
