"""Persistent, resumable evaluation sessions.

This package turns RedForge's evaluation runs into durable, session-based work
that survives browser refresh, backend restart, and interruption. It also emits
an append-only event stream that a future WebSocket feed will consume.
"""
from app.sessions.constants import EventType, SessionStatus, SessionType
from app.sessions.event_repository import EventRepository
from app.sessions.session_manager import SessionManager
from app.sessions.session_repository import SessionRepository

__all__ = [
    "EventType",
    "SessionStatus",
    "SessionType",
    "EventRepository",
    "SessionManager",
    "SessionRepository",
]
