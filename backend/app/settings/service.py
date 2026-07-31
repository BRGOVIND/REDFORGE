"""Settings service — persists overrides and resolves effective values.

Effective value = stored override (if any) else the schema default. Secrets are never
returned in the clear (masked as ``"********"`` when set). Writes are validated against
the schema (type, range, enum). DB-backed via the additive ``app_settings`` table.
"""
from __future__ import annotations

from typing import Any, Optional

from app.settings import schema


class SettingsService:
    """Settings are **authoritative**: anything shown in the UI must affect runtime.

    Consumers are not all async — providers and Job handlers read settings from
    worker threads where awaiting a DB session is impossible. So every read
    refreshes an in-memory snapshot, writes update it, and :meth:`get_sync`
    serves sync callers from it. The snapshot is warmed at startup
    (``app.main`` lifespan) so it is populated before the first request.
    """

    def __init__(self, session_factory=None) -> None:
        self._factory = session_factory
        self._snapshot: Optional[dict] = None

    def _sf(self):
        if self._factory is not None:
            return self._factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    # -- sync access for non-async consumers ---------------------------------

    def get_sync(self, key: str) -> Any:
        """Effective value without awaiting. Falls back to the schema default
        until the snapshot is warmed, so it is always safe to call."""
        s = schema.get_def(key)
        if s is None:
            return None
        if self._snapshot is not None and key in self._snapshot:
            return self._snapshot[key]
        return s.default

    async def warm(self) -> dict:
        """Populate the snapshot. Called once at startup; never raises."""
        try:
            return await self.effective(reveal_secrets=True)
        except Exception:  # noqa: BLE001 - a settings failure must not block boot
            self._snapshot = dict(schema.defaults())
            return self._snapshot

    # -- reads ---------------------------------------------------------------

    async def _overrides(self) -> dict:
        from sqlalchemy import select
        from app.db.models import AppSettingRecord
        async with self._sf()() as db:
            rows = (await db.execute(select(AppSettingRecord))).scalars().all()
        return {r.key: r.value for r in rows}

    async def effective(self, *, reveal_secrets: bool = False) -> dict:
        """Every setting's effective value (override or default), secrets masked."""
        ov = await self._overrides()
        out = {}
        snapshot = {}
        for s in schema.SCHEMA:
            val = ov.get(s.key, s.default)
            # The snapshot always holds real values; masking is a view concern.
            snapshot[s.key] = val
            if s.type == "secret" and not reveal_secrets:
                val = "********" if (ov.get(s.key)) else ""
            out[s.key] = val
        self._snapshot = snapshot
        return out

    async def grouped(self) -> dict:
        """Schema + effective values grouped by category — drives the Settings UI."""
        eff = await self.effective()
        ov = await self._overrides()
        cats = []
        for key, label, blurb in schema.CATEGORIES:
            items = []
            for s in schema.SCHEMA:
                if s.category != key:
                    continue
                items.append({
                    **s.to_dict(),
                    "value": eff[s.key],
                    "is_overridden": s.key in ov,
                    "is_set": bool(ov.get(s.key)) if s.type == "secret" else s.key in ov,
                })
            if items:
                cats.append({"key": key, "label": label, "description": blurb, "settings": items})
        return {"categories": cats}

    async def get(self, key: str, *, reveal_secrets: bool = False) -> Any:
        s = schema.get_def(key)
        if s is None:
            return None
        ov = await self._overrides()
        val = ov.get(key, s.default)
        if s.type == "secret" and not reveal_secrets:
            return "********" if ov.get(key) else ""
        return val

    # -- writes --------------------------------------------------------------

    def _coerce(self, s: schema.Setting, value: Any) -> Any:
        if s.type == "bool":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if s.type == "int":
            v = int(value)
            if s.min is not None:
                v = max(int(s.min), v)
            if s.max is not None:
                v = min(int(s.max), v)
            return v
        if s.type == "float":
            v = float(value)
            if s.min is not None:
                v = max(s.min, v)
            if s.max is not None:
                v = min(s.max, v)
            return v
        if s.type == "enum":
            sval = str(value)
            if s.options and sval not in s.options:
                raise ValueError(f"'{sval}' is not a valid option for {s.key}")
            return sval
        return str(value)

    async def set_many(self, values: dict) -> dict:
        """Validate + persist overrides. Returns the new grouped view."""
        from app.db.models import AppSettingRecord
        errors: dict[str, str] = {}
        clean: dict[str, Any] = {}
        for key, raw in (values or {}).items():
            s = schema.get_def(key)
            if s is None:
                errors[key] = "unknown setting"
                continue
            # A masked secret sent back unchanged means "leave it" — skip.
            if s.type == "secret" and raw == "********":
                continue
            try:
                clean[key] = self._coerce(s, raw)
            except (ValueError, TypeError) as exc:
                errors[key] = str(exc)
        if errors:
            raise SettingsValidationError(errors)

        async with self._sf()() as db:
            for key, val in clean.items():
                row = await db.get(AppSettingRecord, key)
                if row is None:
                    db.add(AppSettingRecord(key=key, value=val))
                else:
                    row.value = val
            await db.commit()
        return await self.grouped()

    async def reset(self, key: Optional[str] = None) -> dict:
        """Reset one key (or all) to defaults by removing overrides."""
        from sqlalchemy import delete
        from app.db.models import AppSettingRecord
        async with self._sf()() as db:
            if key is None:
                await db.execute(delete(AppSettingRecord))
            else:
                await db.execute(delete(AppSettingRecord).where(AppSettingRecord.key == key))
            await db.commit()
        return await self.grouped()


class SettingsValidationError(Exception):
    def __init__(self, errors: dict) -> None:
        super().__init__("invalid settings")
        self.errors = errors


settings_service = SettingsService()
