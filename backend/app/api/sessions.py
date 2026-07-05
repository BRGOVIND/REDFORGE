"""HTTP API for durable evaluation sessions.

Every endpoint is backed by the persistent session store, so a session created
here is immediately retrievable and survives a backend restart. Long-running
execution is scheduled as a background task; all of its state lands in the
database, never in process memory.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.database import AsyncSessionLocal
from app.db.models import EvaluationEvent, EvaluationSession
from app.sessions.constants import SessionType
from app.sessions.session_manager import SessionManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

# A single manager bound to the app's real session factory. Tests override this
# dependency to inject a manager backed by an isolated test database.
_default_manager = SessionManager(AsyncSessionLocal)


def get_session_manager() -> SessionManager:
    return _default_manager


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    session_type: str = SessionType.BATCH
    selected_models: list[str] = Field(default_factory=list)
    selected_categories: list[str] = Field(default_factory=list)
    selected_tier: Optional[str] = None
    metadata: Optional[dict] = None
    # When true (default), execution starts immediately in the background.
    auto_start: bool = True


class SessionResponse(BaseModel):
    id: str
    session_type: str
    status: str
    selected_models: list[str]
    selected_categories: list[str]
    selected_tier: Optional[str]
    total_tasks: int
    completed_tasks: int
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_seconds: Optional[float]
    actual_seconds: Optional[float]
    metadata: Optional[dict]


class EventResponse(BaseModel):
    id: int
    session_id: str
    timestamp: Optional[datetime]
    event_type: str
    model_name: Optional[str]
    category: Optional[str]
    attack_name: Optional[str]
    response_excerpt: Optional[str]
    verdict: Optional[str]
    latency_ms: Optional[int]
    metadata: Optional[dict]


def _to_session_response(session: EvaluationSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        session_type=session.session_type,
        status=session.status,
        selected_models=session.selected_models or [],
        selected_categories=session.selected_categories or [],
        selected_tier=session.selected_tier,
        total_tasks=session.total_tasks or 0,
        completed_tasks=session.completed_tasks or 0,
        created_at=session.created_at,
        started_at=session.started_at,
        completed_at=session.completed_at,
        estimated_seconds=session.estimated_seconds,
        actual_seconds=session.actual_seconds,
        metadata=session.session_metadata,
    )


def _to_event_response(event: EvaluationEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        session_id=event.session_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        model_name=event.model_name,
        category=event.category,
        attack_name=event.attack_name,
        response_excerpt=event.response_excerpt,
        verdict=event.verdict,
        latency_ms=event.latency_ms,
        metadata=event.event_metadata,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=SessionResponse)
async def create_session(
    req: SessionCreateRequest,
    background_tasks: BackgroundTasks,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    session = await manager.create_session(
        session_type=req.session_type,
        selected_models=req.selected_models,
        selected_categories=req.selected_categories,
        selected_tier=req.selected_tier,
        metadata=req.metadata,
    )
    # The session is already durably persisted at this point, so a client that
    # polls GET /{id} immediately will never see a 404.
    if req.auto_start:
        background_tasks.add_task(manager.run_session, session.id)
    return _to_session_response(session)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    status: Optional[str] = None,
    session_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    manager: SessionManager = Depends(get_session_manager),
) -> list[SessionResponse]:
    sessions = await manager.list_sessions(
        status=status, session_type=session_type, limit=limit
    )
    return [_to_session_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _to_session_response(session)


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    # Resume runs in the background so this request returns promptly.
    background_tasks.add_task(manager.resume_session, session_id)
    return _to_session_response(session)


@router.post("/{session_id}/pause", response_model=SessionResponse)
async def pause_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    session = await manager.pause_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _to_session_response(session)


@router.post("/{session_id}/cancel", response_model=SessionResponse)
async def cancel_session(
    session_id: str,
    manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    session = await manager.cancel_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _to_session_response(session)


@router.get("/{session_id}/events", response_model=list[EventResponse])
async def list_session_events(
    session_id: str,
    after_id: Optional[int] = None,
    event_type: Optional[str] = None,
    manager: SessionManager = Depends(get_session_manager),
) -> list[EventResponse]:
    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    events = await manager.get_events(
        session_id, after_id=after_id, event_type=event_type
    )
    return [_to_event_response(e) for e in events]
