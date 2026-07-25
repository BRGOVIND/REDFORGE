"""Artifact lifecycle events (RedForge V3, Epic 2).

Names the internal platform events the Artifact Registry emits onto the shared
event bus (Constitution §8.6). Emitting is honest and explicit — a named event on
publish/version/archive, never a hidden side effect (§2.15). Subscribers (wired in
later epics) react without importing the registry.
"""
from __future__ import annotations

ARTIFACT_PUBLISHED = "artifact.published"
ARTIFACT_VERSION_CREATED = "artifact.version_created"
ARTIFACT_ARCHIVED = "artifact.archived"
ARTIFACT_INVALIDATED = "artifact.invalidated"


async def emit(name: str, payload: dict) -> None:
    from app.events import event_bus
    await event_bus.publish(name, payload)
