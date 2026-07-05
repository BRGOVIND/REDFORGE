"""Estimate the cost of an evaluation *before* it runs.

Given how many base attacks a plan contains (per model), how they mutate, which
evaluator scores them, and which models are involved, this produces an estimate
of wall-clock time, LLM calls, memory, disk, and GPU footprint.

The time estimate is data-driven and *improves over time*: it prefers the
observed average latency of each model (from past ``TestRun`` rows) and only
falls back to a conservative default when a model has no history yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TestRun
from app.runtime.model_sizes import estimate_model_ram_mb

# Conservative fallback when a model has no recorded latency yet.
DEFAULT_LATENCY_MS = 4000.0
# Rough bytes persisted per LLM call (TestRun row + events).
BYTES_PER_CALL = 4096
# Fixed process/runtime overhead added on top of model weights.
BASE_OVERHEAD_RAM_MB = 600
# Extra probing rounds an adaptive agent adds, per model.
ADAPTIVE_AGENT_ROUNDS = 8
# Disk headroom reserved when a run generates a report.
REPORT_DISK_MB = 5


@dataclass
class EstimationInputs:
    """Everything the estimator needs, already resolved from a profile/plan."""

    models: list[str]
    # Base attacks executed against ONE model (sum across categories), before
    # mutation and passes are applied.
    base_attacks_per_model: int
    mutation_multiplier: int = 1  # 1 = no mutation; 1 + variants otherwise
    passes: int = 1
    uses_judge: bool = False
    judge_model: Optional[str] = None
    adaptive_agent: bool = False
    generate_report: bool = False


@dataclass
class RuntimeEstimate:
    estimated_seconds: float
    estimated_minutes: float
    estimated_ram_mb: int
    estimated_disk_mb: float
    estimated_gpu_mb: int
    estimated_llm_calls: int
    avg_latency_ms_used: float
    breakdown: dict = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "estimated_seconds": round(self.estimated_seconds, 1),
            "estimated_minutes": round(self.estimated_minutes, 2),
            "estimated_ram_mb": self.estimated_ram_mb,
            "estimated_disk_mb": round(self.estimated_disk_mb, 2),
            "estimated_gpu_mb": self.estimated_gpu_mb,
            "estimated_llm_calls": self.estimated_llm_calls,
            "avg_latency_ms_used": round(self.avg_latency_ms_used, 1),
            "breakdown": self.breakdown,
            "assumptions": self.assumptions,
        }


async def gather_latency_stats(db: AsyncSession, models: list[str]) -> dict[str, float]:
    """Average observed generation latency (ms) per model, from past runs.

    Models with no history are simply omitted; the estimator substitutes the
    default for them. This is the mechanism by which estimates sharpen as more
    evaluations accumulate.
    """
    if not models:
        return {}
    result = await db.execute(
        select(TestRun.model_name, func.avg(TestRun.latency_ms))
        .where(TestRun.model_name.in_(models))
        .where(TestRun.latency_ms.isnot(None))
        .group_by(TestRun.model_name)
    )
    return {name: float(avg) for name, avg in result.all() if avg is not None}


def _mean_latency(models: list[str], latency_by_model: dict[str, float]) -> tuple[float, bool]:
    """Return (mean latency ms across models, whether any history was used)."""
    samples = [latency_by_model[m] for m in models if m in latency_by_model]
    if samples:
        # Fill missing models with the default so the mean stays representative.
        missing = len(models) - len(samples)
        total = sum(samples) + missing * DEFAULT_LATENCY_MS
        return total / len(models), True
    return DEFAULT_LATENCY_MS, False


def estimate_runtime(
    inputs: EstimationInputs,
    latency_by_model: Optional[dict[str, float]] = None,
) -> RuntimeEstimate:
    """Pure, deterministic estimate. No I/O — callers pass in latency history."""
    latency_by_model = latency_by_model or {}
    models = inputs.models or []
    model_count = max(len(models), 0)

    # --- LLM call accounting -------------------------------------------------
    per_model_target = (
        inputs.base_attacks_per_model
        * max(inputs.mutation_multiplier, 1)
        * max(inputs.passes, 1)
    )
    target_calls = per_model_target * model_count
    judge_calls = target_calls if inputs.uses_judge else 0
    agent_calls = ADAPTIVE_AGENT_ROUNDS * model_count if inputs.adaptive_agent else 0
    total_calls = target_calls + judge_calls + agent_calls

    # --- Time ----------------------------------------------------------------
    target_latency, used_history = _mean_latency(models, latency_by_model)
    judge_latency = latency_by_model.get(inputs.judge_model or "", DEFAULT_LATENCY_MS)

    target_seconds = (target_calls + agent_calls) * target_latency / 1000.0
    judge_seconds = judge_calls * judge_latency / 1000.0
    total_seconds = target_seconds + judge_seconds

    # --- Memory / GPU --------------------------------------------------------
    # Ollama loads one model at a time, so peak weight memory is the largest
    # single model, plus the judge if a separate judge model is used.
    largest_model_ram = max((estimate_model_ram_mb(m) for m in models), default=0)
    judge_ram = (
        estimate_model_ram_mb(inputs.judge_model)
        if inputs.uses_judge and inputs.judge_model and inputs.judge_model not in models
        else 0
    )
    weights_ram = largest_model_ram + judge_ram
    estimated_ram_mb = weights_ram + BASE_OVERHEAD_RAM_MB
    # If a GPU is used, weights live in VRAM; overhead stays in system RAM.
    estimated_gpu_mb = weights_ram

    # --- Disk ----------------------------------------------------------------
    estimated_disk_mb = total_calls * BYTES_PER_CALL / (1024 * 1024)
    if inputs.generate_report:
        estimated_disk_mb += REPORT_DISK_MB

    assumptions: list[str] = []
    if not used_history:
        assumptions.append(
            f"no latency history for selected model(s); assumed {DEFAULT_LATENCY_MS:.0f} ms/call"
        )
    else:
        assumptions.append("time based on observed average latency of past runs")
    assumptions.append("assumes models are loaded sequentially (one at a time)")
    if inputs.uses_judge:
        assumptions.append("LLM-judge doubles model calls (one judge call per attack)")

    return RuntimeEstimate(
        estimated_seconds=total_seconds,
        estimated_minutes=total_seconds / 60.0,
        estimated_ram_mb=estimated_ram_mb,
        estimated_disk_mb=estimated_disk_mb,
        estimated_gpu_mb=estimated_gpu_mb,
        estimated_llm_calls=total_calls,
        avg_latency_ms_used=target_latency,
        breakdown={
            "models": model_count,
            "base_attacks_per_model": inputs.base_attacks_per_model,
            "mutation_multiplier": inputs.mutation_multiplier,
            "passes": inputs.passes,
            "target_calls": target_calls,
            "judge_calls": judge_calls,
            "agent_calls": agent_calls,
        },
        assumptions=assumptions,
    )
