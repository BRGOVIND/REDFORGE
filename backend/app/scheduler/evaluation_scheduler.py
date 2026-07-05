"""Turns a chosen profile into a running (or resumable) evaluation.

The scheduler is the seam between the *declarative* world (profiles, plans) and
the *durable execution* world built in Sprint 1 (``SessionManager``). It:

* expands a profile into a deterministic :class:`ExecutionPlan`,
* creates a persistent session that carries the plan in its metadata,
* delegates pause / resume / cancel to the session manager (so recovery keeps
  working unchanged), and
* computes deterministic retry targets from a session's recorded events.

It intentionally does **not** re-implement the execution loop; it configures and
drives the Sprint 1 engine.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvaluationSession
from app.evaluation_profiles.profile import EvaluationProfile
from app.scheduler.execution_plan import ExecutionPlan
from app.scheduler.plan_builder import build_execution_plan
from app.sessions.constants import EventType, SessionType
from app.sessions.session_manager import SessionManager


class EvaluationScheduler:
    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager

    # -- planning --------------------------------------------------------

    async def build_plan(
        self, profile: EvaluationProfile, models: list[str], db: AsyncSession
    ) -> ExecutionPlan:
        return await build_execution_plan(profile, models, db)

    @staticmethod
    def _session_type(profile: EvaluationProfile) -> str:
        if profile.multi_model:
            return SessionType.BENCHMARK
        if profile.dataset == "attack_library":
            return SessionType.BATCH
        return SessionType.BENCHMARK

    # -- creation --------------------------------------------------------

    async def create_evaluation(
        self, profile: EvaluationProfile, models: list[str], db: AsyncSession
    ) -> tuple[EvaluationSession, ExecutionPlan]:
        """Build the plan and persist a session that embeds it.

        The plan lives in the session's metadata so it survives a restart and
        can be replayed/visualized without rebuilding. Execution is driven by
        the existing session engine.
        """
        plan = await build_execution_plan(profile, models, db)

        session = await self.session_manager.create_session(
            session_type=self._session_type(profile),
            selected_models=plan.models,
            selected_categories=plan.categories,
            selected_tier=profile.name,
            metadata={
                "profile": profile.name,
                "deterministic_key": plan.deterministic_key,
                "evaluator": profile.evaluator,
                "judge_model": profile.judge_model,
                "plan": plan.model_dump(),
            },
        )
        return session, plan

    # -- lifecycle passthroughs (durable, from Sprint 1) -----------------

    async def pause(self, session_id: str) -> Optional[EvaluationSession]:
        return await self.session_manager.pause_session(session_id)

    async def resume(self, session_id: str) -> Optional[EvaluationSession]:
        return await self.session_manager.resume_session(session_id)

    async def cancel(self, session_id: str) -> Optional[EvaluationSession]:
        return await self.session_manager.cancel_session(session_id)

    # -- retries ---------------------------------------------------------

    async def compute_retry_targets(
        self, session_id: str, retry_on: list[str]
    ) -> list[dict]:
        """Deterministically list the attacks in a session eligible for retry.

        An attack is eligible if its recorded verdict is in ``retry_on`` (e.g.
        ``["ERROR", "FAIL"]``). ``ERROR`` maps to a ``session_failed`` event.
        Results are ordered by event id, so a retry run is reproducible.
        """
        retry_on_set = {v.upper() for v in retry_on}
        targets: list[dict] = []

        verdict_events = await self.session_manager.get_events(
            session_id, event_type=EventType.VERDICT_GENERATED
        )
        for event in verdict_events:
            if event.verdict and event.verdict.upper() in retry_on_set:
                targets.append(
                    {
                        "model": event.model_name,
                        "category": event.category,
                        "attack_name": event.attack_name,
                        "verdict": event.verdict,
                        "source_event_id": event.id,
                    }
                )

        if "ERROR" in retry_on_set:
            failed_events = await self.session_manager.get_events(
                session_id, event_type=EventType.SESSION_FAILED
            )
            for event in failed_events:
                targets.append(
                    {
                        "model": event.model_name,
                        "category": event.category,
                        "attack_name": event.attack_name,
                        "verdict": "ERROR",
                        "source_event_id": event.id,
                    }
                )

        targets.sort(key=lambda t: t["source_event_id"])
        return targets
