"""Model Hub (RedForge V3) — browse + one-click-download curated models from inside
RedForge (no terminal). Downloads run as Jobs, so they appear in the Global Task
Manager and post-download register a Foundation Model / runtime automatically."""
from __future__ import annotations

from app.model_hub import catalog
from app.model_hub.download import register_model_hub_handlers
from app.model_hub.service import ModelHubService, model_hub_service

__all__ = ["catalog", "ModelHubService", "model_hub_service", "register_model_hub_handlers"]
