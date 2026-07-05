"""Execution plan data structures.

A plan is the concrete, ordered, *deterministic* expansion of a profile for a
given set of models. It is pure data (Pydantic) so it can be returned over the
API, persisted in a session, and later visualized by the UI without any of the
scheduler's logic leaking out.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal, Optional

from pydantic import BaseModel, Field

StepKind = Literal["attack", "agent", "leaderboard", "report"]


class PlanStep(BaseModel):
    order: int
    kind: StepKind
    description: str
    model: Optional[str] = None
    category: Optional[str] = None
    dataset: Optional[str] = None
    # Base attacks selected for this step (before mutation/passes).
    base_attacks: int = 0
    mutation_multiplier: int = 1
    passes: int = 1
    # base_attacks * mutation_multiplier * passes
    total_prompts: int = 0
    evaluator: Optional[str] = None


class ExecutionPlan(BaseModel):
    profile: str
    models: list[str]
    dataset: str
    categories: list[str]
    steps: list[PlanStep]

    # Totals, useful for the UI and for feeding the runtime estimator.
    base_attacks_per_model: int = 0
    total_base_attacks: int = 0
    total_prompts: int = 0
    attack_step_count: int = 0

    # A stable fingerprint of the ordered plan; identical inputs always yield an
    # identical key, which is what makes execution reproducible/resumable.
    deterministic_key: str = ""
    notes: list[str] = Field(default_factory=list)

    def compute_key(self) -> str:
        signature = [
            (s.order, s.kind, s.model, s.category, s.base_attacks,
             s.mutation_multiplier, s.passes)
            for s in self.steps
        ]
        blob = json.dumps(
            {"profile": self.profile, "models": self.models, "steps": signature},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]
