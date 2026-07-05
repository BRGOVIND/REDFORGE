"""Data-driven evaluation profile schema.

A profile is a *declarative* description of an evaluation: which dataset and
categories to use, how many attacks, whether to mutate them, which evaluator to
score with, and the checkpoint/retry/timeout policy. Profiles are authored as
JSON (see ``data/*.json``) and validated into these Pydantic models, so the
execution engine is entirely data-driven — no evaluation logic is hardcoded per
profile.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Sentinel usable in a profile's ``categories`` list to mean "every category
# available in the chosen dataset".
ALL_CATEGORIES = "all"

DatasetSource = Literal["attack_library", "benchmark_sample", "full_benchmark"]
EvaluatorKind = Literal["heuristic", "llm_judge"]
MutationMode = Literal["none", "static", "adaptive"]


class MutationConfig(BaseModel):
    model_config = {"extra": "forbid"}

    enabled: bool = False
    # Number of mutated variants generated per base attack.
    count: int = Field(default=0, ge=0, le=50)
    mode: MutationMode = "none"

    @model_validator(mode="after")
    def _coherent(self) -> "MutationConfig":
        if self.enabled and self.mode == "none":
            self.mode = "static"
        if not self.enabled:
            self.count = 0
            self.mode = "none"
        return self


class CheckpointConfig(BaseModel):
    model_config = {"extra": "forbid"}

    enabled: bool = True
    # Persist a checkpoint after every N completed tasks.
    frequency: int = Field(default=1, ge=1, le=1000)


class RetryConfig(BaseModel):
    model_config = {"extra": "forbid"}

    enabled: bool = False
    max_retries: int = Field(default=0, ge=0, le=10)
    # Which outcomes trigger a retry. "ERROR" = inference/transport failure.
    retry_on: list[str] = Field(default_factory=lambda: ["ERROR"])

    @model_validator(mode="after")
    def _coherent(self) -> "RetryConfig":
        if not self.enabled:
            self.max_retries = 0
        elif self.max_retries == 0:
            self.max_retries = 1
        return self


class EvaluationProfile(BaseModel):
    """A named, validated evaluation configuration."""

    model_config = {"extra": "forbid"}

    name: str = Field(pattern=r"^[a-z0-9_]+$")
    display_name: str
    description: str
    purpose: str

    dataset: DatasetSource
    categories: list[str] = Field(default_factory=lambda: [ALL_CATEGORIES])
    # Cap of base attacks per category (None = use everything available).
    attacks_per_category: Optional[int] = Field(default=None, ge=1)
    # For benchmark_sample: how many cases to sample (None = all in category).
    benchmark_sample_size: Optional[int] = Field(default=None, ge=1)

    evaluator: EvaluatorKind = "heuristic"
    judge_model: Optional[str] = None

    mutation: MutationConfig = Field(default_factory=MutationConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)

    timeout_seconds: int = Field(default=1800, ge=1)
    # Number of full passes over the attack set (Thorough runs several).
    passes: int = Field(default=1, ge=1, le=10)

    multi_model: bool = False
    adaptive_agent: bool = False
    generate_leaderboard: bool = False
    generate_report: bool = False

    estimated_runtime_hint: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "EvaluationProfile":
        if self.evaluator == "llm_judge" and not self.judge_model:
            raise ValueError(
                f"profile '{self.name}': evaluator 'llm_judge' requires a judge_model"
            )
        if not self.categories:
            raise ValueError(f"profile '{self.name}': categories cannot be empty")
        if ALL_CATEGORIES in self.categories and len(self.categories) > 1:
            raise ValueError(
                f"profile '{self.name}': '{ALL_CATEGORIES}' cannot be combined with "
                "specific categories"
            )
        return self

    @property
    def uses_all_categories(self) -> bool:
        return self.categories == [ALL_CATEGORIES]

    @property
    def mutation_multiplier(self) -> int:
        """How many prompts one base attack expands into (base + variants)."""
        return 1 + (self.mutation.count if self.mutation.enabled else 0)
