"""Reviewed, trace-derived security tests for the local Security Center."""
from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.attacks.library import Category
from app.db.database import get_db
from app.db.models import (FeedbackCase, Project, SecurityCandidate,
                           SecurityCandidateRun, SecurityCandidateVersion, TraceEvent)
from app.jobs import job_service
from app.observability_privacy import _scrub, audit, get_policy
from app.release_gates import CandidateIdentity

router = APIRouter(prefix="/api/projects/{project_id}/security-candidates", tags=["security-candidates"])
_CATEGORIES = {Category.PROMPT_INJECTION, Category.JAILBREAK,
               Category.CONTEXT_MANIPULATION, Category.DATA_LEAKAGE}


class CandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str | None = Field(default=None, max_length=128)
    feedback_case_id: str | None = Field(default=None, max_length=36)
    category: str
    title: str = Field(min_length=1, max_length=200)
    include_source_input: bool = False

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.event_id) == bool(self.feedback_case_id):
            raise ValueError("Select exactly one trace or approved feedback case")
        if self.category not in _CATEGORIES:
            raise ValueError("Category is not supported by existing Security Center")
        return self


class CandidateEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    prompt_text: str = Field(min_length=1, max_length=4096)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["local_evaluation"]
    model: str = Field(min_length=1, max_length=200)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    max_output_tokens: int = Field(default=256, ge=16, le=512)
    max_external_cost_usd: Literal[0] = 0
    release_candidate: CandidateIdentity | None = None


class RunClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: Literal["confirmed", "dismissed"]
    severity: Literal["low", "medium", "high", "critical"] | None = None
    remediation_status: Literal["unreviewed", "planned", "fixed", "accepted"] = "unreviewed"
    justification: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def confirmed_needs_severity(self):
        if self.classification == "confirmed" and self.severity is None:
            raise ValueError("Confirmed finding needs reviewed severity")
        return self


async def _project(db: AsyncSession, project_id: str, request: Request) -> None:
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


async def _candidate(db: AsyncSession, project_id: str, candidate_id: str) -> SecurityCandidate:
    row = (await db.execute(select(SecurityCandidate).where(
        SecurityCandidate.id == candidate_id,
        SecurityCandidate.project_id == project_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Security candidate not found")
    return row


def _sanitize(value: str, limit: int) -> str:
    try:
        result = _scrub(value, limit)
    except Exception:
        raise HTTPException(422, "Sensitive text could not be sanitized") from None
    if not isinstance(result, str):
        raise HTTPException(422, "Invalid sensitive text")
    return result


def _view(row: SecurityCandidate, *, include_body: bool = False) -> dict:
    return {"id": row.id, "project_id": row.project_id, "source_event_id": row.source_event_id,
            "trace_id": row.trace_id, "feedback_case_id": row.feedback_case_id,
            "source_received_at": row.source_received_at, "provider": row.provider,
            "model": row.model, "prompt_template_id": row.prompt_template_id,
            "prompt_version_id": row.prompt_version_id, "category": row.category,
            "title": row.title, "state": row.state,
            "approved_version": row.approved_version, "created_at": row.created_at,
            "prompt_text": row.prompt_text if include_body else None}


@router.post("", status_code=201)
async def create_candidate(project_id: str, body: CandidateCreate, request: Request,
                           x_redforge_sensitive_access: str | None = Header(default=None),
                           x_redforge_confirm_action: str | None = Header(default=None),
                           db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    trace: TraceEvent | None = None
    feedback: FeedbackCase | None = None
    if body.event_id:
        trace = (await db.execute(select(TraceEvent).where(
            TraceEvent.project_id == project_id,
            TraceEvent.event_id == body.event_id))).scalar_one_or_none()
        if trace is None:
            raise HTTPException(404, "Project trace not found")
    else:
        feedback = (await db.execute(select(FeedbackCase).where(
            FeedbackCase.id == body.feedback_case_id,
            FeedbackCase.project_id == project_id,
            FeedbackCase.state == "approved"))).scalar_one_or_none()
        if feedback is None:
            raise HTTPException(404, "Approved project feedback case not found")
        trace = (await db.execute(select(TraceEvent).where(
            TraceEvent.id == feedback.trace_event_id,
            TraceEvent.project_id == project_id))).scalar_one_or_none()
    fingerprint = hashlib.sha256(f"{project_id}:{body.event_id or body.feedback_case_id}:{body.category}".encode()).hexdigest()
    prompt_text = None
    if body.include_source_input:
        if x_redforge_sensitive_access != "allow" or x_redforge_confirm_action != "include-source-input":
            raise HTTPException(403, "Explicit sensitive-data access and confirmation required")
        if feedback is not None:
            if not feedback.prompt_text:
                raise HTTPException(409, "Reviewed source prompt unavailable")
            prompt_text = _sanitize(feedback.prompt_text, 4096)
        else:
            policy = await get_policy(db, project_id)
            if not policy.telemetry_enabled or not policy.capture_input or trace is None or not trace.input_text:
                raise HTTPException(409, "Trace input unavailable under project privacy policy")
            prompt_text = _sanitize(trace.input_text, 4096)
    row = SecurityCandidate(
        id=str(uuid4()), project_id=project_id, fingerprint=fingerprint,
        trace_event_id=trace.id if trace else feedback.trace_event_id,
        feedback_case_id=feedback.id if feedback else None,
        source_event_id=trace.event_id if trace else feedback.source_event_id,
        trace_id=trace.trace_id if trace else feedback.trace_id,
        source_received_at=trace.received_at if trace else None,
        provider=trace.provider if trace else feedback.provider,
        model=trace.model if trace else feedback.model,
        prompt_template_id=trace.prompt_template_id if trace else feedback.prompt_template_id,
        prompt_version_id=trace.prompt_version_id if trace else feedback.prompt_version_id,
        category=body.category, title=_sanitize(body.title, 200), prompt_text=prompt_text)
    db.add(row)
    audit(db, project_id, "security_candidate_created", row.id,
          details={"source_event_id": row.source_event_id, "feedback_case_id": row.feedback_case_id,
                   "source_input_included": bool(prompt_text)})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Candidate for this source/category already exists") from None
    return _view(row)


@router.get("")
async def list_candidates(project_id: str, request: Request,
                          state: Literal["draft", "in_review", "approved", "archived"] | None = None,
                          offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                          db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    filters = [SecurityCandidate.project_id == project_id]
    if state:
        filters.append(SecurityCandidate.state == state)
    total = await db.scalar(select(func.count()).select_from(SecurityCandidate).where(*filters))
    rows = (await db.execute(select(SecurityCandidate).where(*filters)
        .order_by(SecurityCandidate.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    return {"items": [_view(row) for row in rows], "total": total, "offset": offset, "limit": limit}


@router.get("/comparison")
async def compare_runs(project_id: str, request: Request,
                       candidate_ids: list[str] = Query(default=[]),
                       db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if not 1 <= len(candidate_ids) <= 20:
        raise HTTPException(422, "Select 1 to 20 candidates")
    rows = (await db.execute(select(SecurityCandidateRun, SecurityCandidateVersion,
                                    SecurityCandidate).join(
        SecurityCandidateVersion,
        SecurityCandidateRun.candidate_version_id == SecurityCandidateVersion.id).join(
        SecurityCandidate,
        SecurityCandidateVersion.candidate_id == SecurityCandidate.id).where(
        SecurityCandidateRun.project_id == project_id,
        SecurityCandidate.id.in_(candidate_ids))
        .order_by(SecurityCandidateRun.created_at.desc()).limit(100))).all()
    return [{"run_id": run.id, "candidate_id": candidate.id,
             "candidate_version": version.version, "category": candidate.category,
             "model": run.model, "provider": run.provider,
             "prompt_version_id": run.prompt_version_id,
             "status": run.status, "outcome": run.outcome,
             "classification": run.classification, "severity": run.severity,
             "score": (run.evidence or {}).get("score"),
             "created_at": run.created_at} for run, version, candidate in rows]


@router.get("/{candidate_id}")
async def get_candidate(project_id: str, candidate_id: str, request: Request,
                        include_body: bool = False,
                        x_redforge_sensitive_access: str | None = Header(default=None),
                        db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _candidate(db, project_id, candidate_id)
    if include_body:
        if x_redforge_sensitive_access != "allow":
            raise HTTPException(403, "Explicit sensitive-data access required")
        audit(db, project_id, "security_candidate_sensitive_read", row.id)
        await db.commit()
    return _view(row, include_body=include_body)


@router.put("/{candidate_id}")
async def edit_candidate(project_id: str, candidate_id: str, body: CandidateEdit,
                         request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _candidate(db, project_id, candidate_id)
    if row.state not in {"draft", "in_review"}:
        raise HTTPException(409, "Approved candidate is immutable")
    row.title = _sanitize(body.title, 200)
    row.prompt_text = _sanitize(body.prompt_text, 4096)
    audit(db, project_id, "security_candidate_edited", row.id)
    await db.commit()
    return _view(row)


@router.post("/{candidate_id}/review")
async def review_candidate(project_id: str, candidate_id: str, request: Request,
                           db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _candidate(db, project_id, candidate_id)
    if row.state != "draft" or not row.prompt_text:
        raise HTTPException(409, "Draft requires sanitized test prompt")
    row.state = "in_review"
    audit(db, project_id, "security_candidate_review", row.id)
    await db.commit()
    return _view(row)


@router.post("/{candidate_id}/approve")
async def approve_candidate(project_id: str, candidate_id: str, request: Request,
                            x_redforge_confirm_action: str | None = Header(default=None),
                            db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if x_redforge_confirm_action != "approve-security-candidate":
        raise HTTPException(403, "Explicit approval confirmation required")
    row = await _candidate(db, project_id, candidate_id)
    if row.state != "in_review" or not row.prompt_text:
        raise HTTPException(409, "Candidate must be reviewed before approval")
    snapshot = {"title": row.title, "prompt_text": _sanitize(row.prompt_text, 4096),
                "category": row.category, "source_event_id": row.source_event_id,
                "trace_id": row.trace_id, "provider": row.provider, "model": row.model,
                "prompt_template_id": row.prompt_template_id,
                "prompt_version_id": row.prompt_version_id,
                "source_received_at": row.source_received_at.isoformat() if row.source_received_at else None}
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    version = 1
    db.add(SecurityCandidateVersion(id=str(uuid4()), project_id=project_id,
        candidate_id=row.id, version=version, snapshot=snapshot,
        content_hash=hashlib.sha256(raw.encode()).hexdigest(), approved_by="local-operator"))
    row.approved_version = version
    row.state = "approved"
    audit(db, project_id, "security_candidate_approved", row.id,
          details={"version": version})
    await db.commit()
    return _view(row)


@router.post("/{candidate_id}/archive")
async def archive_candidate(project_id: str, candidate_id: str, request: Request,
                            x_redforge_confirm_action: str | None = Header(default=None),
                            db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if x_redforge_confirm_action != "archive-security-candidate":
        raise HTTPException(403, "Explicit archive confirmation required")
    row = await _candidate(db, project_id, candidate_id)
    if row.state == "archived":
        return _view(row)
    row.state = "archived"
    audit(db, project_id, "security_candidate_archived", row.id)
    await db.commit()
    return _view(row)


@router.post("/{candidate_id}/runs", status_code=202)
async def run_candidate(project_id: str, candidate_id: str, body: RunRequest,
                        request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _candidate(db, project_id, candidate_id)
    if row.state != "approved" or not row.approved_version:
        raise HTTPException(409, "Only approved candidates can run")
    from app.feedback_replay import local_runtime_ready
    if not local_runtime_ready():
        raise HTTPException(409, "Explicit local runtime required; no third-party attacks")
    version = (await db.execute(select(SecurityCandidateVersion).where(
        SecurityCandidateVersion.candidate_id == candidate_id,
        SecurityCandidateVersion.project_id == project_id,
        SecurityCandidateVersion.version == row.approved_version))).scalar_one_or_none()
    if version is None:
        raise HTTPException(409, "Approved snapshot missing")
    from app.config import settings
    if body.release_candidate and (body.release_candidate.model != body.model or
                                   body.release_candidate.provider != settings.RUNTIME_PROVIDER.lower()):
        raise HTTPException(422, "Release candidate model/provider must match actual local test")
    run = SecurityCandidateRun(id=str(uuid4()), project_id=project_id,
        candidate_version_id=version.id, environment=body.environment,
        model=body.model, provider=settings.RUNTIME_PROVIDER.lower(),
        prompt_version_id=version.snapshot.get("prompt_version_id"),
        config=body.model_dump(), status="pending")
    db.add(run)
    audit(db, project_id, "security_candidate_run_queued", run.id,
          details={"candidate_version_id": version.id})
    await db.commit()
    try:
        job = await job_service.submit(type="security_candidate_run", project_id=project_id,
            target_ref=candidate_id, max_attempts=1,
            params={"run_id": run.id, "environment": body.environment,
                    "timeout_seconds": body.timeout_seconds,
                    "max_output_tokens": body.max_output_tokens})
        run.job_id = job["id"] if isinstance(job, dict) else getattr(job, "id", None)
        await db.commit()
    except Exception:
        run.status = "failed"
        run.evidence = {"error": "Could not schedule local security run"}
        await db.commit()
        raise HTTPException(503, "Could not schedule local security run") from None
    return {"run_id": run.id, "job": job}


@router.get("/{candidate_id}/runs")
async def list_runs(project_id: str, candidate_id: str, request: Request,
                    limit: int = Query(50, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    await _candidate(db, project_id, candidate_id)
    rows = (await db.execute(select(SecurityCandidateRun).join(SecurityCandidateVersion,
        SecurityCandidateRun.candidate_version_id == SecurityCandidateVersion.id).where(
        SecurityCandidateRun.project_id == project_id,
        SecurityCandidateVersion.candidate_id == candidate_id)
        .order_by(SecurityCandidateRun.created_at.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "candidate_version_id": r.candidate_version_id,
             "environment": r.environment, "model": r.model, "provider": r.provider,
             "status": r.status, "outcome": r.outcome, "severity": r.severity,
             "classification": r.classification,
             "evidence": r.evidence, "remediation_status": r.remediation_status,
             "created_at": r.created_at, "completed_at": r.completed_at} for r in rows]


@router.get("/{candidate_id}/report")
async def security_report(project_id: str, candidate_id: str, request: Request,
                          model: str = Query(min_length=1, max_length=200),
                          db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    candidate = await _candidate(db, project_id, candidate_id)
    rows = (await db.execute(select(SecurityCandidateRun).join(SecurityCandidateVersion,
        SecurityCandidateRun.candidate_version_id == SecurityCandidateVersion.id).where(
        SecurityCandidateRun.project_id == project_id,
        SecurityCandidateVersion.candidate_id == candidate_id,
        SecurityCandidateRun.model == model,
        SecurityCandidateRun.status == "completed")
        .order_by(SecurityCandidateRun.created_at.desc()).limit(100))).scalars().all()
    if not rows:
        raise HTTPException(404, "No completed project security runs for model")
    from app.analysis.security_analyzer import AttackResult, analyze
    from app.analysis.report_builder import build_report
    results = [AttackResult(category=candidate.category, attack_name=candidate.title,
        severity=row.severity or "medium",
        verdict=("FAIL" if row.classification == "confirmed" and row.outcome == "detected"
                 else "UNCERTAIN" if row.outcome in {"detected", "uncertain"} else "PASS"),
        score=(row.evidence or {}).get("score") or 0,
        latency_ms=(row.evidence or {}).get("latency_ms")) for row in rows]
    analysis = analyze(model, results)
    report = build_report(model_name=model, profile_name="trace-driven-reviewed",
        model_overview={"provider": rows[0].provider, "candidate_id": candidate.id},
        analysis=analysis, findings=[],
        execution={"candidate_version": candidate.approved_version,
                   "source_event_id": candidate.source_event_id,
                   "run_ids": [row.id for row in rows],
                   "warning": "Heuristic detections are not confirmed exploitability"})
    return report.model_dump(mode="json")


@router.post("/{candidate_id}/runs/{run_id}/classify")
async def classify_run(project_id: str, candidate_id: str, run_id: str,
                       body: RunClassification, request: Request,
                       x_redforge_confirm_action: str | None = Header(default=None),
                       db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    await _candidate(db, project_id, candidate_id)
    if x_redforge_confirm_action != "classify-security-run":
        raise HTTPException(403, "Explicit finding classification required")
    run = (await db.execute(select(SecurityCandidateRun).join(SecurityCandidateVersion,
        SecurityCandidateRun.candidate_version_id == SecurityCandidateVersion.id).where(
        SecurityCandidateRun.id == run_id, SecurityCandidateRun.project_id == project_id,
        SecurityCandidateVersion.candidate_id == candidate_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Project security run not found")
    if run.status != "completed" or run.outcome != "detected":
        raise HTTPException(409, "Only detected completed behavior can be classified")
    if run.classification != "observed":
        raise HTTPException(409, "Classification is already recorded")
    run.classification = body.classification
    run.severity = body.severity if body.classification == "confirmed" else None
    run.remediation_status = body.remediation_status
    audit(db, project_id, "security_candidate_run_classified", run.id,
          details={"classification": run.classification, "severity": run.severity,
                   "justification": _sanitize(body.justification, 1000)})
    await db.commit()
    return {"id": run.id, "classification": run.classification,
            "severity": run.severity, "remediation_status": run.remediation_status}


@router.post("/{candidate_id}/runs/{run_id}/regression", status_code=201)
async def create_regression_case(project_id: str, candidate_id: str, run_id: str,
                                 request: Request,
                                 x_redforge_confirm_action: str | None = Header(default=None),
                                 db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if x_redforge_confirm_action != "create-security-regression":
        raise HTTPException(403, "Explicit regression-case confirmation required")
    candidate = await _candidate(db, project_id, candidate_id)
    run = (await db.execute(select(SecurityCandidateRun).join(SecurityCandidateVersion,
        SecurityCandidateRun.candidate_version_id == SecurityCandidateVersion.id).where(
        SecurityCandidateRun.id == run_id, SecurityCandidateRun.project_id == project_id,
        SecurityCandidateVersion.candidate_id == candidate_id))).scalar_one_or_none()
    if run is None or run.status != "completed" or run.outcome != "detected":
        raise HTTPException(409, "Detected completed run required")
    version = await db.get(SecurityCandidateVersion, run.candidate_version_id)
    prompt = (version.snapshot or {}).get("prompt_text") if version else None
    if not isinstance(prompt, str) or not prompt:
        raise HTTPException(409, "Approved test prompt unavailable")
    fingerprint = hashlib.sha256(f"{project_id}:security-run:{run_id}".encode()).hexdigest()
    existing = (await db.execute(select(FeedbackCase.id).where(
        FeedbackCase.project_id == project_id,
        FeedbackCase.fingerprint == fingerprint))).scalar_one_or_none()
    if existing:
        return {"case_id": existing, "already_exists": True}
    case = FeedbackCase(id=str(uuid4()), project_id=project_id,
        trace_event_id=candidate.trace_event_id, source_event_id=candidate.source_event_id,
        trace_id=candidate.trace_id, fingerprint=fingerprint,
        category="security_concern", state="draft", title=_sanitize(candidate.title, 200),
        prompt_text=_sanitize(prompt, 4096), labels=["security-regression"],
        notes=f"Derived from reviewed security run {run_id}; expected outcome not supplied.",
        provider=run.provider, model=run.model,
        prompt_template_id=candidate.prompt_template_id,
        prompt_version_id=candidate.prompt_version_id)
    db.add(case)
    audit(db, project_id, "security_regression_created", case.id,
          details={"security_run_id": run_id, "candidate_id": candidate_id})
    await db.commit()
    return {"case_id": case.id, "already_exists": False,
            "next_step": "Review expected outcome, then approve in feedback workflow"}
