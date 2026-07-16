"""In-memory live-progress store for active training runs.

Holds the latest metrics, a bounded history for live charts, a log tail, and the
cancel/pause flags — keyed by run id. The SSE stream and the snapshot endpoint
both read from here; the runner writes to it. Process-local (live state only —
the durable record lives in the DB).
"""
from __future__ import annotations

import time
from collections import deque
from typing import Optional


class RunState:
    def __init__(self, run_id: str, total_steps: int = 0) -> None:
        self.run_id = run_id
        self.status = "pending"
        self.latest: dict = {}
        self.history: deque[dict] = deque(maxlen=2000)  # step-level points for charts
        self.logs: deque[str] = deque(maxlen=500)
        self.cancelled = False
        self.paused = False
        self.updated_at = time.time()

    def snapshot(self, *, history_tail: int = 500) -> dict:
        hist = list(self.history)
        return {
            "run_id": self.run_id,
            "status": self.status,
            "latest": self.latest,
            "history": hist[-history_tail:],
            "logs": list(self.logs)[-100:],
            "paused": self.paused,
        }


class ProgressStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def start(self, run_id: str) -> RunState:
        st = RunState(run_id)
        st.status = "running"
        self._runs[run_id] = st
        return st

    def get(self, run_id: str) -> Optional[RunState]:
        return self._runs.get(run_id)

    def update(self, run_id: str, event: dict) -> None:
        st = self._runs.get(run_id)
        if st is None:
            return
        st.status = event.get("status", st.status)
        st.latest = event
        st.updated_at = time.time()
        if event.get("step"):
            st.history.append({
                "step": event["step"], "epoch": event.get("epoch"),
                "loss": event.get("loss"), "val_loss": event.get("val_loss"),
                "learning_rate": event.get("learning_rate"),
            })
        if event.get("message"):
            st.logs.append(f"[{event.get('step', 0)}] {event['message']}")

    def cancel(self, run_id: str) -> bool:
        st = self._runs.get(run_id)
        if st is None:
            return False
        st.cancelled = True
        return True

    def pause(self, run_id: str, paused: bool) -> bool:
        st = self._runs.get(run_id)
        if st is None:
            return False
        st.paused = paused
        return True

    def discard(self, run_id: str) -> None:
        self._runs.pop(run_id, None)


progress_store = ProgressStore()
