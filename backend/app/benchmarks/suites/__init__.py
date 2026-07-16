"""Benchmark suites — one module per dimension, all pluggable."""
from app.benchmarks.suites.base import BenchmarkSuite, SuiteContext, SuiteResult
from app.benchmarks.suites.performance import PerformanceSuite
from app.benchmarks.suites.quality import (
    ContextSuite,
    HallucinationSuite,
    InstructionFollowingSuite,
)
from app.benchmarks.suites.reasoning import ReasoningSuite
from app.benchmarks.suites.security import SecuritySuite

__all__ = [
    "BenchmarkSuite",
    "SuiteContext",
    "SuiteResult",
    "PerformanceSuite",
    "ReasoningSuite",
    "InstructionFollowingSuite",
    "HallucinationSuite",
    "ContextSuite",
    "SecuritySuite",
]
