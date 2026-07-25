"""Job lifecycle events (RedForge V3, Epic 2).

Names the internal platform events the Job System emits onto the shared event bus
(Constitution §8.6). Later epics subscribe to react (e.g. a checkpoint job's
completion triggering a security job) without importing the Job System.
"""
from __future__ import annotations

JOB_STARTED = "job.started"
JOB_PROGRESS = "job.progress"
JOB_COMPLETED = "job.completed"
JOB_FAILED = "job.failed"
JOB_CANCELLED = "job.cancelled"


async def emit(name: str, payload: dict) -> None:
    from app.events import event_bus
    await event_bus.publish(name, payload)
