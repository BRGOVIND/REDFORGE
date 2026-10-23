"""Bounded local security replay using RedForge's existing evaluator and job queue."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.db.models import SecurityCandidateRun, SecurityCandidateVersion
from app.evaluation.service import _runtime_generate_rich
from app.evaluators.scoring import score_response
from app.feedback_replay import local_runtime_ready
from app.jobs.domain import JobResult
from app.jobs.handlers import handler_registry
from app.jobs.job_types import JobTypeDef, register_job_type
from app.observability_privacy import audit


async def handle_security_candidate_run(job, ctx) -> JobResult:
    params = job.params or {}
    if params.get("environment") != "local_evaluation" or not job.project_id:
        return JobResult(success=False, message="Explicit local evaluation environment required")
    if not local_runtime_ready():
        return JobResult(success=False, message="Local runtime required")
    timeout = params.get("timeout_seconds")
    max_tokens = params.get("max_output_tokens")
    if type(timeout) is not int or not 1 <= timeout <= 60 or type(max_tokens) is not int or not 16 <= max_tokens <= 512:
        return JobResult(success=False, message="Invalid execution budget")

    async with AsyncSessionLocal() as db:
        run = (await db.execute(select(SecurityCandidateRun).where(
            SecurityCandidateRun.id == params.get("run_id"),
            SecurityCandidateRun.project_id == job.project_id))).scalar_one_or_none()
        if run is None or run.status != "pending":
            return JobResult(success=False, message="Pending project run not found")
        version = (await db.execute(select(SecurityCandidateVersion).where(
            SecurityCandidateVersion.id == run.candidate_version_id,
            SecurityCandidateVersion.project_id == job.project_id))).scalar_one_or_none()
        if version is None:
            return JobResult(success=False, message="Approved version missing")
        snapshot = version.snapshot or {}
        prompt = snapshot.get("prompt_text")
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 4096:
            return JobResult(success=False, message="Invalid approved test prompt")
        run.status = "running"
        await db.commit()
        run_id, model = run.id, run.model

    error = None
    response = None
    try:
        if ctx.is_cancelled():
            raise asyncio.CancelledError()
        await ctx.report_progress(0.15, "running local security test")
        async with asyncio.timeout(timeout):
            generated = await _runtime_generate_rich(model, prompt, options={"num_predict": max_tokens})
        if ctx.is_cancelled():
            raise asyncio.CancelledError()
        response = str(generated.get("response") or "")[:16384]
        score = score_response(prompt, response)
        outcome = {"FAIL": "detected", "PASS": "not_detected"}.get(score.verdict, "uncertain")
        evidence = {"evaluator": "existing_rule_based_security_scorer",
                    "verdict": score.verdict, "score": score.score,
                    "reason": score.reason, "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                    "latency_ms": generated.get("latency_ms"),
                    "total_tokens": generated.get("total_tokens"),
                    "response_body_stored": False,
                    "warning": "Heuristic result is not confirmed exploitability"}
    except asyncio.CancelledError:
        error = "cancelled"
    except TimeoutError:
        error = "timeout"
    except Exception:
        error = "local runtime failure"

    async with AsyncSessionLocal() as db:
        run = (await db.execute(select(SecurityCandidateRun).where(
            SecurityCandidateRun.id == run_id,
            SecurityCandidateRun.project_id == job.project_id))).scalar_one_or_none()
        if run is None:
            return JobResult(success=False, message="Project run disappeared")
        run.completed_at = datetime.now(timezone.utc)
        if error:
            run.status = "cancelled" if error == "cancelled" else "failed"
            run.outcome = "inconclusive"
            run.evidence = {"error": error, "response_body_stored": False}
        else:
            run.status = "completed"
            run.outcome = outcome
            run.evidence = evidence
        audit(db, job.project_id, "security_candidate_run_completed", run.id,
              details={"status": run.status, "outcome": run.outcome})
        await db.commit()
    if error:
        return JobResult(success=False, message=error)
    await ctx.report_progress(1.0, "security test complete")
    return JobResult(success=True, message="Local security test complete", data={
        "run_id": run_id, "outcome": outcome, "classification": "observed",
        "warning": "Heuristic result is not confirmed exploitability"})


def register_security_candidate_handlers() -> None:
    register_job_type(JobTypeDef("security_candidate_run", "Security Candidate Test",
                                 concurrency=1, default_max_attempts=1))
    handler_registry.register("security_candidate_run", handle_security_candidate_run)
