"""Suite registry — the pluggable catalog of benchmark suites.

Register a new dimension by adding one entry here; the queue, API, and UI pick it
up with no further changes. Order defines display order.
"""
from __future__ import annotations

from typing import Optional

from app.benchmarks.suites import (
    BenchmarkSuite,
    ContextSuite,
    HallucinationSuite,
    InstructionFollowingSuite,
    PerformanceSuite,
    ReasoningSuite,
    SecuritySuite,
)

_SUITES: dict[str, BenchmarkSuite] = {
    s.key: s
    for s in (
        PerformanceSuite(),
        ReasoningSuite(),
        InstructionFollowingSuite(),
        HallucinationSuite(),
        ContextSuite(),
        SecuritySuite(),
    )
}

# Sensible default when the caller doesn't pick suites.
DEFAULT_SUITES = ["performance", "security"]


def list_suites() -> list[dict]:
    return [
        {"key": s.key, "label": s.label, "dimension": s.dimension,
         "description": s.description, "real": s.real}
        for s in _SUITES.values()
    ]


def get_suite(key: str) -> Optional[BenchmarkSuite]:
    return _SUITES.get(key)


def valid_suites(keys: list[str]) -> list[str]:
    """Filter to known suite keys, preserving request order; empty → defaults."""
    seen = [k for k in keys if k in _SUITES]
    return seen or list(DEFAULT_SUITES)
