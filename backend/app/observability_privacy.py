"""Server-side, fail-closed trace capture policy and bounded retention."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select

from app.db.models import GovernanceAuditEvent, TraceEvent, TracePrivacyPolicy

_PRIVATE_KEY = re.compile(r"(?i)(auth|pass(word)?|secret|token|cookie|credential|api[_-]?key|private[_-]?key)")
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+|sk-[a-z0-9_-]{8,}|(?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;\"']+"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    r"|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
)


class PrivacySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry_enabled: bool = True
    capture_input: bool = False
    capture_output: bool = False
    capture_metadata: bool = False
    capture_errors: bool = False
    metadata_allowlist: list[str] = Field(default_factory=list, max_length=32)
    metadata_denylist: list[str] = Field(default_factory=list, max_length=64)
    redact_keys: list[str] = Field(default_factory=list, max_length=64)
    max_payload_bytes: int = Field(default=2048, ge=64, le=4096)
    sample_rate: float = Field(default=1, ge=0, le=1)
    retention_days: int = Field(default=30, ge=1, le=365)

    @field_validator("metadata_allowlist", "metadata_denylist", "redact_keys")
    @classmethod
    def valid_keys(cls, value: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", x) for x in value):
            raise ValueError("Keys must be simple field names up to 64 characters")
        return sorted(set(value))

    @model_validator(mode="after")
    def no_private_allowlist(self):
        if any(_PRIVATE_KEY.search(x) for x in self.metadata_allowlist):
            raise ValueError("Sensitive keys cannot be allowlisted")
        return self


def _scrub(value: Any, limit: int, *, depth: int = 0, keys: set[str] | None = None) -> Any:
    """Only small JSON-like values survive; unexpected types fail closed."""
    if depth > 4:
        return "[REDACTED]"
    if isinstance(value, str):
        cleaned = _SECRET_VALUE.sub("[REDACTED]", value[:limit])
        return cleaned.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [_scrub(x, limit, depth=depth + 1, keys=keys) for x in value[:16]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:32]:
            if not isinstance(key, str):
                continue
            if _PRIVATE_KEY.search(key) or key.lower() in (keys or set()):
                continue
            out[key[:64]] = _scrub(item, limit, depth=depth + 1, keys=keys)
        return out
    raise ValueError("Unsupported sensitive payload")


def _scrub_metadata(value: Any, limit: int, path: str, allowed: set[str], denied: set[str], depth: int = 0) -> Any:
    """Nested metadata needs an explicit dotted allowlist entry per leaf."""
    if depth > 4:
        return None
    if isinstance(value, dict):
        return {key: _scrub_metadata(item, limit, f"{path}.{key}", allowed, denied, depth + 1)
                for key, item in list(value.items())[:32]
                if isinstance(key, str) and not _PRIVATE_KEY.search(key)
                and f"{path}.{key}" not in denied
                and any(name == f"{path}.{key}" or name.startswith(f"{path}.{key}.") for name in allowed)}
    if path not in allowed:
        return None
    if isinstance(value, list):
        return [_scrub(item, limit, depth=depth + 1, keys=denied) for item in value[:16]
                if not isinstance(item, (dict, list))]
    return _scrub(value, limit, depth=depth, keys=denied)


def filter_event(event: dict[str, Any], policy: PrivacySettings) -> dict[str, Any] | None:
    """Apply project policy even when an SDK or caller sends forbidden bodies."""
    if not policy.telemetry_enabled:
        return None
    try:
        out = dict(event)
        out["input_text"] = _scrub(event.get("input_text"), policy.max_payload_bytes) if policy.capture_input else None
        out["output_text"] = _scrub(event.get("output_text"), policy.max_payload_bytes) if policy.capture_output else None
        out["error_detail"] = _scrub(event.get("error_detail"), min(policy.max_payload_bytes, 500)) if policy.capture_errors else None
        out["error_category"] = _scrub(event.get("error_category"), 100) if policy.capture_errors else None
        if policy.capture_metadata:
            allowed = set(policy.metadata_allowlist) - set(policy.metadata_denylist)
            attrs = event.get("attributes") or {}
            if not isinstance(attrs, dict):
                raise ValueError("Invalid metadata")
            out["attributes"] = {
                key: _scrub_metadata(value, min(policy.max_payload_bytes, 256), key,
                    allowed, set(policy.redact_keys) | set(policy.metadata_denylist))
                for key, value in list(attrs.items())[:32]
                if isinstance(key, str) and not _PRIVATE_KEY.search(key)
                and any(name == key or name.startswith(key + ".") for name in allowed)
            }
            if len(json.dumps(out["attributes"], ensure_ascii=False).encode("utf-8")) > policy.max_payload_bytes:
                out["attributes"] = {}
            for key in ("user_id", "conversation_id", "request_id", "route", "service", "environment", "git_revision"):
                out[key] = _scrub(event.get(key), 256)
        else:
            out["attributes"] = {}
            for key in ("user_id", "conversation_id", "request_id", "route", "service", "environment", "git_revision"):
                out[key] = None
        # Even structured labels supplied by an untrusted client are scrubbed.
        for key in ("provider", "model", "operation", "finish_reason", "application_version", "trace_id", "span_id", "parent_span_id", "prompt_template_id", "prompt_version_id"):
            out[key] = _scrub(event.get(key), 256)
        return out
    except Exception:
        # A redaction error must not turn into unfiltered persistence.
        return None


async def get_policy(db, project_id: str) -> PrivacySettings:
    row = await db.get(TracePrivacyPolicy, project_id)
    try:
        return PrivacySettings.model_validate(row.settings) if row else PrivacySettings()
    except Exception:
        return PrivacySettings(telemetry_enabled=False)


def audit(db, project_id: str, action: str, resource_id: str | None = None, *, details: dict | None = None, actor: str = "local-operator") -> None:
    db.add(GovernanceAuditEvent(project_id=project_id, action=action, resource_id=resource_id, actor=actor, details=details or {}))


async def cleanup_expired(db, *, batch_size: int = 200) -> int:
    """One indexed, bounded pass; safe to call at startup and periodically on ingest."""
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be 1..500")
    now = datetime.now(timezone.utc)
    global _cleanup_cursor
    stmt = select(TracePrivacyPolicy).order_by(TracePrivacyPolicy.project_id).limit(min(batch_size, 50))
    policies = (await db.execute(stmt.where(TracePrivacyPolicy.project_id > _cleanup_cursor))).scalars().all()
    if not policies:
        _cleanup_cursor = ""
        policies = (await db.execute(stmt)).scalars().all()
    if policies:
        _cleanup_cursor = policies[-1].project_id
    removed = 0
    for row in policies:
        if removed >= batch_size:
            break
        policy = await get_policy(db, row.project_id)
        cutoff = now - timedelta(days=policy.retention_days)
        ids = (await db.execute(select(TraceEvent.id).where(
            TraceEvent.project_id == row.project_id, TraceEvent.received_at < cutoff
        ).order_by(TraceEvent.received_at, TraceEvent.id).limit(batch_size - removed))).scalars().all()
        if ids:
            await db.execute(delete(TraceEvent).where(TraceEvent.id.in_(ids)))
            removed += len(ids)
    # Projects without an explicit policy still get the conservative default.
    if removed < batch_size:
        cutoff = now - timedelta(days=PrivacySettings().retention_days)
        ids = (await db.execute(select(TraceEvent.id).where(
            TraceEvent.received_at < cutoff,
            ~TraceEvent.project_id.in_(select(TracePrivacyPolicy.project_id))
        ).order_by(TraceEvent.received_at, TraceEvent.id).limit(batch_size - removed))).scalars().all()
        if ids:
            await db.execute(delete(TraceEvent).where(TraceEvent.id.in_(ids)))
            removed += len(ids)
    if removed:
        await db.commit()
    return removed


_cleanup_cursor = ""
