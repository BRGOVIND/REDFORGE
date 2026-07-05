"""Durable persistence primitives for evaluation sessions.

Every method here reads or writes the ``evaluation_sessions`` table through an
``AsyncSession``. Nothing is kept in memory, so state survives a backend
restart. The repository owns commits for the writes it performs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvaluationSession
from app.sessions.constants import SessionStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        session_type: str,
        selected_models: list[str],
        selected_categories: list[str],
        selected_tier: Optional[str] = None,
        total_tasks: int = 0,
        estimated_seconds: Optional[float] = None,
        metadata: Optional[dict] = None,
        status: str = SessionStatus.PENDING,
    ) -> EvaluationSession:
        session = EvaluationSession(
            id=str(uuid4()),
            session_type=session_type,
            status=status,
            selected_models=list(selected_models),
            selected_categories=list(selected_categories),
            selected_tier=selected_tier,
            total_tasks=total_tasks,
            completed_tasks=0,
            created_at=_utcnow(),
            estimated_seconds=estimated_seconds,
            session_metadata=metadata,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get(self, session_id: str) -> Optional[EvaluationSession]:
        result = await self.db.execute(
            select(EvaluationSession).where(EvaluationSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        status: Optional[str] = None,
        session_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[EvaluationSession]:
        query = select(EvaluationSession).order_by(EvaluationSession.created_at.desc())
        if status is not None:
            query = query.where(EvaluationSession.status == status)
        if session_type is not None:
            query = query.where(EvaluationSession.session_type == session_type)
        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_running(self, session: EvaluationSession) -> EvaluationSession:
        session.status = SessionStatus.RUNNING
        if session.started_at is None:
            session.started_at = _utcnow()
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def set_status(
        self, session: EvaluationSession, status: str
    ) -> EvaluationSession:
        session.status = status
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def increment_completed(
        self, session: EvaluationSession, amount: int = 1
    ) -> EvaluationSession:
        session.completed_tasks = (session.completed_tasks or 0) + amount
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def mark_completed(self, session: EvaluationSession) -> EvaluationSession:
        session.status = SessionStatus.COMPLETED
        session.completed_at = _utcnow()
        session.actual_seconds = self._elapsed_seconds(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def mark_failed(
        self, session: EvaluationSession, error: Optional[str] = None
    ) -> EvaluationSession:
        session.status = SessionStatus.FAILED
        session.completed_at = _utcnow()
        session.actual_seconds = self._elapsed_seconds(session)
        if error is not None:
            meta = dict(session.session_metadata or {})
            meta["error"] = error
            session.session_metadata = meta
        await self.db.commit()
        await self.db.refresh(session)
        return session

    @staticmethod
    def _elapsed_seconds(session: EvaluationSession) -> Optional[float]:
        if session.started_at is None:
            return None
        started = session.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return (_utcnow() - started).total_seconds()
