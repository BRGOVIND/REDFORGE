"""Data-driven evaluation profiles.

Users pick a profile (Quick Scan, Standard, Thorough, Comparative, Exhaustive)
instead of hand-selecting attacks. The profile declares the dataset, categories,
attack counts, mutation, evaluator, and checkpoint/retry/timeout policy that the
scheduler expands into a concrete execution plan.
"""
from app.evaluation_profiles.profile import (
    ALL_CATEGORIES,
    CheckpointConfig,
    EvaluationProfile,
    MutationConfig,
    RetryConfig,
)
from app.evaluation_profiles.profile_loader import ProfileLoadError, load_profiles
from app.evaluation_profiles import profile_registry

__all__ = [
    "ALL_CATEGORIES",
    "CheckpointConfig",
    "EvaluationProfile",
    "MutationConfig",
    "RetryConfig",
    "ProfileLoadError",
    "load_profiles",
    "profile_registry",
]
