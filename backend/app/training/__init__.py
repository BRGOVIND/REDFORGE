"""Training Lab (RedForge V2, Phase 2.2) — local LoRA / QLoRA fine-tuning.

Completely isolated from the Runtime Manager, Security Center, and Benchmark
Center (Phase 3 integrates them). Training happens through a **swappable
provider** abstraction — Unsloth is one provider, never hardcoded across the app.

Providers:
  * ``simulation`` (default) — a realistic, dependency-free training loop so the
    whole UX works offline with no ML stack. Clearly labelled as a simulation.
  * ``unsloth`` — real LoRA/QLoRA via Unsloth + PEFT + Transformers +
    bitsandbytes; lazily imported and degrades with a clear message when the ML
    stack or a GPU is unavailable.

Privacy: nothing here uploads datasets, models, checkpoints, or logs.
"""
from app.training.manager import (
    available_backends,
    get_provider,
    register_provider,
)
from app.training.service import TrainingService, training_service

__all__ = [
    "available_backends",
    "get_provider",
    "register_provider",
    "TrainingService",
    "training_service",
]
