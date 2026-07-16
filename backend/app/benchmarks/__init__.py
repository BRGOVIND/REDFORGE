"""Benchmark Center (RedForge V2 Phase 3).

Objective, local, async comparison of base models, checkpoints, and final models
across pluggable suites. Reuses the Runtime Manager (performance), the Security
Center engine (security), and the Runtime Registry (checkpoint identity). Distinct
from the legacy v1 ``benchmarks`` (attack-suite) feature.
"""
from app.benchmarks.registry import get_suite, list_suites, valid_suites
from app.benchmarks.service import BenchmarkService, benchmark_center

__all__ = ["BenchmarkService", "benchmark_center", "get_suite", "list_suites", "valid_suites"]
