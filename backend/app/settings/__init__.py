"""Settings system (RedForge V3) — a data-driven, persisted, categorized settings
layer overlaying the env-based ``app.config``. Additive; nothing else depends on it."""
from __future__ import annotations

from app.settings import schema
from app.settings.service import SettingsService, SettingsValidationError, settings_service

__all__ = ["schema", "SettingsService", "SettingsValidationError", "settings_service"]
