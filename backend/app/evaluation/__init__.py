"""Evaluation Workbench (RedForge V2 Phase 4).

The qualitative evaluation layer — prompt engineering, regression testing,
response comparison, and model validation. Complements Benchmark Center
("how well does the model perform?") by answering "how does it behave?".

Additive and local-only; reuses the Runtime Manager, the async queue
architecture, Projects, the Runtime Registry, Reports, and the Assistant.
"""
from app.evaluation.comparator import GoldenResponseComparator, golden_comparator
from app.evaluation.regression import REGRESSION_TYPES, RegressionAnalyzer, regression_analyzer
from app.evaluation.service import (
    EvaluationSessionService,
    EvaluationWorkbenchService,
    compose_summary,
    evaluation_sessions,
    evaluation_workbench,
)
from app.evaluation.similarity import (
    DEFAULT_SIMILARITY,
    SimilarityProvider,
    get_similarity,
    list_similarity,
)
from app.evaluation.versioning import PromptVersionService, prompt_version_service

__all__ = [
    "GoldenResponseComparator", "golden_comparator",
    "REGRESSION_TYPES", "RegressionAnalyzer", "regression_analyzer",
    "EvaluationSessionService", "EvaluationWorkbenchService",
    "compose_summary", "evaluation_sessions", "evaluation_workbench",
    "DEFAULT_SIMILARITY", "SimilarityProvider", "get_similarity", "list_similarity",
    "PromptVersionService", "prompt_version_service",
]
