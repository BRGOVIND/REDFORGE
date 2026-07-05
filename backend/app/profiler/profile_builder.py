"""Assemble a complete :class:`ModelProfile` from capabilities + history + DB.

A profile is the engine's understanding of a model *before* evaluation: how big
it is, how fast it has been, where it has failed before, and how much memory it
needs. The planner uses this to make intelligent, deterministic decisions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attack, BenchmarkRun, ModelScore, TestRun
from app.profiler.capability_detector import Capabilities, detect_capabilities
from app.runtime.model_sizes import estimate_model_ram_mb


class ModelProfile(BaseModel):
    model_name: str
    parameter_size: Optional[float] = None       # billions
    parameter_label: Optional[str] = None
    quantization: Optional[str] = None
    context_length: Optional[int] = None
    family: Optional[str] = None

    avg_latency_ms: Optional[float] = None
    historical_benchmark_scores: dict = Field(default_factory=dict)
    historical_failure_categories: list[str] = Field(default_factory=list)
    resource_footprint_mb: int = 0
    installed_locally: bool = False
    capability_source: str = "name"
    ollama_metadata: dict = Field(default_factory=dict)
    profiled_at: Optional[datetime] = None

    @property
    def historical_overall_score(self) -> Optional[float]:
        val = self.historical_benchmark_scores.get("overall_score")
        return float(val) if val is not None else None


def _capabilities_to_fields(caps: Capabilities) -> dict:
    return {
        "parameter_size": caps.parameter_size,
        "parameter_label": caps.parameter_label,
        "quantization": caps.quantization,
        "context_length": caps.context_length,
        "family": caps.family,
        "capability_source": caps.source,
    }


async def _avg_latency(db: AsyncSession, model_name: str) -> Optional[float]:
    result = await db.execute(
        select(func.avg(TestRun.latency_ms))
        .where(TestRun.model_name == model_name)
        .where(TestRun.latency_ms.isnot(None))
    )
    avg = result.scalar_one_or_none()
    return float(avg) if avg is not None else None


async def _latest_benchmark_scores(db: AsyncSession, model_name: str) -> dict:
    result = await db.execute(
        select(ModelScore)
        .join(BenchmarkRun, ModelScore.benchmark_run_id == BenchmarkRun.id)
        .where(ModelScore.model_name == model_name)
        .order_by(ModelScore.created_at.desc())
        .limit(1)
    )
    score = result.scalar_one_or_none()
    if score is None:
        return {}
    return {
        "overall_score": score.overall_score,
        "injection_rate": score.injection_rate,
        "jailbreak_rate": score.jailbreak_rate,
        "hallucination_rate": score.hallucination_rate,
        "data_leakage_rate": score.data_leakage_rate,
        "avg_latency_ms": score.avg_latency_ms,
    }


async def _failure_categories(db: AsyncSession, model_name: str) -> list[str]:
    """Categories where this model has historically been compromised (FAIL),
    ordered by failure count descending (deterministic tiebreak by category)."""
    result = await db.execute(
        select(Attack.category, func.count(TestRun.id).label("fails"))
        .join(Attack, TestRun.attack_id == Attack.id)
        .where(TestRun.model_name == model_name)
        .where(TestRun.verdict == "FAIL")
        .group_by(Attack.category)
        .order_by(func.count(TestRun.id).desc(), Attack.category.asc())
    )
    return [cat for cat, _ in result.all()]


async def build_model_profile(
    model_name: str,
    db: AsyncSession,
    *,
    ollama_show: Optional[dict] = None,
    installed_locally: bool = False,
) -> ModelProfile:
    caps = detect_capabilities(model_name, ollama_show)

    avg_latency = await _avg_latency(db, model_name)
    benchmark_scores = await _latest_benchmark_scores(db, model_name)
    failure_categories = await _failure_categories(db, model_name)

    return ModelProfile(
        model_name=model_name,
        avg_latency_ms=avg_latency,
        historical_benchmark_scores=benchmark_scores,
        historical_failure_categories=failure_categories,
        resource_footprint_mb=estimate_model_ram_mb(model_name),
        installed_locally=installed_locally or bool(ollama_show),
        ollama_metadata=(ollama_show.get("details", {}) if ollama_show else {}),
        profiled_at=datetime.now(timezone.utc),
        **_capabilities_to_fields(caps),
    )
