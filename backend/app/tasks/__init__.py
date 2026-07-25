"""Global Task Manager (RedForge V3) — the one unified view + control surface for ALL
long-running work. A thin projection over the single Execution Platform (Job System);
it introduces no new execution mechanism and no duplicated state."""
from __future__ import annotations

from app.tasks import facade
from app.tasks.service import TaskService, task_service

__all__ = ["facade", "TaskService", "task_service"]
