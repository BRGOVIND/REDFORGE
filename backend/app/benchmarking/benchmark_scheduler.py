from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BenchmarkJobState:
    benchmark_run_id: int
    status: str = "pending"        # pending / running / completed / failed
    progress: int = 0              # 0-100
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


BENCHMARK_JOBS: dict[int, BenchmarkJobState] = {}


def register_job(benchmark_run_id: int) -> BenchmarkJobState:
    state = BenchmarkJobState(benchmark_run_id=benchmark_run_id)
    BENCHMARK_JOBS[benchmark_run_id] = state
    return state


def get_job(benchmark_run_id: int) -> Optional[BenchmarkJobState]:
    return BENCHMARK_JOBS.get(benchmark_run_id)


def update_job_status(
    benchmark_run_id: int,
    status: str,
    progress: int = 0,
    error: Optional[str] = None,
) -> None:
    state = BENCHMARK_JOBS.get(benchmark_run_id)
    if state:
        state.status = status
        state.progress = progress
        if error:
            state.error = error
