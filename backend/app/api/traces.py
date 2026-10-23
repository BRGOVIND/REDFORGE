"""Versioned trace ingestion plus loopback-only desktop trace exploration."""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import secrets
import time
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Project, TraceEvent, TraceToken, TracePrivacyPolicy, GovernanceAuditEvent
from app.observability_privacy import PrivacySettings, audit, cleanup_expired, filter_event, get_policy
from app.network_policy import is_strict

router = APIRouter(tags=["observability"])
MAX_BODY = 128 * 1024
MAX_EVENTS = 50
RATE_PER_MINUTE = 120
_rate: OrderedDict[str, deque[float]] = OrderedDict()
_last_cleanup = 0.0


def _local(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        safe = ipaddress.ip_address(host).is_loopback
    except ValueError:
        safe = host in {"localhost", "testclient"}
    if not safe:
        raise HTTPException(403, "Desktop trace management is available only on loopback")


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    started_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0, le=86_400_000)
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    operation: str | None = Field(default=None, max_length=80)
    route: str | None = Field(default=None, max_length=240)
    status: Literal["success", "error", "cancelled"]
    timed_out: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    usage_source: Literal["provider", "estimated"] | None = None
    finish_reason: str | None = Field(default=None, max_length=100)
    cost_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    cost_source: Literal["provider", "estimated"] | None = None
    error_category: str | None = Field(default=None, max_length=100)
    error_detail: str | None = Field(default=None, max_length=500)
    service: str | None = Field(default=None, max_length=120)
    environment: str | None = Field(default=None, max_length=80)
    application_version: str | None = Field(default=None, max_length=80)
    git_revision: str | None = Field(default=None, max_length=80)
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=128)
    span_id: str | None = Field(default=None, max_length=128)
    parent_span_id: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)
    prompt_template_id: str | None = Field(default=None, max_length=128)
    prompt_version_id: str | None = Field(default=None, max_length=128)
    input_text: str | None = Field(default=None, max_length=4096)
    output_text: str | None = Field(default=None, max_length=4096)
    attributes: dict[str, Any] = Field(default_factory=dict)


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[EventIn] = Field(min_length=1, max_length=MAX_EVENTS)


async def _project_token(authorization: str | None, db: AsyncSession) -> TraceToken:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Project token required", headers={"WWW-Authenticate": "Bearer"})
    raw = authorization[7:]
    if not raw.startswith("rft_") or len(raw) > 200:
        raise HTTPException(401, "Invalid project token")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    token = (await db.execute(select(TraceToken).where(TraceToken.token_hash == digest, TraceToken.revoked_at.is_(None)))).scalar_one_or_none()
    if token is None:
        raise HTTPException(401, "Invalid project token")
    if await db.get(Project, token.project_id) is None:
        raise HTTPException(401, "Invalid project token")
    return token


def _check_rate(token_id: str) -> None:
    now = time.monotonic()
    hits = _rate.setdefault(token_id, deque())
    _rate.move_to_end(token_id)
    while hits and hits[0] <= now - 60:
        hits.popleft()
    if len(hits) >= RATE_PER_MINUTE:
        raise HTTPException(429, "Trace ingestion rate exceeded", headers={"Retry-After": "60"})
    hits.append(now)
    if len(_rate) > 1024:
        _rate.popitem(last=False)


@router.post("/api/projects/{project_id}/trace-tokens", status_code=201)
async def create_token(project_id: str, request: Request, name: str = Query("SDK", max_length=100),
                       tenant_id: str | None = Query(None, max_length=128), db: AsyncSession = Depends(get_db)):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    raw = "rft_" + secrets.token_urlsafe(32)
    row = TraceToken(id=str(uuid.uuid4()), project_id=project_id, tenant_id=tenant_id, name=name,
                     token_hash=hashlib.sha256(raw.encode()).hexdigest(), prefix=raw[:12])
    db.add(row)
    await db.commit()
    return {"id": row.id, "name": name, "tenant_id": tenant_id, "prefix": row.prefix, "token": raw, "created_at": row.created_at}


@router.get("/api/projects/{project_id}/trace-tokens")
async def list_tokens(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    rows = (await db.execute(select(TraceToken).where(TraceToken.project_id == project_id).order_by(TraceToken.created_at.desc()).limit(100))).scalars().all()
    return [{"id": r.id, "name": r.name, "tenant_id": r.tenant_id, "prefix": r.prefix, "created_at": r.created_at, "revoked_at": r.revoked_at} for r in rows]


@router.delete("/api/projects/{project_id}/trace-tokens/{token_id}", status_code=204)
async def revoke_token(project_id: str, token_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    row = (await db.execute(select(TraceToken).where(TraceToken.id == token_id, TraceToken.project_id == project_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Token not found")
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/api/v1/traces/events", status_code=202)
async def ingest(request: Request, authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_db)):
    if is_strict():
        _local(request)
    # Authenticate before parsing the body; no validation oracle for anonymous clients.
    token = await _project_token(authorization, db)
    _check_rate(token.id)
    try:
        content_length = int(request.headers.get("content-length", "0") or "0")
    except ValueError:
        raise HTTPException(400, "Invalid Content-Length") from None
    if content_length > MAX_BODY:
        raise HTTPException(413, "Trace batch too large")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "Trace batch too large")
    try:
        batch = BatchIn.model_validate_json(body)
    except Exception:
        raise HTTPException(422, "Invalid trace batch") from None
    received = datetime.now(timezone.utc)
    accepted = 0
    duplicates = 0
    dropped = 0
    if token.tenant_id and any(e.tenant_id not in {None, token.tenant_id} for e in batch.events):
        raise HTTPException(403, "Token is scoped to another tenant")
    try:
        async with asyncio.timeout(5):
            policy = await get_policy(db, token.project_id)
            for event in batch.events:
                values = event.model_dump(exclude={"attributes"})
                values["project_id"] = token.project_id
                values["tenant_id"] = token.tenant_id or (event.tenant_id if policy.capture_metadata else None)
                values["received_at"] = received
                values["attributes"] = event.attributes
                values = filter_event(values, policy)
                if values is None:
                    dropped += 1
                    continue
                if event.request_id:
                    values["logical_call_key"] = hashlib.sha256(
                        f"{token.project_id}\0{event.request_id}".encode()).hexdigest()
                # Stable sampling preserves idempotency on retried batches.
                if int(hashlib.sha256(event.event_id.encode()).hexdigest()[:8], 16) / 0xffffffff >= policy.sample_rate:
                    dropped += 1
                    continue
                from app.cost_control import apply_price
                await apply_price(db, values)
                result = await db.execute(insert(TraceEvent).values(**values).prefix_with("OR IGNORE"))
                accepted += result.rowcount or 0
                duplicates += 0 if result.rowcount else 1
            await db.commit()
    except TimeoutError:
        await db.rollback()
        raise HTTPException(503, "Trace persistence timed out") from None
    global _last_cleanup
    if time.monotonic() - _last_cleanup > 3600:
        _last_cleanup = time.monotonic()
        try:
            await cleanup_expired(db, batch_size=200)
        except Exception:
            await db.rollback()
    return {"accepted": accepted, "duplicates": duplicates, "dropped": dropped}


@router.get("/api/projects/{project_id}/trace-privacy", response_model=PrivacySettings)
async def read_privacy(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    return await get_policy(db, project_id)


@router.put("/api/projects/{project_id}/trace-privacy", response_model=PrivacySettings)
async def update_privacy(project_id: str, policy: PrivacySettings, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    row = await db.get(TracePrivacyPolicy, project_id)
    if row is None:
        row = TracePrivacyPolicy(project_id=project_id, settings=policy.model_dump())
        db.add(row)
    else:
        row.settings = policy.model_dump()
    audit(db, project_id, "trace_privacy.changed", details={"capture_input": policy.capture_input,
        "capture_output": policy.capture_output, "capture_metadata": policy.capture_metadata,
        "capture_errors": policy.capture_errors, "retention_days": policy.retention_days})
    await db.commit()
    return policy


@router.post("/api/projects/{project_id}/traces/retention-cleanup")
async def run_retention(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    removed = await cleanup_expired(db, batch_size=200)
    audit(db, project_id, "trace_retention.cleanup", details={"removed": removed})
    await db.commit()
    return {"removed": removed, "batch_limit": 200}


@router.get("/api/projects/{project_id}/governance-audit")
async def list_audit(project_id: str, request: Request, limit: int = Query(50, ge=1, le=100),
                     before_id: int | None = Query(None, ge=1), db: AsyncSession = Depends(get_db)):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    stmt = select(GovernanceAuditEvent).where(GovernanceAuditEvent.project_id == project_id)
    if before_id:
        stmt = stmt.where(GovernanceAuditEvent.id < before_id)
    rows = (await db.execute(stmt.order_by(GovernanceAuditEvent.id.desc()).limit(limit + 1))).scalars().all()
    return {"items": [{"id": r.id, "action": r.action, "resource_id": r.resource_id,
        "actor": r.actor, "details": r.details, "created_at": r.created_at} for r in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


def _summary(row: TraceEvent) -> dict[str, Any]:
    return {k: getattr(row, k) for k in (
        "event_id", "received_at", "started_at", "duration_ms", "provider", "model", "operation", "route", "status", "timed_out",
        "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens",
        "usage_source", "finish_reason", "cost_usd", "cost_source", "pricing_record_id",
        "cost_calculated_at", "error_category",
        "service", "environment", "request_id", "trace_id", "span_id", "parent_span_id", "conversation_id", "tenant_id",
    )}


@router.get("/api/projects/{project_id}/traces")
async def list_traces(
    project_id: str, request: Request, db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100), before_id: int | None = Query(None, ge=1), after_id: int | None = Query(None, ge=1),
    after: datetime | None = None, before: datetime | None = None,
    provider: str | None = None, model: str | None = None, status: str | None = None,
    service: str | None = None, environment: str | None = None, route: str | None = None,
    tenant_id: str | None = None, trace_id: str | None = None, conversation_id: str | None = None,
):
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    conditions = [TraceEvent.project_id == project_id]
    grouping = bool(trace_id or conversation_id)
    if grouping and after_id is not None:
        conditions.append(TraceEvent.id > after_id)
    elif not grouping and before_id is not None:
        conditions.append(TraceEvent.id < before_id)
    if after is not None:
        conditions.append(TraceEvent.received_at >= after)
    if before is not None:
        conditions.append(TraceEvent.received_at <= before)
    for key, value in {"provider": provider, "model": model, "status": status, "service": service, "environment": environment,
                       "route": route, "tenant_id": tenant_id, "trace_id": trace_id, "conversation_id": conversation_id}.items():
        if value:
            conditions.append(getattr(TraceEvent, key) == value[:240])
    ordering = TraceEvent.id.asc() if grouping else TraceEvent.id.desc()
    rows = (await db.execute(select(TraceEvent).where(and_(*conditions)).order_by(ordering).limit(limit + 1))).scalars().all()
    page = rows[:limit]
    return {"items": [{**_summary(r), "cursor": r.id} for r in page], "next_cursor": page[-1].id if len(rows) > limit else None}


@router.get("/api/projects/{project_id}/traces/{event_id}")
async def trace_detail(project_id: str, event_id: str, request: Request, db: AsyncSession = Depends(get_db),
                       include_bodies: bool = False, x_redforge_sensitive_access: str | None = Header(default=None)):
    _local(request)
    row = (await db.execute(select(TraceEvent).where(TraceEvent.project_id == project_id, TraceEvent.event_id == event_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Trace event not found")
    if include_bodies and x_redforge_sensitive_access != "allow":
        raise HTTPException(403, "Explicit sensitive-data access header required")
    if include_bodies:
        audit(db, project_id, "trace.sensitive_read", event_id)
        await db.commit()
    return {**_summary(row), "error_detail": row.error_detail if include_bodies else None,
            "input_text": row.input_text if include_bodies else None, "output_text": row.output_text if include_bodies else None,
            "attributes": row.attributes, "application_version": row.application_version, "git_revision": row.git_revision,
            "user_id": row.user_id, "prompt_template_id": row.prompt_template_id, "prompt_version_id": row.prompt_version_id}
