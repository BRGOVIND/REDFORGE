"""Runtime layer.

Two concerns live here:
  * **Estimation** — predict cost/duration of an evaluation before it runs.
  * **The unified LLM runtime** — the single client every feature uses to talk
    to a model provider (see ``manager.get_runtime``). Import the client lazily
    from ``app.runtime.manager`` / ``app.runtime.client`` to avoid pulling the
    transport stack into estimation-only call sites.
"""
from app.runtime.model_sizes import estimate_model_ram_mb
from app.runtime.runtime_estimator import (
    EstimationInputs,
    RuntimeEstimate,
    estimate_runtime,
    gather_latency_stats,
)

__all__ = [
    "estimate_model_ram_mb",
    "EstimationInputs",
    "RuntimeEstimate",
    "estimate_runtime",
    "gather_latency_stats",
]
