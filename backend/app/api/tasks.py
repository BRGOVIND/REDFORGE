"""Global Task Manager API (RedForge V3).

The single endpoint set the desktop UI uses for the Task Panel, the top-bar "Running
(N)" indicator, and task history. Everything is a projection/controller over the one
Execution Platform (Job System) — no new execution path.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.tasks import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(status: Optional[str] = Query(None),
                     kind: Optional[str] = Query(None),
                     active_only: bool = Query(False),
                     limit: int = Query(200, ge=1, le=500)) -> dict:
    """All tasks (active first) + an aggregate summary for the top bar."""
    return await task_service.list(status=status, kind=kind, active_only=active_only, limit=limit)


@router.get("/summary")
async def summary() -> dict:
    """Just the counts (running/queued/failed/…) — cheap for frequent polling."""
    return await task_service.summary()


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    t = await task_service.get(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    return t


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    return await task_service.cancel(task_id)


@router.post("/{task_id}/retry")
async def retry_task(task_id: str) -> dict:
    t = await task_service.retry(task_id)
    if t is None:
        raise HTTPException(status_code=404, detail="task not found")
    return t


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict:
    ok = await task_service.delete(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task not found")
    return {"deleted": True, "id": task_id}
