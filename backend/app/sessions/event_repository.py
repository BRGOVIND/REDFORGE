"""Append-only persistence for evaluation events.

Events are never mutated after creation. They form the durable backbone that a
future WebSocket feed will replay (catch-up) and stream (live). Because they are
persisted, a client can reconnect after a refresh or backend restart and
reconstruct the full history of a session by querying this table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvaluationEvent
from app.sessions.constants import RESPONSE_EXCERPT_LEN


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(
        self,
        *,
        session_id: str,
        event_type: str,
        model_name: Optional[str] = None,
        category: Optional[str] = None,
        attack_name: Optional[str] = None,
        response_excerpt: Optional[str] = None,
        verdict: Optional[str] = None,
        latency_ms: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> EvaluationEvent:
        if response_excerpt is not None and len(response_excerpt) > RESPONSE_EXCERPT_LEN:
            response_excerpt = response_excerpt[:RESPONSE_EXCERPT_LEN]

        event = EvaluationEvent(
            session_id=session_id,
            timestamp=_utcnow(),
            event_type=event_type,
            model_name=model_name,
            category=category,
            attack_name=attack_name,
            response_excerpt=response_excerpt,
            verdict=verdict,
            latency_ms=latency_ms,
            event_metadata=metadata,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_for_session(
        self,
        session_id: str,
        *,
        after_id: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[EvaluationEvent]:
        """Return a session's events in creation order.

        ``after_id`` supports the future WebSocket catch-up pattern: a client
        that already has events up to ``N`` can request only what came later.
        """
        query = (
            select(EvaluationEvent)
            .where(EvaluationEvent.session_id == session_id)
            .order_by(EvaluationEvent.id.asc())
        )
        if after_id is not None:
            query = query.where(EvaluationEvent.id > after_id)
        if event_type is not None:
            query = query.where(EvaluationEvent.event_type == event_type)
        if limit is not None:
            query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())
