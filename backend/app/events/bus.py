"""Internal platform event bus (RedForge V3, Epic 2).

A tiny, in-process, dependency-free publish/subscribe bus — the Constitution's
Event Bus (§4.2 Infrastructure, §8.6). No message broker, no network, no external
dependency. It exists so bounded contexts can react to one another's events
without importing each other (§2.15 no hidden magic — reactions are named
subscriptions to named events, not buried side effects).

Epic 2 scope: the bus exists and is used by the Artifact Registry and the Job
System to *emit* lifecycle events. Cross-context *reactions* (e.g. a checkpoint
event triggering a security job) are wired in later epics; the mechanism is ready.

Design notes:
- Handlers may be sync or async; ``publish`` awaits async handlers and calls sync
  ones directly.
- A failing handler NEVER breaks the publisher (graceful degradation, §2.13) — its
  exception is logged and swallowed so one bad subscriber can't cascade.
- Delivery is best-effort and in-order per publish; there is no persistence or
  replay here (event-sourced domains persist their own events separately).
"""
from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Union

from app.logging_config import get_logger

logger = get_logger("events")

# A subscriber may be sync (returns None) or async (returns an awaitable).
EventHandler = Callable[["Event"], Union[None, Awaitable[None]]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Event:
    """A platform event. ``name`` is a dotted string (e.g. ``artifact.published``,
    ``job.completed``); ``payload`` is a plain dict — never an ORM object, never a
    framework type, so subscribers stay decoupled from producers' internals."""

    name: str
    payload: dict = field(default_factory=dict)
    at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"name": self.name, "payload": self.payload,
                "at": self.at.isoformat() if self.at else None}


class EventBus:
    """In-process pub/sub. One process, one bus (the single-process constraint makes
    this safe — there is exactly one, and nothing else could observe a stale copy)."""

    def __init__(self) -> None:
        # exact-name subscribers + wildcard ("*") subscribers that see every event.
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._wildcard: list[EventHandler] = []

    def subscribe(self, event_name: str, handler: EventHandler) -> Callable[[], None]:
        """Register a handler for an event name (or ``"*"`` for all events).
        Returns an unsubscribe callable."""
        if event_name == "*":
            self._wildcard.append(handler)
            return lambda: self._wildcard.remove(handler) if handler in self._wildcard else None
        self._subscribers.setdefault(event_name, []).append(handler)

        def _unsub() -> None:
            lst = self._subscribers.get(event_name, [])
            if handler in lst:
                lst.remove(handler)
        return _unsub

    async def publish(self, event: Union[Event, str], payload: Optional[dict] = None) -> Event:
        """Publish an event to all matching subscribers. Accepts either an ``Event``
        or a ``(name, payload)`` pair for convenience. A handler that raises is
        logged and skipped — publishing never fails because of a subscriber."""
        evt = event if isinstance(event, Event) else Event(name=event, payload=payload or {})
        handlers = list(self._subscribers.get(evt.name, ())) + list(self._wildcard)
        for handler in handlers:
            try:
                result = handler(evt)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # noqa: BLE001 - a bad subscriber must not break publish
                logger.warning("event subscriber for %s failed: %s", evt.name, exc)
        return evt

    def publish_nowait(self, event: Union[Event, str], payload: Optional[dict] = None) -> None:
        """Fire-and-forget publish from a sync context. Schedules the async publish
        on the running loop if there is one; otherwise runs sync handlers inline and
        skips async ones (best-effort). Never raises."""
        evt = event if isinstance(event, Event) else Event(name=event, payload=payload or {})
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(evt))
        except RuntimeError:
            # No running loop — deliver to sync handlers only, best-effort.
            for handler in list(self._subscribers.get(evt.name, ())) + list(self._wildcard):
                try:
                    res = handler(evt)
                    if inspect.isawaitable(res):
                        res.close()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass

    def clear(self) -> None:
        """Drop all subscribers (used by tests for isolation)."""
        self._subscribers.clear()
        self._wildcard.clear()


# One process, one bus.
event_bus = EventBus()
