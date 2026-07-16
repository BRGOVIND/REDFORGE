"""Runtime Registry (RedForge V2, Phase 2.5).

Makes a training checkpoint a first-class **runnable model** through the existing
Runtime Manager, so the Playground and Security Center can use it like any other
model. Provider-agnostic: it maps a registry id → the model name the runtime
actually runs. When a provider can host the checkpoint's adapter it points at the
real fine-tuned model; otherwise (or when the simulation backend produced no
adapter files) it falls back to the base model, with full identity + metadata
stored for reproducibility. It never re-implements the runtime and never breaks
training.
"""
from app.runtime_registry.service import RuntimeRegistry, runtime_registry

__all__ = ["RuntimeRegistry", "runtime_registry"]
