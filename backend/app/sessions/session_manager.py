"""Orchestrates the durable evaluation session lifecycle.

The manager is deliberately built around a *session factory* (an
``async_sessionmaker``) rather than a single request-scoped session: it opens a
short-lived database session for each unit of work so that progress and events
are committed continuously. That is what lets a session survive a backend
restart and be resumed exactly where it left off.

No execution state is ever held only in memory. The database is the single
source of truth; this class merely reads it, advances it, and writes it back.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import select

from app.db.models import Attack, EvaluationSession, TestRun
from app.evaluators.scoring import score_response
from app.sessions.constants import (
    AVG_TASK_SECONDS,
    EventType,
    SessionStatus,
)
from app.sessions.event_repository import EventRepository
from app.sessions.session_repository import SessionRepository

# (model_name, prompt) -> (response_text, latency_ms)
GenerateFn = Callable[[str, str], Awaitable[tuple[str, int]]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionManager:
    def __init__(self, session_factory, generate_fn: Optional[GenerateFn] = None) -> None:
        """``session_factory`` is a callable returning an async DB session
        context manager (i.e. an ``async_sessionmaker``). ``generate_fn`` is the
        model-inference call; it defaults to the real Ollama client but can be
        injected in tests to avoid needing a live model.
        """
        self.session_factory = session_factory
        self._generate_fn = generate_fn

    # -- inference -------------------------------------------------------

    async def _generate(self, model_name: str, prompt: str) -> tuple[str, int]:
        if self._generate_fn is not None:
            return await self._generate_fn(model_name, prompt)
        # Call the shared runtime directly — the session (domain) layer depends on
        # the runtime layer, not on the API layer. This removes the former
        # sessions → api.runs inversion and its lazy-import cycle workaround.
        from app.runtime.manager import get_runtime

        result = await get_runtime().generate(model_name, prompt)
        return result.text, result.latency_ms

    # -- read helpers ----------------------------------------------------

    async def get_session(self, session_id: str) -> Optional[EvaluationSession]:
        async with self.session_factory() as db:
            return await SessionRepository(db).get(session_id)

    async def list_sessions(
        self,
        *,
        status: Optional[str] = None,
        session_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[EvaluationSession]:
        async with self.session_factory() as db:
            return await SessionRepository(db).list(
                status=status, session_type=session_type, limit=limit
            )

    async def get_events(
        self,
        session_id: str,
        *,
        after_id: Optional[int] = None,
        event_type: Optional[str] = None,
    ):
        async with self.session_factory() as db:
            return await EventRepository(db).list_for_session(
                session_id, after_id=after_id, event_type=event_type
            )

    async def _load_attacks(self, db, categories: list[str]) -> list[Attack]:
        query = select(Attack).order_by(Attack.id.asc())
        if categories:
            query = query.where(Attack.category.in_(categories))
        result = await db.execute(query)
        return list(result.scalars().all())

    # -- lifecycle: create ----------------------------------------------

    async def create_session(
        self,
        *,
        session_type: str,
        selected_models: list[str],
        selected_categories: list[str],
        selected_tier: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> EvaluationSession:
        async with self.session_factory() as db:
            srepo = SessionRepository(db)
            erepo = EventRepository(db)

            attacks = await self._load_attacks(db, selected_categories or [])
            total_tasks = len(selected_models) * len(attacks)
            estimated = total_tasks * AVG_TASK_SECONDS

            session = await srepo.create(
                session_type=session_type,
                selected_models=selected_models,
                selected_categories=selected_categories,
                selected_tier=selected_tier,
                total_tasks=total_tasks,
                estimated_seconds=estimated,
                metadata=metadata,
            )
            await erepo.add(
                session_id=session.id,
                event_type=EventType.SESSION_CREATED,
                metadata={
                    "total_tasks": total_tasks,
                    "selected_models": selected_models,
                    "selected_categories": selected_categories,
                    "selected_tier": selected_tier,
                },
            )
            return session

    # -- lifecycle: pause / cancel / resume -----------------------------

    async def pause_session(self, session_id: str) -> Optional[EvaluationSession]:
        async with self.session_factory() as db:
            srepo = SessionRepository(db)
            session = await srepo.get(session_id)
            if session is None:
                return None
            if session.status in SessionStatus.TERMINAL:
                return session
            return await srepo.set_status(session, SessionStatus.PAUSED)

    async def cancel_session(self, session_id: str) -> Optional[EvaluationSession]:
        async with self.session_factory() as db:
            srepo = SessionRepository(db)
            session = await srepo.get(session_id)
            if session is None:
                return None
            if session.status in SessionStatus.TERMINAL:
                return session
            return await srepo.set_status(session, SessionStatus.CANCELLED)

    async def resume_session(self, session_id: str) -> Optional[EvaluationSession]:
        """Continue a paused, failed, or interrupted (still-``running`` after a
        restart) session from where it stopped. Completed/cancelled sessions are
        returned unchanged.
        """
        async with self.session_factory() as db:
            session = await SessionRepository(db).get(session_id)
            if session is None:
                return None
            if session.status in SessionStatus.TERMINAL:
                return session
        return await self.run_session(session_id)

    # -- lifecycle: execute ---------------------------------------------

    async def run_session(self, session_id: str) -> Optional[EvaluationSession]:
        """Execute (or continue) a session to completion.

        Safe to call on a fresh, paused, failed, or interrupted session. Already
        completed tasks (tracked by ``completed_tasks``) are skipped, which is
        what makes resume-after-restart correct. A fresh DB session is opened for
        each task so pause/cancel requests made concurrently are observed.
        """
        # Phase 1: validate, snapshot the plan, and mark running.
        async with self.session_factory() as db:
            srepo = SessionRepository(db)
            session = await srepo.get(session_id)
            if session is None:
                return None
            if session.status in SessionStatus.TERMINAL:
                return session

            models = list(session.selected_models or [])
            attacks = await self._load_attacks(db, list(session.selected_categories or []))
            # Extract plain data so we never touch detached ORM objects later.
            attack_specs = [
                {
                    "id": a.id,
                    "name": a.name,
                    "category": a.category,
                    "prompt": a.prompt,
                }
                for a in attacks
            ]
            already_done = session.completed_tasks or 0
            await srepo.mark_running(session)

        # Deterministic task ordering is essential for correct resume: the first
        # ``already_done`` tasks are assumed finished and skipped.
        tasks = [(model, spec) for model in models for spec in attack_specs]
        emitted_models: set[str] = set()

        for idx, (model, spec) in enumerate(tasks):
            if idx < already_done:
                emitted_models.add(model)
                continue

            # Per-task: check for pause/cancel and emit start events.
            async with self.session_factory() as db:
                srepo = SessionRepository(db)
                erepo = EventRepository(db)
                session = await srepo.get(session_id)
                if session is None:
                    return None
                if session.status in (SessionStatus.CANCELLED, SessionStatus.PAUSED):
                    return session

                if model not in emitted_models:
                    await erepo.add(
                        session_id=session_id,
                        event_type=EventType.MODEL_STARTED,
                        model_name=model,
                    )
                    emitted_models.add(model)

                await erepo.add(
                    session_id=session_id,
                    event_type=EventType.ATTACK_STARTED,
                    model_name=model,
                    category=spec["category"],
                    attack_name=spec["name"],
                )

            # Inference happens outside any DB transaction (it is network I/O).
            try:
                response_text, latency_ms = await self._generate(model, spec["prompt"])
            except Exception as exc:  # noqa: BLE001 - surface any failure durably
                error_detail = getattr(exc, "detail", str(exc))
                async with self.session_factory() as db:
                    srepo = SessionRepository(db)
                    erepo = EventRepository(db)
                    session = await srepo.get(session_id)
                    if session is None:
                        return None
                    await erepo.add(
                        session_id=session_id,
                        event_type=EventType.SESSION_FAILED,
                        model_name=model,
                        metadata={"error": str(error_detail)},
                    )
                    return await srepo.mark_failed(session, error=str(error_detail))

            scored = score_response(spec["prompt"], response_text)

            # Persist the result (as a TestRun, so reports/dashboards keep
            # working), the two result events, and the progress increment.
            async with self.session_factory() as db:
                srepo = SessionRepository(db)
                erepo = EventRepository(db)
                session = await srepo.get(session_id)
                if session is None:
                    return None

                test_run = TestRun(
                    model_name=model,
                    attack_id=spec["id"],
                    prompt_sent=spec["prompt"],
                    model_response=response_text,
                    score=scored.score,
                    verdict=scored.verdict,
                    reason=scored.reason,
                    latency_ms=latency_ms,
                    timestamp=_utcnow(),
                )
                db.add(test_run)
                await db.commit()
                await db.refresh(test_run)

                await erepo.add(
                    session_id=session_id,
                    event_type=EventType.RESPONSE_RECEIVED,
                    model_name=model,
                    category=spec["category"],
                    attack_name=spec["name"],
                    response_excerpt=response_text,
                    latency_ms=latency_ms,
                )
                # The full result is stored in the verdict event's metadata so
                # the legacy batch-status endpoint can be reconstructed purely
                # from persisted state.
                await erepo.add(
                    session_id=session_id,
                    event_type=EventType.VERDICT_GENERATED,
                    model_name=model,
                    category=spec["category"],
                    attack_name=spec["name"],
                    verdict=scored.verdict,
                    latency_ms=latency_ms,
                    metadata={
                        "id": test_run.id,
                        "model_name": model,
                        "attack_id": spec["id"],
                        "attack_name": spec["name"],
                        "category": spec["category"],
                        "prompt_sent": spec["prompt"],
                        "model_response": response_text,
                        "score": scored.score,
                        "verdict": scored.verdict,
                        "reason": scored.reason,
                        "latency_ms": latency_ms,
                        "timestamp": test_run.timestamp.isoformat(),
                    },
                )
                await srepo.increment_completed(session, 1)

        # Phase 3: finalize (unless paused/cancelled slipped in at the very end).
        async with self.session_factory() as db:
            srepo = SessionRepository(db)
            erepo = EventRepository(db)
            session = await srepo.get(session_id)
            if session is None:
                return None
            if session.status in (SessionStatus.CANCELLED, SessionStatus.PAUSED):
                return session
            session = await srepo.mark_completed(session)
            await erepo.add(
                session_id=session_id,
                event_type=EventType.SESSION_COMPLETED,
                metadata={
                    "completed_tasks": session.completed_tasks,
                    "total_tasks": session.total_tasks,
                    "actual_seconds": session.actual_seconds,
                },
            )
            return session
