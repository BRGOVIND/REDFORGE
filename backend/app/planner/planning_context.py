"""Resolved inputs the planner reasons over.

The context does the I/O (reading attacks from the database or the benchmark
dataset, honoring the profile's per-category caps) so that the planner itself
stays a pure, deterministic function of its inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset import benchmark_loader
from app.db.models import Attack
from app.evaluation_profiles.profile import EvaluationProfile
from app.planner import planning_rules
from app.profiler.profile_builder import ModelProfile
from app.scheduler.plan_builder import (
    ATTACK_LIBRARY_ORDER,
    BENCHMARK_ORDER,
    PlanBuildError,
)


class AttackSpec(BaseModel):
    """A single attack, normalized across the attack library and benchmark."""

    ref: str                    # stable string id (e.g. "attack:12" or "pi_003")
    name: str
    prompt: str
    severity: str
    category: str
    attack_id: Optional[int] = None   # DB id when sourced from the attack table


@dataclass
class PlanningContext:
    profile: EvaluationProfile
    models: list[str]
    model_profiles: dict[str, ModelProfile]
    available_categories: list[str]
    canonical_order: list[str]
    # category -> capped, resolved attacks (ordering is the planner's job)
    attack_pool: dict[str, list[AttackSpec]]
    resources: Optional[dict] = field(default=None)

    @property
    def primary_model(self) -> str:
        return self.models[0]

    @property
    def primary_profile(self) -> ModelProfile:
        return self.model_profiles[self.primary_model]


def _canonical_order(dataset: str) -> list[str]:
    return ATTACK_LIBRARY_ORDER if dataset == "attack_library" else BENCHMARK_ORDER


async def _attack_library_pool(
    profile: EvaluationProfile, db: AsyncSession
) -> dict[str, list[AttackSpec]]:
    result = await db.execute(select(Attack).order_by(Attack.id.asc()))
    pool: dict[str, list[AttackSpec]] = {}
    for a in result.scalars().all():
        pool.setdefault(a.category, []).append(
            AttackSpec(
                ref=f"attack:{a.id}",
                name=a.name,
                prompt=a.prompt,
                severity=a.severity,
                category=a.category,
                attack_id=a.id,
            )
        )
    return pool


def _benchmark_pool(profile: EvaluationProfile) -> dict[str, list[AttackSpec]]:
    data = benchmark_loader.get_all()
    pool: dict[str, list[AttackSpec]] = {}
    for category, entries in data.items():
        specs = [
            AttackSpec(
                ref=str(entry.get("id", f"{category}_{i}")),
                name=str(entry.get("id", f"{category}_{i}")),
                prompt=entry.get("prompt", ""),
                severity=entry.get("severity", "medium"),
                category=category,
            )
            for i, entry in enumerate(entries)
        ]
        pool[category] = specs
    return pool


def _apply_caps(
    profile: EvaluationProfile, pool: dict[str, list[AttackSpec]]
) -> dict[str, list[AttackSpec]]:
    capped: dict[str, list[AttackSpec]] = {}
    for category, specs in pool.items():
        cap = planning_rules.per_category_cap(profile, len(specs))
        capped[category] = specs[:cap]
    return capped


async def build_planning_context(
    profile: EvaluationProfile,
    models: list[str],
    model_profiles: dict[str, ModelProfile],
    db: AsyncSession,
    *,
    resources: Optional[dict] = None,
) -> PlanningContext:
    if not models:
        raise PlanBuildError("at least one model is required to plan an evaluation")
    if not profile.multi_model:
        models = models[:1]

    if profile.dataset == "attack_library":
        raw_pool = await _attack_library_pool(profile, db)
    else:
        raw_pool = _benchmark_pool(profile)

    pool = _apply_caps(profile, raw_pool)
    canonical = _canonical_order(profile.dataset)

    available_categories = [c for c in canonical if pool.get(c)]
    if not profile.uses_all_categories:
        # Restrict to the profile's explicitly requested categories.
        requested = set(profile.categories)
        available_categories = [c for c in available_categories if c in requested]

    return PlanningContext(
        profile=profile,
        models=models,
        model_profiles=model_profiles,
        available_categories=available_categories,
        canonical_order=_canonical_order(profile.dataset),
        attack_pool=pool,
        resources=resources,
    )
