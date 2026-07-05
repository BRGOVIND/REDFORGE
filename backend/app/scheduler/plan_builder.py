"""Expand an evaluation profile into a deterministic execution plan.

Ordering is fixed and reproducible: attack steps are emitted model-major, then
category in a canonical order, followed by any per-model agent step, and finally
the global leaderboard/report steps. Given the same profile, models, and
dataset contents, the produced plan (and its ``deterministic_key``) is identical
every time — the property the scheduler relies on for resume.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dataset import benchmark_loader
from app.db.models import Attack
from app.evaluation_profiles.profile import ALL_CATEGORIES, EvaluationProfile
from app.scheduler.execution_plan import ExecutionPlan, PlanStep

# Canonical, stable category ordering for each dataset source.
ATTACK_LIBRARY_ORDER = [
    "PROMPT_INJECTION",
    "JAILBREAK",
    "CONTEXT_MANIPULATION",
    "DATA_LEAKAGE",
]
BENCHMARK_ORDER = [
    "prompt_injection",
    "jailbreak",
    "data_leakage",
    "hallucination",
    "toxicity",
]


class PlanBuildError(ValueError):
    """Raised when a profile cannot be expanded (e.g. unknown category)."""


def _order_for_dataset(dataset: str) -> list[str]:
    return ATTACK_LIBRARY_ORDER if dataset == "attack_library" else BENCHMARK_ORDER


async def _attack_library_counts(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        select(Attack.category, func.count(Attack.id)).group_by(Attack.category)
    )
    return {cat: int(n) for cat, n in result.all()}


def _benchmark_counts() -> dict[str, int]:
    data = benchmark_loader.get_all()
    return {cat: len(entries) for cat, entries in data.items()}


async def _available_counts(profile: EvaluationProfile, db: AsyncSession) -> dict[str, int]:
    if profile.dataset == "attack_library":
        return await _attack_library_counts(db)
    return _benchmark_counts()


def _resolve_categories(profile: EvaluationProfile, available: dict[str, int]) -> list[str]:
    canonical = _order_for_dataset(profile.dataset)
    present = [c for c in canonical if c in available]
    if profile.uses_all_categories:
        return present
    # Explicit categories: keep them in canonical order, validate membership.
    unknown = [c for c in profile.categories if c not in available]
    if unknown:
        raise PlanBuildError(
            f"profile '{profile.name}' references categories not in dataset "
            f"'{profile.dataset}': {unknown}"
        )
    return [c for c in canonical if c in profile.categories]


def _per_category_base(profile: EvaluationProfile, available_in_category: int) -> int:
    """How many base attacks to take from a category, honoring profile caps."""
    count = available_in_category
    if profile.dataset == "attack_library" and profile.attacks_per_category is not None:
        count = min(count, profile.attacks_per_category)
    elif profile.dataset == "benchmark_sample" and profile.benchmark_sample_size is not None:
        count = min(count, profile.benchmark_sample_size)
    # full_benchmark uses everything available.
    return count


async def build_execution_plan(
    profile: EvaluationProfile,
    models: list[str],
    db: AsyncSession,
) -> ExecutionPlan:
    if not models:
        raise PlanBuildError("at least one model is required to build a plan")
    if not profile.multi_model and len(models) > 1:
        # Non-comparative profiles evaluate a single model; use the first.
        models = models[:1]

    available = await _available_counts(profile, db)
    categories = _resolve_categories(profile, available)
    if not categories:
        raise PlanBuildError(
            f"profile '{profile.name}' resolved to zero categories for dataset "
            f"'{profile.dataset}'"
        )

    mult = profile.mutation_multiplier
    passes = profile.passes
    steps: list[PlanStep] = []
    order = 0
    base_per_model = 0

    # --- attack steps: model-major, canonical category order ---------------
    for model in models:
        model_base = 0
        for category in categories:
            base = _per_category_base(profile, available[category])
            model_base += base
            total_prompts = base * mult * passes
            steps.append(
                PlanStep(
                    order=order,
                    kind="attack",
                    description=f"Evaluate {model} on {category}",
                    model=model,
                    category=category,
                    dataset=profile.dataset,
                    base_attacks=base,
                    mutation_multiplier=mult,
                    passes=passes,
                    total_prompts=total_prompts,
                    evaluator=profile.evaluator,
                )
            )
            order += 1
        # Per-model adaptive agent step, if enabled.
        if profile.adaptive_agent:
            steps.append(
                PlanStep(
                    order=order,
                    kind="agent",
                    description=f"Adaptive red-team agent against {model}",
                    model=model,
                    dataset=profile.dataset,
                    evaluator=profile.evaluator,
                )
            )
            order += 1
        base_per_model = model_base  # identical across models (same category set)

    # --- global terminal steps ---------------------------------------------
    if profile.generate_leaderboard:
        steps.append(
            PlanStep(
                order=order,
                kind="leaderboard",
                description="Rank evaluated models by security score",
            )
        )
        order += 1
    if profile.generate_report:
        steps.append(
            PlanStep(
                order=order,
                kind="report",
                description="Generate downloadable evaluation report",
            )
        )
        order += 1

    attack_steps = [s for s in steps if s.kind == "attack"]
    total_base = sum(s.base_attacks for s in attack_steps)
    total_prompts = sum(s.total_prompts for s in attack_steps)

    notes: list[str] = []
    if profile.dataset == "attack_library" and profile.attacks_per_category is not None:
        capped = [c for c in categories if available[c] < profile.attacks_per_category]
        if capped:
            notes.append(
                f"attacks_per_category={profile.attacks_per_category} exceeds available "
                f"attacks in: {capped}; using all available there"
            )

    plan = ExecutionPlan(
        profile=profile.name,
        models=models,
        dataset=profile.dataset,
        categories=categories,
        steps=steps,
        base_attacks_per_model=base_per_model,
        total_base_attacks=total_base,
        total_prompts=total_prompts,
        attack_step_count=len(attack_steps),
        notes=notes,
    )
    plan.deterministic_key = plan.compute_key()
    return plan
