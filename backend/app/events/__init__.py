"""Internal platform event bus (RedForge V3, Epic 2 — Infrastructure layer).

Shared in-process pub/sub used by bounded contexts to react to one another without
importing each other. See :mod:`app.events.bus`.
"""
from app.events.bus import Event, EventBus, event_bus

__all__ = ["Event", "EventBus", "event_bus"]
