"""First-run onboarding services (hardware-aware recommendations).

Pure orchestration over existing detection: resources come from
``resources.resource_monitor``, provider status from the Runtime Manager
(``runtime.management``), and model sizing from ``runtime.model_sizes``. No
detection logic is duplicated here.
"""
from app.onboarding.recommender import build_recommendations

__all__ = ["build_recommendations"]
