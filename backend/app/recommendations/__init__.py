"""Recommendation Engine (RedForge V2, Phase 2.4).

Turns a detected model weakness into concrete guidance: training strategy,
hyperparameters, dataset suggestions, extra attacks, and an improvement estimate.

Isolated and non-duplicative — it *reads* existing local metadata (Continuous
Security results, training config, dataset quality) and produces advice; it never
runs an evaluation or a training job itself. It only suggests; nothing is
downloaded or launched automatically. Predictions are heuristic estimates.
"""
from app.recommendations.service import RecommendationService, recommendation_service

__all__ = ["RecommendationService", "recommendation_service"]
