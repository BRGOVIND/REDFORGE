"""Pluggable benchmark-suite contract.

Every suite implements :class:`BenchmarkSuite`. A suite receives a
:class:`SuiteContext` (the runnable model name + an injectable ``generate_fn`` so
tests never touch a real provider) and returns a :class:`SuiteResult` (a single
normalized 0–100 score plus detailed metrics). Suites are registered in
:mod:`app.benchmarks.registry`; adding a new dimension is a one-file change.

Honesty: only suites that can measure something locally return ``simulated=False``
(Performance via the Runtime Manager, Security via the existing engine). Suites
that need labeled datasets (reasoning, hallucination, …) ship as *architecture*:
they run a light behavioural probe and mark ``simulated=True`` until a dataset
adapter is attached — the same graceful-fallback pattern as the Runtime Registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Protocol

# generate_fn(model, prompt, options?) -> text response
GenerateFn = Callable[..., Awaitable[str]]


@dataclass
class SuiteContext:
    model: str                                   # runnable model name (resolved)
    generate_fn: GenerateFn                      # injectable — defaults to Runtime Manager
    provider: Optional[str] = None
    config: dict = field(default_factory=dict)   # sampling / suite params
    resources: dict = field(default_factory=dict)  # hardware snapshot (cpu/gpu/ram/vram)


@dataclass
class SuiteResult:
    suite: str
    score: Optional[float]                       # primary 0–100 score (None if N/A)
    metrics: dict = field(default_factory=dict)  # detailed, suite-specific
    simulated: bool = False                      # True → architecture/probe, not a real dataset run
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "suite": self.suite,
            "score": self.score,
            "metrics": self.metrics,
            "simulated": self.simulated,
            "note": self.note,
        }


class BenchmarkSuite(Protocol):
    key: str
    label: str
    dimension: str
    description: str
    real: bool                                   # True → measures something locally

    async def run(self, ctx: SuiteContext) -> SuiteResult: ...


def _stable_probe_score(model: str, dimension: str, sample: str) -> float:
    """Deterministic 0–100 pseudo-score for architecture suites, derived from the
    model identity + a probe response so the same model scores consistently and
    different models spread out. Clearly flagged ``simulated`` by the caller —
    never presented as a real benchmark number."""
    h = 0
    for ch in f"{model}|{dimension}|{sample[:64]}":
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return round(55 + (h % 4000) / 100.0, 2)   # 55.00–95.00, stable per (model, dim)
