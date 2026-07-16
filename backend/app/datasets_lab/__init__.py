"""Dataset Lab (RedForge V2, Phase 2) — local-first dataset management.

Isolated, dependency-light dataset logic: parsing, quality analysis, cleaning,
and splitting are pure functions with no runtime/provider or training coupling.
Persistence + versioning live in :mod:`app.datasets_lab.service`.

Training logic (fine-tuning/LoRA/benchmarks) is explicitly out of scope and must
not be added here.
"""
from app.datasets_lab.service import DatasetService, dataset_service

__all__ = ["DatasetService", "dataset_service"]
