"""Continuous Security (RedForge V2, Phase 2.3).

Wires the Training Lab into the existing Security Center: when a training
checkpoint is created, a security evaluation is scheduled automatically and runs
asynchronously (queued, cancellable, never blocking training or the UI). Results
are stored per checkpoint to build a security timeline and checkpoint comparison.

This is **orchestration only** — it reuses the existing evaluation engine
(`app.sessions` + `app.analysis`); it never implements a second evaluator.
Everything stays local.
"""
from app.continuous_security.service import (
    ContinuousSecurityService,
    continuous_security,
)

__all__ = ["ContinuousSecurityService", "continuous_security"]
