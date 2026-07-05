"""Generate an intelligent, deterministic evaluation plan.

The planner turns *what the user asked for* (an evaluation profile) plus *what we
know about the model* (its profile and history) into a concrete, ordered attack
sequence with explicit decisions about mutation, judging, retries, and
checkpointing. It is a pure function of the :class:`PlanningContext` — given the
same context it always produces the same plan (and the same ``deterministic_key``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from pydantic import BaseModel, Field

from app.planner import planning_rules
from app.planner.planning_context import PlanningContext
from app.scheduler.plan_builder import build_execution_plan


class PlannedAttack(BaseModel):
    order: int
    model: str
    category: str
    attack_ref: str
    attack_name: str
    prompt: str
    severity: str
    priority_rank: int
    attack_id: Optional[int] = None


class EvaluationPlan(BaseModel):
    profile: str
    models: list[str]
    dataset: str
    category_order: list[str]

    evaluator: str
    judge_model: Optional[str] = None
    mutation_level: int = 0
    escalation_strategies: list[str] = Field(default_factory=list)
    max_retries: int = 0
    checkpoint_frequency: int = 1

    attack_sequence: list[PlannedAttack] = Field(default_factory=list)
    total_attacks: int = 0

    # Human-readable rationale for each decision — surfaced to the UI.
    decisions: dict = Field(default_factory=dict)
    # Sprint-2 step-level plan, embedded for visualization.
    base_execution_plan: Optional[dict] = None

    deterministic_key: str = ""

    def compute_key(self) -> str:
        signature = [
            (a.order, a.model, a.category, a.attack_ref, a.priority_rank)
            for a in self.attack_sequence
        ]
        blob = json.dumps(
            {
                "profile": self.profile,
                "models": self.models,
                "category_order": self.category_order,
                "mutation_level": self.mutation_level,
                "max_retries": self.max_retries,
                "checkpoint_frequency": self.checkpoint_frequency,
                "sequence": signature,
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


class EvaluationPlanner:
    def build(self, context: PlanningContext) -> EvaluationPlan:
        profile = context.profile
        primary = context.primary_profile

        # --- decisions (deterministic rules) -------------------------------
        order = planning_rules.category_order(
            primary.historical_failure_categories,
            context.available_categories,
            context.canonical_order,
        )
        evaluator, judge_model = planning_rules.select_judge(profile)
        mut_level = planning_rules.mutation_level(profile, primary.historical_overall_score)
        retries = planning_rules.retry_budget(profile, primary.historical_overall_score)

        # --- ordered attack sequence ---------------------------------------
        sequence: list[PlannedAttack] = []
        idx = 0
        for model in context.models:
            for category in order:
                specs = context.attack_pool.get(category, [])
                # Priority: severity desc, then stable ref for determinism.
                ordered_specs = sorted(
                    specs,
                    key=lambda s: (planning_rules.severity_rank(s.severity), s.ref),
                )
                for rank, spec in enumerate(ordered_specs):
                    sequence.append(
                        PlannedAttack(
                            order=idx,
                            model=model,
                            category=category,
                            attack_ref=spec.ref,
                            attack_name=spec.name,
                            prompt=spec.prompt,
                            severity=spec.severity,
                            priority_rank=rank,
                            attack_id=spec.attack_id,
                        )
                    )
                    idx += 1

        total = len(sequence)
        checkpoint = planning_rules.checkpoint_frequency(profile, total)
        escalation = planning_rules.escalation_strategies(max(retries, mut_level))

        robust = planning_rules.is_robust(primary.historical_overall_score)
        decisions = {
            "category_order_reason": (
                "prioritized historically weak categories, then canonical order"
                if primary.historical_failure_categories
                else "no failure history; canonical order used"
            ),
            "attack_priority_reason": "highest-severity attacks first within each category",
            "mutation_level_reason": (
                f"profile mutation count {profile.mutation.count}"
                + (" +1 (model is historically robust)" if robust and profile.mutation.enabled else "")
            ),
            "judge_reason": f"evaluator '{evaluator}'"
            + (f" using judge model '{judge_model}'" if judge_model else ""),
            "retry_reason": (
                f"profile max_retries {profile.retry.max_retries}"
                + (" +1 (model is historically robust)" if robust and profile.retry.enabled else "")
                if profile.retry.enabled
                else "retries disabled by profile"
            ),
            "checkpoint_reason": (
                f"every {checkpoint} attacks"
                + (" (widened for a large run)" if total > 100 and checkpoint > profile.checkpoint.frequency else "")
            ),
            "model_robust": robust,
        }

        plan = EvaluationPlan(
            profile=profile.name,
            models=context.models,
            dataset=profile.dataset,
            category_order=order,
            evaluator=evaluator,
            judge_model=judge_model,
            mutation_level=mut_level,
            escalation_strategies=escalation,
            max_retries=retries,
            checkpoint_frequency=checkpoint,
            attack_sequence=sequence,
            total_attacks=total,
            decisions=decisions,
        )
        plan.deterministic_key = plan.compute_key()
        return plan

    async def plan(self, context: PlanningContext, db) -> EvaluationPlan:
        """Build the plan and attach the Sprint-2 step-level execution plan."""
        plan = self.build(context)
        try:
            base = await build_execution_plan(context.profile, context.models, db)
            plan.base_execution_plan = base.model_dump()
        except Exception:
            # The step-level plan is purely informational; never fail planning.
            plan.base_execution_plan = None
        return plan
