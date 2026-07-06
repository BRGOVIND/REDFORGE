"""The intelligent evaluation pipeline — RedForge's primary entry point.

Given only a model and an evaluation profile, this orchestrates the whole flow
end to end on top of the durable session engine:

    create session -> profile model -> generate plan -> execute (adaptive)
        -> analyze results -> build report

Every stage persists into the session (status, events, and metadata), so the
result survives a restart and is queryable via the API. Inference and judging
are injectable so the pipeline runs deterministically in tests without Ollama.
"""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable, Optional

from app.analysis import (
    analyze,
    attach_recommendations,
    build_report,
    generate_findings,
)
from app.analysis.security_analyzer import AttackResult
from app.evaluation_profiles import profile_registry
from app.execution.adaptive_executor import AdaptiveExecutor
from app.logging_config import get_logger, log_op
from app.planner import EvaluationPlanner, build_planning_context
from app.planner.evaluation_planner import EvaluationPlan
from app.profiler import ModelProfiler
from app.profiler.profile_builder import ModelProfile
from app.sessions.constants import EventType, SessionStatus, SessionType
from app.sessions.event_repository import EventRepository
from app.sessions.session_repository import SessionRepository

GenerateFn = Callable[[str, str], Awaitable[tuple[str, int]]]
JudgeFn = Callable[[str, str, Optional[str]], Awaitable[tuple[str, float, str]]]
MetadataFetcher = Callable[[str], Awaitable[Optional[dict]]]


logger = get_logger("pipeline")


class PipelineError(ValueError):
    pass


class EvaluationPipeline:
    def __init__(
        self,
        session_factory,
        *,
        metadata_fetcher: Optional[MetadataFetcher] = None,
        generate_fn: Optional[GenerateFn] = None,
        judge_fn: Optional[JudgeFn] = None,
    ) -> None:
        self.session_factory = session_factory
        self.profiler = ModelProfiler(metadata_fetcher)
        self.planner = EvaluationPlanner()
        self.executor = AdaptiveExecutor(session_factory, generate_fn, judge_fn)

    # -- session metadata helpers ---------------------------------------

    async def _merge_metadata(self, session_id: str, updates: dict) -> None:
        async with self.session_factory() as db:
            session = await SessionRepository(db).get(session_id)
            if session is None:
                return
            meta = dict(session.session_metadata or {})
            meta.update(updates)
            session.session_metadata = meta
            await db.commit()

    async def _emit(self, session_id: str, event_type: str, **fields) -> None:
        async with self.session_factory() as db:
            await EventRepository(db).add(
                session_id=session_id, event_type=event_type, **fields
            )

    # -- entry points ----------------------------------------------------

    async def create_session_shell(
        self, profile_name: str, models: list[str]
    ) -> str:
        """Persist a minimal session immediately so the caller gets an id that is
        instantly retrievable (no 404), then execution happens separately."""
        profile = profile_registry.get_profile(profile_name)
        if profile is None:
            raise PipelineError(f"unknown profile '{profile_name}'")
        if not models:
            raise PipelineError("at least one model is required")

        session_type = (
            SessionType.BENCHMARK if profile.multi_model else SessionType.BATCH
        )
        async with self.session_factory() as db:
            session = await SessionRepository(db).create(
                session_type=session_type,
                selected_models=models if profile.multi_model else models[:1],
                selected_categories=[],
                selected_tier=profile.name,
                total_tasks=0,
                metadata={"profile": profile.name, "stage": "created", "models": models},
            )
            session_id = session.id
        await self._emit(session_id, EventType.SESSION_CREATED,
                         metadata={"profile": profile.name})
        return session_id

    async def run(self, session_id: str) -> str:
        """Execute the full pipeline for an already-created session. Idempotent
        enough to resume: if a plan already exists it is reused."""
        async with self.session_factory() as db:
            session = await SessionRepository(db).get(session_id)
            if session is None:
                raise PipelineError(f"session '{session_id}' not found")
            meta = dict(session.session_metadata or {})

        profile_name = meta.get("profile")
        profile = profile_registry.get_profile(profile_name) if profile_name else None
        if profile is None:
            raise PipelineError(f"session '{session_id}' has no valid profile")
        models = meta.get("models") or session.selected_models or []
        primary_model = models[0] if models else None
        started = time.monotonic()
        log_op(logger, logging.INFO, f"evaluation started (profile={profile.name})",
               op="run", session=session_id, model=primary_model)

        # 1+2. Profile models and 3. build plan (skip if resuming with a plan).
        if "evaluation_plan" in meta:
            plan = EvaluationPlan(**meta["evaluation_plan"])
        else:
            plan = await self._profile_and_plan(session_id, profile, models)

        # 4. Execute adaptively.
        summary = await self.executor.execute_plan(session_id, plan)
        if summary.status in (SessionStatus.PAUSED, SessionStatus.CANCELLED):
            await self._merge_metadata(session_id, {"stage": summary.status})
            log_op(logger, logging.INFO, f"evaluation {summary.status}",
                   op="run", session=session_id, model=primary_model,
                   duration=time.monotonic() - started)
            return session_id

        # 5+6. Analyze and build the report from durable events.
        await self._analyze_and_report(session_id, profile, models, plan)
        log_op(logger, logging.INFO,
               f"evaluation completed ({summary.executed} attacks, {summary.compromised} compromised)",
               op="run", session=session_id, model=primary_model,
               duration=time.monotonic() - started)
        return session_id

    async def run_full(self, profile_name: str, models: list[str]) -> str:
        session_id = await self.create_session_shell(profile_name, models)
        await self.run(session_id)
        return session_id

    # -- stages ----------------------------------------------------------

    async def _profile_and_plan(self, session_id, profile, models) -> EvaluationPlan:
        model_profiles: dict[str, ModelProfile] = {}
        async with self.session_factory() as db:
            for model in (models if profile.multi_model else models[:1]):
                mp = await self.profiler.get_profile(model, db, session_id=session_id)
                model_profiles[model] = mp

        await self._merge_metadata(session_id, {
            "model_profiles": {m: p.model_dump(mode="json") for m, p in model_profiles.items()},
            "stage": "profiled",
        })
        await self._emit(session_id, EventType.MODEL_PROFILED,
                         metadata={"models": list(model_profiles)})

        async with self.session_factory() as db:
            context = await build_planning_context(profile, models, model_profiles, db)
            plan = await self.planner.plan(context, db)

        # Record the plan and align session progress fields to it.
        async with self.session_factory() as db:
            session = await SessionRepository(db).get(session_id)
            if session is not None:
                session.selected_categories = plan.category_order
                session.total_tasks = plan.total_attacks
                meta = dict(session.session_metadata or {})
                meta["evaluation_plan"] = plan.model_dump(mode="json")
                meta["stage"] = "planned"
                session.session_metadata = meta
                await db.commit()
        await self._emit(session_id, EventType.PLAN_GENERATED,
                         metadata={"deterministic_key": plan.deterministic_key,
                                   "total_attacks": plan.total_attacks})
        return plan

    async def _analyze_and_report(self, session_id, profile, models, plan) -> None:
        results_by_model = await self._results_from_events(session_id)

        analyses: dict[str, dict] = {}
        for model, results in results_by_model.items():
            analysis = analyze(model, results)
            findings = attach_recommendations(generate_findings(analysis))
            analyses[model] = {
                "analysis": analysis.model_dump(),
                "findings": [f.model_dump() for f in findings],
            }

        primary = (plan.models or models)[0]
        primary_entry = analyses.get(primary)
        report_dict = None
        if primary_entry is not None:
            from app.analysis.security_analyzer import AnalysisResult
            from app.analysis.finding_generator import Finding

            analysis = AnalysisResult(**primary_entry["analysis"])
            findings = [Finding(**f) for f in primary_entry["findings"]]
            model_overview = {}
            meta_profiles = (await self._get_meta(session_id)).get("model_profiles", {})
            model_overview = meta_profiles.get(primary, {})
            report = build_report(
                model_name=primary, profile_name=profile.name,
                model_overview=model_overview, analysis=analysis, findings=findings,
                execution={"executed": analysis.total_tests,
                           "compromised": analysis.failed_tests},
                plan_key=plan.deterministic_key,
            )
            report_dict = report.model_dump(mode="json")

        # Optional leaderboard for multi-model runs.
        leaderboard = None
        if profile.multi_model and len(analyses) > 1:
            leaderboard = sorted(
                (
                    {"model": m, "overall_security_score": a["analysis"]["overall_security_score"]}
                    for m, a in analyses.items()
                ),
                key=lambda e: e["overall_security_score"], reverse=True,
            )

        updates = {
            "analyses": analyses,
            "findings": primary_entry["findings"] if primary_entry else [],
            "report": report_dict,
            "stage": "completed",
        }
        if leaderboard is not None:
            updates["leaderboard"] = leaderboard
        await self._merge_metadata(session_id, updates)

        await self._emit(session_id, EventType.ANALYSIS_COMPLETED,
                         metadata={"models": list(analyses)})
        if report_dict is not None:
            await self._emit(session_id, EventType.REPORT_GENERATED,
                             metadata={"overall_security_score":
                                       report_dict["security_score"]["overall"]})

    # -- durable result derivation --------------------------------------

    async def _get_meta(self, session_id: str) -> dict:
        async with self.session_factory() as db:
            session = await SessionRepository(db).get(session_id)
            return dict(session.session_metadata or {}) if session else {}

    async def _results_from_events(self, session_id: str) -> dict[str, list[AttackResult]]:
        """Derive one decisive result per attack from the verdict events.

        Grouped by (model, attack_name); the decisive verdict is the first
        compromise, else the highest-numbered attempt. Reading from persisted
        events (not in-memory outcomes) makes analysis correct after a restart.
        """
        async with self.session_factory() as db:
            events = await EventRepository(db).list_for_session(
                session_id, event_type=EventType.VERDICT_GENERATED
            )

        groups: dict[tuple[str, str], list[dict]] = {}
        for ev in events:
            md = ev.event_metadata or {}
            key = (md.get("model_name", ""), md.get("attack_name", ev.attack_name or ""))
            groups.setdefault(key, []).append(md)

        results_by_model: dict[str, list[AttackResult]] = {}
        for (model, _attack), metas in groups.items():
            decisive = next(
                (m for m in metas if m.get("verdict") == "FAIL"),
                max(metas, key=lambda m: m.get("attempt", 0)),
            )
            results_by_model.setdefault(model, []).append(AttackResult(
                category=decisive.get("category", "UNKNOWN"),
                attack_name=decisive.get("attack_name", "unknown"),
                severity=decisive.get("severity", "medium"),
                verdict=decisive.get("verdict", "UNCERTAIN"),
                response_excerpt=decisive.get("model_response", "") or "",
                score=float(decisive.get("score", 0.0) or 0.0),
                latency_ms=decisive.get("latency_ms"),
            ))
        return results_by_model
