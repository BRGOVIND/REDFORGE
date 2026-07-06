"""In-process runtime metrics, exposed at GET /api/runtime/status."""
from __future__ import annotations

from collections import deque
from threading import Lock


class RuntimeMetrics:
    def __init__(self, window: int = 200) -> None:
        self._lock = Lock()
        self.active_requests = 0
        self.total_requests = 0
        self.completed = 0
        self.failed = 0
        self.cancelled = 0
        self.retries = 0
        self.queue_length = 0
        self._latencies: deque[float] = deque(maxlen=window)
        self._tps: deque[float] = deque(maxlen=window)

    def record_start(self) -> None:
        with self._lock:
            self.active_requests += 1
            self.total_requests += 1

    def record_end(self) -> None:
        with self._lock:
            self.active_requests = max(0, self.active_requests - 1)

    def record_complete(self, latency_ms: float, tokens_per_sec: float | None = None) -> None:
        with self._lock:
            self.completed += 1
            self._latencies.append(latency_ms)
            if tokens_per_sec:
                self._tps.append(tokens_per_sec)

    def record_fail(self) -> None:
        with self._lock:
            self.failed += 1

    def record_cancel(self) -> None:
        with self._lock:
            self.cancelled += 1

    def record_retry(self) -> None:
        with self._lock:
            self.retries += 1

    def set_queue_length(self, n: int) -> None:
        with self._lock:
            self.queue_length = n

    def snapshot(self) -> dict:
        with self._lock:
            avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
            avg_tps = sum(self._tps) / len(self._tps) if self._tps else 0.0
            return {
                "active_requests": self.active_requests,
                "queue_length": self.queue_length,
                "total_requests": self.total_requests,
                "completed_requests": self.completed,
                "failed_requests": self.failed,
                "cancelled_requests": self.cancelled,
                "retry_count": self.retries,
                "avg_latency_ms": round(avg_latency, 1),
                "avg_tokens_per_sec": round(avg_tps, 2),
            }


# Shared instance for the whole process.
metrics = RuntimeMetrics()
