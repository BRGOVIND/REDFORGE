"""Settings API — read the categorized schema+values, update, and reset.

Every failure is specific (per-key validation errors), never a generic message.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.settings import settings_service
from app.settings.service import SettingsValidationError

router = APIRouter(prefix="/api/settings", tags=["settings"])


class UpdateRequest(BaseModel):
    values: dict


@router.get("")
async def get_settings() -> dict:
    """All settings grouped by category, with effective values (secrets masked)."""
    return await settings_service.grouped()


@router.put("")
async def update_settings(req: UpdateRequest) -> dict:
    """Persist one or more setting overrides. Returns the updated grouped view."""
    try:
        return await settings_service.set_many(req.values)
    except SettingsValidationError as exc:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_settings",
            "message": "Some settings could not be saved.",
            "fields": exc.errors,
        })


@router.post("/reset")
async def reset_settings(key: Optional[str] = None) -> dict:
    """Reset a single setting (``?key=``) or all settings to their defaults."""
    return await settings_service.reset(key)
