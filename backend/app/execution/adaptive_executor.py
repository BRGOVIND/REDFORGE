"""Adaptive attack execution.

Upgrades the flat ``attack -> judge -> done`` flow into a feedback loop:

    attack -> judge -> analyze
        if the attack failed (the model resisted): mutate + escalate + retry
        if the attack succeeded (the model was compromised): stop, move on

Escalation reuses the existing mutation engine (``app.mutations.mutator``) — no
mutation logic is duplicated here. Behavior is fully deterministic given fixed
model/judge outputs and the plan's fixed escalation order, and every attempt is
logged to the durable event store.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from app.db.models import TestRun
from app.evaluators.scoring import score_response
from app.mutations.mutator import mutate_prompt
from app.planner.evaluation_planner import EvaluationPlan, PlannedAttack
from app.sessions.constants import RESPONSE_EXCERPT_LEN, EventType, SessionStatus
from app.sessions.event_repository import EventRepository
from app.sessions.session_repository import SessionRepository

GenerateFn = Callable[[str, str], Awaitable[tuple[str, int]]]
# (attack_prompt, model_response, judge_model) -> (verdict, score, reason)
JudgeFn = Callable[[str, str, Optional[str]], Awaitable[tuple[str, float, str]]]

# Verdicts that mean the attack succeeded (the model was compromised).
COMPROMISED_VERDICTS = {"FAIL"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AttackAttempt(BaseModel):
    attempt: int
    strategy: Optional[str]      # mutation strategy, None for the original attack
    prompt: str
    response: str
    verdict: str
    score: float
    reason: str
    latency_ms: int


class AttackOutcome(BaseModel):
    order: int
    model: str
    category: str
    attack_name: str
    severity: str
    attempts: list[AttackAttempt] = Field(default_factory=list)
    final_verdict: str
    final_response_excerpt: str = ""
    compromised: bool
    retries_used: int


class ExecutionSummary(BaseModel):
    total_attacks: int
    executed: int
    compromised: int
    stopped_early: bool
    status: str
    outcomes: list[AttackOutcome] = Field(default_factory=list)


class AdaptiveExecutor:
    def __init__(
        self,
        session_factory,
        generate_fn: Optional[GenerateFn] = None,
        judge_fn: Optional[JudgeFn] = None,
    ) -> None:
        self.session_factory = session_factory
        self._generate_fn = generate_fn
        self._judge_fn = judge_fn

    # -- pluggable inference / evaluation --------------------------------

    async def _generate(self, model: str, prompt: str) -> tuple[str, int]:
        if self._generate_fn is not None:
            return await self._generate_fn(model, prompt)
        from app.api.runs import call_ollama

        return await call_ollama(model, prompt)

    async def _evaluate(
        self, prompt: str, response: str, plan: EvaluationPlan
    ) -> tuple[str, float, str]:
        if plan.evaluator == "llm_judge":
            if self._judge_fn is not None:
                return await self._judge_fn(prompt, response, plan.judge_model)
            from app.evaluators.judge import judge_response

            result = await judge_response(prompt, response, plan.judge_model or "llama3.2")
            return result.verdict, result.confidence, result.reason
        scored = score_response(prompt, response)
        return scored.verdict, scored.score, scored.reason

    # -- mutation (reuses the mutation engine) ---------------------------

    @staticmethod
    def _mutate(base_prompt: str, strategy: str) -> str:
        variants = mutate_prompt(base_prompt, [strategy])
        return variants[0].prompt if variants else base_prompt

    # -- main loop -------------------------------------------------------

    async def execute_plan(self, session_id: str, plan: EvaluationPlan) -> ExecutionSummary:
        # Mark running.
        async with self.session_factory() as db:
            srepo = SessionRepository(db)
            session = await srepo.get(session_id)
            if session is None:
                return ExecutionSummary(
                    total_attacks=0, executed=0, compromised=0,
                    stopped_early=True, status="missing",
                )
            if session.status not in SessionStatus.TERMINAL:
                await srepo.mark_running(session)
            already_done = session.completed_tasks or 0

        outcomes: list[AttackOutcome] = []
        compromised = 0
        executed = 0
        stopped_early = False
        final_status = SessionStatus.COMPLETED

        for planned in plan.attack_sequence:
            if planned.order < already_done:
                continue  # resume: skip already-completed attacks

            # Check for pause/cancel at each attack boundary.
            async with self.session_factory() as db:
                status = (await SessionRepository(db).get(session_id)).status
            if status in (SessionStatus.PAUSED, SessionStatus.CANCELLED):
                stopped_early = True
                final_status = status
                break

            outcome = await self._execute_attack(session_id, planned, plan)
            outcomes.append(outcome)
            executed += 1
            if outcome.compromised:
                compromised += 1

        if not stopped_early:
            async with self.session_factory() as db:
                srepo = SessionRepository(db)
                session = await srepo.get(session_id)
                if session and session.status not in SessionStatus.TERMINAL:
                    await srepo.mark_completed(session)
                    final_status = SessionStatus.COMPLETED

        return ExecutionSummary(
            total_attacks=len(plan.attack_sequence),
            executed=executed,
            compromised=compromised,
            stopped_early=stopped_early,
            status=final_status,
            outcomes=outcomes,
        )

    async def _execute_attack(
        self, session_id: str, planned: PlannedAttack, plan: EvaluationPlan
    ) -> AttackOutcome:
        attempts: list[AttackAttempt] = []
        strategy: Optional[str] = None
        current_prompt = planned.prompt
        attempt = 0
        escalation = plan.escalation_strategies
        max_retries = plan.max_retries

        async with self.session_factory() as db:
            erepo = EventRepository(db)
            srepo = SessionRepository(db)

            while True:
                # Start / retry marker.
                if attempt == 0:
                    await erepo.add(
                        session_id=session_id, event_type=EventType.ATTACK_STARTED,
                        model_name=planned.model, category=planned.category,
                        attack_name=planned.attack_name,
                        metadata={"attempt": 0, "order": planned.order},
                    )
                else:
                    await erepo.add(
                        session_id=session_id, event_type=EventType.ATTACK_RETRIED,
                        model_name=planned.model, category=planned.category,
                        attack_name=planned.attack_name,
                        metadata={"attempt": attempt, "strategy": strategy},
                    )

                # Inference (errors become an ERROR verdict; no retry on error).
                try:
                    response_text, latency_ms = await self._generate(planned.model, current_prompt)
                    verdict, score, reason = await self._evaluate(current_prompt, response_text, plan)
                except Exception as exc:  # noqa: BLE001 - keep the run resilient
                    response_text, latency_ms = "", 0
                    verdict, score, reason = "ERROR", 0.0, f"execution error: {exc}"

                await erepo.add(
                    session_id=session_id, event_type=EventType.RESPONSE_RECEIVED,
                    model_name=planned.model, category=planned.category,
                    attack_name=planned.attack_name, response_excerpt=response_text,
                    latency_ms=latency_ms, metadata={"attempt": attempt, "strategy": strategy},
                )
                await erepo.add(
                    session_id=session_id, event_type=EventType.VERDICT_GENERATED,
                    model_name=planned.model, category=planned.category,
                    attack_name=planned.attack_name, verdict=verdict, latency_ms=latency_ms,
                    metadata={
                        "attempt": attempt, "strategy": strategy,
                        "attack_id": planned.attack_id, "attack_name": planned.attack_name,
                        "category": planned.category, "model_name": planned.model,
                        "severity": planned.severity,
                        "prompt_sent": current_prompt, "model_response": response_text,
                        "score": score, "verdict": verdict, "reason": reason,
                        "latency_ms": latency_ms,
                    },
                )

                attempts.append(AttackAttempt(
                    attempt=attempt, strategy=strategy, prompt=current_prompt,
                    response=response_text[:RESPONSE_EXCERPT_LEN], verdict=verdict,
                    score=score, reason=reason, latency_ms=latency_ms,
                ))

                if verdict in COMPROMISED_VERDICTS:
                    break  # attack succeeded — stop escalating
                if verdict == "ERROR":
                    break  # don't hammer a failing backend
                if attempt < max_retries and escalation:
                    strategy = escalation[attempt % len(escalation)]
                    current_prompt = self._mutate(planned.prompt, strategy)
                    await erepo.add(
                        session_id=session_id, event_type=EventType.MUTATION_APPLIED,
                        model_name=planned.model, category=planned.category,
                        attack_name=planned.attack_name,
                        metadata={"next_attempt": attempt + 1, "strategy": strategy},
                    )
                    attempt += 1
                    continue
                break

            # Decisive attempt: first compromise, else the last one tried.
            decisive = next(
                (a for a in attempts if a.verdict in COMPROMISED_VERDICTS), attempts[-1]
            )
            test_run = TestRun(
                model_name=planned.model, attack_id=planned.attack_id,
                prompt_sent=decisive.prompt, model_response=decisive.response,
                score=decisive.score, verdict=decisive.verdict, reason=decisive.reason,
                latency_ms=decisive.latency_ms, timestamp=_utcnow(),
            )
            db.add(test_run)
            await db.commit()

            session = await srepo.get(session_id)
            if session is not None:
                await srepo.increment_completed(session, 1)

        compromised = decisive.verdict in COMPROMISED_VERDICTS
        return AttackOutcome(
            order=planned.order, model=planned.model, category=planned.category,
            attack_name=planned.attack_name, severity=planned.severity, attempts=attempts,
            final_verdict=decisive.verdict, final_response_excerpt=decisive.response,
            compromised=compromised, retries_used=len(attempts) - 1,
        )
