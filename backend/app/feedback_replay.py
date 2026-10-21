"""Side-effect-free local feedback replay through the existing Job and Evaluation engines."""
from __future__ import annotations

import asyncio
import ipaddress
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.db.models import EvaluationResult, FeedbackCase, Prompt, PromptVersion, WorkbenchSession
from app.evaluation.service import _runtime_generate_rich, compose_summary
from app.evaluation.similarity import get_similarity
from app.jobs.domain import JobResult
from app.jobs.handlers import handler_registry
from app.jobs.job_types import JobTypeDef, register_job_type
from app.observability_privacy import audit


def local_runtime_ready() -> bool:
    """A local provider label alone is insufficient if its URL was overridden."""
    from app.config import settings
    from app.runtime.manager import get_runtime
    name = settings.RUNTIME_PROVIDER.lower()
    if name not in {"ollama", "lmstudio", "llamacpp", "vllm"}:
        return False
    provider = get_runtime().provider
    if getattr(provider, "name", "").lower() != name:
        return False
    parsed = urlsplit(getattr(provider, "base_url", ""))
    if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


async def handle_feedback_replay(job, ctx) -> JobResult:
    from app.config import settings
    params = job.params or {}
    if params.get("environment") != "local_evaluation" or not job.project_id:
        return JobResult(success=False, message="Explicit local evaluation environment required")
    if not local_runtime_ready():
        return JobResult(success=False, message="Local runtime provider required")
    timeout = params.get("timeout_seconds")
    candidate = params.get("candidate_model")
    baseline = params.get("baseline_model")
    if not isinstance(timeout, int) or not 1 <= timeout <= 60 or not isinstance(candidate, str) or not 1 <= len(candidate) <= 200:
        return JobResult(success=False, message="Invalid replay limits")
    if baseline is not None and (not isinstance(baseline, str) or not 1 <= len(baseline) <= 200):
        return JobResult(success=False, message="Invalid baseline model")
    if not isinstance(params.get("max_calls"), int) or params["max_calls"] < (2 if baseline else 1) or params["max_calls"] > 2:
        return JobResult(success=False, message="Replay call budget must match selected models")
    async with AsyncSessionLocal() as db:
        case = (await db.execute(select(FeedbackCase).where(FeedbackCase.id == params.get("case_id"),
            FeedbackCase.project_id == job.project_id, FeedbackCase.state == "approved"))).scalar_one_or_none()
        if case is None or not case.evaluation_prompt_id:
            return JobResult(success=False, message="Approved project case not found")
        prompt = await db.get(Prompt, case.evaluation_prompt_id)
        if prompt is None:
            return JobResult(success=False, message="Published evaluation prompt missing")
        version = (await db.execute(select(PromptVersion).where(PromptVersion.prompt_id == prompt.id,
            PromptVersion.version == (prompt.active_version or 1)))).scalar_one_or_none()
        if version is None:
            return JobResult(success=False, message="Published prompt version missing")
        snapshot = version.snapshot or {}
        text = snapshot.get("prompt")
        expected = snapshot.get("expected_output") or ""
        criteria = snapshot.get("acceptance_criteria") or {}
        if not isinstance(text, str) or not text or len(text) > 4096:
            return JobResult(success=False, message="Invalid published test prompt")
        prompt_id, prompt_set_id, version_number = prompt.id, prompt.prompt_set_id, version.version
    # Only plain text enters the Runtime Manager. No tools, arbitrary options,
    # captured production operations, or production environment are forwarded.
    results: dict[str, dict] = {}
    for label, model in (("baseline", baseline), ("candidate", candidate)):
        if model is None:
            continue
        if ctx.is_cancelled():
            return JobResult(success=False, message="Replay cancelled")
        await ctx.report_progress(0.15 if label == "baseline" else 0.55, f"evaluating {label}")
        try:
            async with asyncio.timeout(timeout):
                generated = await _runtime_generate_rich(model, text, options={"num_predict": 512})
        except TimeoutError:
            return JobResult(success=False, message=f"{label} timed out")
        except Exception:
            return JobResult(success=False, message=f"{label} local runtime failed")
        if ctx.is_cancelled():
            return JobResult(success=False, message="Replay cancelled")
        results[label] = {"response": str(generated.get("response") or "")[:16384],
                          "latency_ms": generated.get("latency_ms"),
                          "total_tokens": generated.get("total_tokens")}
    response = results["candidate"]["response"]
    reference = expected or (results.get("baseline") or {}).get("response", "")
    score = get_similarity("text").score(response, reference).score if reference else None
    min_similarity = criteria.get("min_similarity", 60)
    if not isinstance(min_similarity, (int, float)) or not 0 <= min_similarity <= 100:
        min_similarity = 60
    includes = criteria.get("must_include", [])
    excludes = criteria.get("must_exclude", [])
    if not isinstance(includes, list) or not isinstance(excludes, list):
        includes, excludes = [], []
    checks = [all(isinstance(x, str) and x in response for x in includes[:20]),
              all(isinstance(x, str) and x not in response for x in excludes[:20])]
    if criteria.get("require_json"):
        import json
        try:
            json.loads(response)
            checks.append(True)
        except ValueError:
            checks.append(False)
    explicit_criteria = (criteria.get("min_similarity") is not None or bool(includes)
                         or bool(excludes) or bool(criteria.get("require_json")))
    verdict = ("pass" if all(checks) and (score is None or score >= min_similarity) else "fail") if (expected or explicit_criteria) else "ungraded"
    if ctx.is_cancelled():
        return JobResult(success=False, message="Replay cancelled")
    # Persist only numeric results into the existing Workbench, never raw model
    # output. Its ordinary evaluation history and anomaly rules can use the row.
    session_id = str(uuid4())
    model_specs = [{"target_model": model, "label": label} for label, model in
                   (("baseline", baseline), ("candidate", candidate)) if model]
    rows = []
    for label, model in (("baseline", baseline), ("candidate", candidate)):
        if model is None:
            continue
        rows.append({"id": str(uuid4()), "session_id": session_id, "prompt_id": prompt_id,
            "prompt_set_id": prompt_set_id, "prompt_version": version_number,
            "prompt_title": case.title, "target_model": model, "provider": settings.RUNTIME_PROVIDER.lower(),
            "label": label, "response": "", "metrics": {"latency_ms": results[label]["latency_ms"],
                "total_tokens": results[label]["total_tokens"]},
            "similarity_score": score if label == "candidate" else None,
            "baseline_type": "expected" if expected else "none",
            "verdict": (verdict if verdict != "ungraded" else "none") if label == "candidate" else "none",
            "regressions": [], "warnings": ["Response body omitted by feedback privacy policy"]})
    summary = compose_summary(rows, model_specs)
    summary["feedback_case_id"] = case.id
    summary["responses_omitted"] = True
    async with AsyncSessionLocal() as db:
        db.add(WorkbenchSession(id=session_id, project_id=job.project_id,
            name=f"Feedback replay {case.id}", models=model_specs,
            prompt_set_ids=[prompt_set_id], similarity="text", status="completed",
            config={"feedback_case_id": case.id, "environment": "local_evaluation",
                    "prompt_versions": {prompt_id: version_number}},
            summary=summary, total_tasks=len(rows), completed_tasks=len(rows),
            completed_at=datetime.now(timezone.utc)))
        for row in rows:
            db.add(EvaluationResult(**row))
        audit(db, job.project_id, "feedback_case_replayed", case.id,
              details={"session_id": session_id, "calls": len(rows), "verdict": verdict})
        await db.commit()
    await ctx.report_progress(1.0, "comparison complete")
    return JobResult(success=True, message="Local replay complete", data={
        "case_id": case.id, "evaluation_session_id": session_id,
        "evaluation_prompt_id": prompt_id, "prompt_version": version_number,
        "environment": "local_evaluation", "candidate_model": candidate,
        "baseline_model": baseline, "similarity_score": score, "verdict": verdict,
        "candidate_latency_ms": results["candidate"]["latency_ms"],
        "baseline_latency_ms": results.get("baseline", {}).get("latency_ms"),
        "external_cost_usd": 0, "calls": len(results),
        "note": "Ungraded means no expected outcome or pass/fail criterion was supplied."})


def register_feedback_handlers() -> None:
    register_job_type(JobTypeDef("feedback_replay", "Feedback Replay", concurrency=1, default_max_attempts=1))
    handler_registry.register("feedback_replay", handle_feedback_replay)
