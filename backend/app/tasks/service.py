"""Global Task Manager — application service.

The single facade the UI (and CLI) talk to for ALL long-running work. It delegates
control (cancel/retry/delete) to the one Execution Platform (``job_service``) and
projects Jobs into Tasks via ``facade``. No new persistence, no duplicated state.
"""
from __future__ import annotations

from typing import Optional

from app.tasks import facade


class TaskService:
    def __init__(self, jobs=None) -> None:
        self._jobs = jobs  # injectable for tests; else the singleton

    def _job_service(self):
        if self._jobs is not None:
            return self._jobs
        from app.jobs import job_service
        return job_service

    async def list(self, *, status: Optional[str] = None, kind: Optional[str] = None,
                   active_only: bool = False, limit: int = 200) -> dict:
        jobs = await self._job_service().list(status=status, type=kind, limit=limit)
        tasks = [facade.to_task(j) for j in jobs]
        if active_only:
            tasks = [t for t in tasks if t["status"] in ("running", "queued", "paused")]
        # Active first (running → queued → paused), then most-recent terminal.
        order = {"running": 0, "queued": 1, "paused": 2}
        tasks.sort(key=lambda t: (order.get(t["status"], 3),
                                  -(_epoch(t.get("created_at")))))
        return {"tasks": tasks, "summary": facade.summarize(tasks)}

    async def summary(self) -> dict:
        jobs = await self._job_service().list(limit=500)
        return facade.summarize([facade.to_task(j) for j in jobs])

    async def get(self, task_id: str) -> Optional[dict]:
        job = await self._job_service().get(task_id)
        if job is None:
            return None
        t = facade.to_task(job)
        t["logs"] = job.get("logs") or []   # full logs on the detail view
        return t

    async def cancel(self, task_id: str) -> dict:
        return await self._job_service().cancel(task_id)

    async def retry(self, task_id: str) -> Optional[dict]:
        job = await self._job_service().retry(task_id)
        return facade.to_task(job) if job else None

    async def delete(self, task_id: str) -> bool:
        js = self._job_service()
        # Only terminal tasks may be deleted; cancel a live one first.
        job = await js.get(task_id)
        if job is None:
            return False
        if job.get("status") in ("running", "queued", "paused"):
            await js.cancel(task_id)
        repo = getattr(js, "_repo", None)
        if repo is not None and hasattr(repo, "delete"):
            return await repo.delete(task_id)
        return False


def _epoch(iso: Optional[str]) -> float:
    from datetime import datetime, timezone
    if not iso:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return 0.0


task_service = TaskService()
