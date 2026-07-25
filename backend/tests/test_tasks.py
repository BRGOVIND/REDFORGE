"""Global Task Manager tests — Job→Task projection, ETA moving average, control."""
from __future__ import annotations

import pytest

from app.tasks import facade
from app.tasks.service import TaskService


def _job(**over):
    base = {
        "id": "j1", "type": "training", "status": "running",
        "progress": {"fraction": 0.4, "step": 4, "total": 10, "message": "training…"},
        "params": {"name": "My run"}, "target_ref": "run-1", "attempts": 1, "max_attempts": 1,
        "logs": ["a", "b", "c", "d"], "error": None, "result": None, "metadata": {},
        "created_at": "2026-07-26T10:00:00+00:00", "started_at": "2026-07-26T10:00:00+00:00",
        "completed_at": None,
    }
    base.update(over)
    return base


def test_to_task_shape_and_percent():
    t = facade.to_task(_job())
    assert t["label"] == "Training"
    assert t["progress"] == 40            # 0.4 → integer percent
    assert t["current_step"] == "training…"
    assert t["cancellable"] is True and t["retryable"] is False
    assert t["logs_tail"] == ["b", "c", "d"]   # tail only in the list view


def test_eta_from_moving_average():
    # 0.2 → 0.4 over 10s ⇒ 0.02/s ⇒ remaining 0.6 ⇒ ~30s.
    job = _job(progress={"fraction": 0.4, "message": "x"},
               metadata={"_eta_samples": [["2026-07-26T10:00:00+00:00", 0.2],
                                          ["2026-07-26T10:00:10+00:00", 0.4]]})
    eta = facade.estimate_eta_seconds(job, facade._now())
    assert eta is not None and 25 <= eta <= 35


def test_no_eta_when_not_running_or_complete():
    assert facade.estimate_eta_seconds(_job(status="completed"), facade._now()) is None
    assert facade.estimate_eta_seconds(_job(progress={"fraction": 1.0}), facade._now()) is None


def test_retryable_only_when_budget_remains():
    assert facade.to_task(_job(status="failed", attempts=1, max_attempts=3))["retryable"] is True
    assert facade.to_task(_job(status="failed", attempts=3, max_attempts=3))["retryable"] is False
    assert facade.to_task(_job(status="cancelled"))["retryable"] is True


def test_label_fallback_titlecases_unknown_kind():
    assert facade.label_for("workspace_index") == "Workspace indexing"
    assert facade.label_for("some_new_kind") == "Some New Kind"


def test_summary_counts():
    tasks = [facade.to_task(_job(id=str(i), status=s))
             for i, s in enumerate(["running", "running", "queued", "failed", "completed"])]
    s = facade.summarize(tasks)
    assert s["running"] == 2 and s["queued"] == 1 and s["active"] == 3 and s["failed"] == 1


# --- service control over an injected fake execution platform --------------------

class _FakeRepo:
    def __init__(self, store):
        self.store = store

    async def delete(self, jid):
        return self.store.pop(jid, None) is not None


class _FakeJobs:
    def __init__(self):
        self.jobs: dict = {}
        self._repo = _FakeRepo(self.jobs)

    async def list(self, *, status=None, type=None, limit=200):
        out = [j for j in self.jobs.values()
               if (status is None or j["status"] == status) and (type is None or j["type"] == type)]
        return out[:limit]

    async def get(self, jid):
        return self.jobs.get(jid)

    async def cancel(self, jid):
        if jid in self.jobs:
            self.jobs[jid]["status"] = "cancelled"
        return {"cancelled": True, "id": jid}

    async def retry(self, jid):
        self.jobs[jid]["status"] = "queued"
        return self.jobs[jid]


@pytest.mark.asyncio
async def test_service_list_summary_cancel_retry_delete():
    fake = _FakeJobs()
    fake.jobs["a"] = _job(id="a", status="running")
    fake.jobs["b"] = _job(id="b", status="failed", attempts=1, max_attempts=2)
    svc = TaskService(jobs=fake)

    listed = await svc.list()
    assert {t["id"] for t in listed["tasks"]} == {"a", "b"}
    assert listed["tasks"][0]["status"] == "running"      # active first
    assert listed["summary"]["running"] == 1

    active = await svc.list(active_only=True)
    assert {t["id"] for t in active["tasks"]} == {"a"}

    assert (await svc.cancel("a"))["cancelled"] is True
    assert fake.jobs["a"]["status"] == "cancelled"

    retried = await svc.retry("b")
    assert retried["status"] == "queued"

    # delete cancels a live task first, then removes it
    assert await svc.delete("a") is True and "a" not in fake.jobs
