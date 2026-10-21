"""Production trace feedback to reviewed, versioned, local evaluation cases."""
from __future__ import annotations

import hashlib
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.db.database import get_db
from app.db.models import (Dataset, DatasetVersion, FeedbackCase, Project, Prompt,
                           PromptSet, TraceEvent)
from app.evaluation.versioning import prompt_version_service
from app.jobs import job_service
from app.observability_privacy import _scrub, audit, get_policy

router = APIRouter(prefix="/api/projects/{project_id}/feedback", tags=["feedback"])
Category = Literal["incorrect_output", "hallucination", "tool_failure", "policy_violation",
                   "latency_regression", "security_concern"]


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    category: Category
    title: str = Field(min_length=1, max_length=200)
    include_captured_input: bool = False


class AcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_similarity: float | None = Field(default=None, ge=0, le=100)
    must_include: list[str] = Field(default_factory=list, max_length=20)
    must_exclude: list[str] = Field(default_factory=list, max_length=20)
    require_json: bool = False


class CaseEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    labels: list[str] = Field(default_factory=list, max_length=12)
    prompt_text: str | None = Field(default=None, max_length=4096)
    expected_output: str | None = Field(default=None, max_length=4096)
    acceptance_criteria: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)


class StateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["in_review", "rejected", "archived"]


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_set_id: str


class ReplayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["local_evaluation"]
    candidate_model: str = Field(min_length=1, max_length=200)
    baseline_model: str | None = Field(default=None, max_length=200)
    timeout_seconds: int = Field(default=30, ge=1, le=60)
    max_calls: int = Field(default=2, ge=1, le=2)
    max_external_cost_usd: float = Field(default=0, ge=0, le=0)


async def _project(db: AsyncSession, project_id: str, request: Request) -> None:
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


async def _case(db: AsyncSession, project_id: str, case_id: str) -> FeedbackCase:
    row = (await db.execute(select(FeedbackCase).where(FeedbackCase.project_id == project_id,
        FeedbackCase.id == case_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Feedback case not found")
    return row


def _safe_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    try:
        return _scrub(value, limit)
    except Exception:
        raise HTTPException(422, "Could not sanitize text") from None


def _view(c: FeedbackCase, *, include_bodies: bool = False) -> dict:
    out = {k: getattr(c, k) for k in ("id", "project_id", "trace_event_id", "source_event_id", "trace_id", "category",
        "state", "labels", "title", "notes", "prompt_text", "expected_output", "acceptance_criteria",
        "provider", "model", "prompt_template_id", "prompt_version_id", "dataset_id", "dataset_version",
        "evaluation_prompt_id", "created_at", "updated_at")}
    if not include_bodies:
        out["prompt_text"] = None
        out["expected_output"] = None
        out["notes"] = None
    return out


@router.post("/cases", status_code=201)
async def create_case(project_id: str, body: CaseCreate, request: Request,
                      x_redforge_sensitive_access: str | None = Header(default=None),
                      x_redforge_confirm_action: str | None = Header(default=None),
                      db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    trace = (await db.execute(select(TraceEvent).where(TraceEvent.project_id == project_id,
        TraceEvent.event_id == body.event_id))).scalar_one_or_none()
    if trace is None:
        raise HTTPException(404, "Trace not found")
    fingerprint = hashlib.sha256(f"{project_id}:{trace.event_id}:{body.category}".encode()).hexdigest()
    prior = (await db.execute(select(FeedbackCase.id).where(FeedbackCase.project_id == project_id,
        FeedbackCase.fingerprint == fingerprint))).scalar_one_or_none()
    if prior:
        raise HTTPException(409, f"Case already exists: {prior}")
    prompt_text = None
    if body.include_captured_input:
        if x_redforge_sensitive_access != "allow" or x_redforge_confirm_action != "include-captured-input":
            raise HTTPException(403, "Explicit sensitive-data access and confirmation headers required")
        policy = await get_policy(db, project_id)
        if not policy.telemetry_enabled or not policy.capture_input or not trace.input_text:
            raise HTTPException(409, "Captured input unavailable under project privacy policy")
        prompt_text = _safe_text(trace.input_text, 4096)
    row = FeedbackCase(id=str(uuid4()), project_id=project_id, trace_event_id=trace.id,
        source_event_id=trace.event_id,
        trace_id=trace.trace_id, fingerprint=fingerprint, category=body.category,
        title=_safe_text(body.title, 200), prompt_text=prompt_text,
        provider=trace.provider, model=trace.model,
        prompt_template_id=trace.prompt_template_id, prompt_version_id=trace.prompt_version_id)
    db.add(row)
    audit(db, project_id, "feedback_case_created", row.id,
          details={"trace_event_id": trace.id, "captured_input_included": bool(prompt_text)})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Case already exists") from None
    return _view(row)


@router.get("/cases")
async def list_cases(project_id: str, request: Request, state: str | None = None,
                     offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                     db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if state and state not in {"draft", "in_review", "approved", "rejected", "archived"}:
        raise HTTPException(422, "Invalid case state")
    filters = [FeedbackCase.project_id == project_id]
    if state:
        filters.append(FeedbackCase.state == state)
    total = await db.scalar(select(func.count()).select_from(FeedbackCase).where(*filters))
    rows = (await db.execute(select(FeedbackCase).where(*filters)
        .order_by(FeedbackCase.created_at.desc()).offset(offset).limit(limit))).scalars().all()
    return {"items": [_view(c) for c in rows], "total": total, "offset": offset, "limit": limit}


@router.get("/cases/{case_id}")
async def get_case(project_id: str, case_id: str, request: Request,
                   include_bodies: bool = False,
                   x_redforge_sensitive_access: str | None = Header(default=None),
                   db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    c = await _case(db, project_id, case_id)
    if include_bodies:
        if x_redforge_sensitive_access != "allow":
            raise HTTPException(403, "Explicit sensitive-data access header required")
        audit(db, project_id, "feedback_case_sensitive_read", c.id)
        await db.commit()
    return _view(c, include_bodies=include_bodies)


@router.put("/cases/{case_id}")
async def edit_case(project_id: str, case_id: str, body: CaseEdit, request: Request,
                    db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    c = await _case(db, project_id, case_id)
    if c.state not in {"draft", "in_review"}:
        raise HTTPException(409, "Only draft or in-review cases can be edited")
    if any(len(label) > 40 for label in body.labels):
        raise HTTPException(422, "Labels must be at most 40 characters")
    if any(len(x) > 200 for x in body.acceptance_criteria.must_include + body.acceptance_criteria.must_exclude):
        raise HTTPException(422, "Criterion text too long")
    c.title = _safe_text(body.title, 200)
    c.notes = _safe_text(body.notes, 2000)
    c.labels = [_safe_text(x, 40) for x in body.labels]
    c.prompt_text = _safe_text(body.prompt_text, 4096)
    c.expected_output = _safe_text(body.expected_output, 4096)
    c.acceptance_criteria = {"min_similarity": body.acceptance_criteria.min_similarity,
        "must_include": [_safe_text(x, 200) for x in body.acceptance_criteria.must_include],
        "must_exclude": [_safe_text(x, 200) for x in body.acceptance_criteria.must_exclude],
        "require_json": body.acceptance_criteria.require_json}
    audit(db, project_id, "feedback_case_edited", c.id)
    await db.commit()
    return _view(c)


@router.post("/cases/{case_id}/state")
async def set_case_state(project_id: str, case_id: str, body: StateIn, request: Request,
                         db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    c = await _case(db, project_id, case_id)
    if c.state == "approved":
        raise HTTPException(409, "Approved history is immutable")
    if c.state == "archived" or (body.state == "in_review" and c.state != "draft"):
        raise HTTPException(409, "Invalid review transition")
    c.state = body.state
    audit(db, project_id, "feedback_case_state", c.id, details={"state": c.state})
    await db.commit()
    return _view(c)


@router.post("/cases/{case_id}/approve")
async def approve_case(project_id: str, case_id: str, body: ApproveIn, request: Request,
                       db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    c = await _case(db, project_id, case_id)
    if c.state != "in_review":
        raise HTTPException(409, "Case must be reviewed before approval")
    if not c.prompt_text:
        raise HTTPException(422, "A sanitized test prompt is required")
    prompt_set = (await db.execute(select(PromptSet).where(PromptSet.id == body.prompt_set_id,
        PromptSet.project_id == project_id))).scalar_one_or_none()
    if prompt_set is None:
        raise HTTPException(404, "Project prompt set not found")
    dataset = (await db.execute(select(Dataset).where(Dataset.project_id == project_id,
        Dataset.source_format == "feedback", Dataset.name == "Production feedback"))).scalar_one_or_none()
    if dataset is None:
        dataset = Dataset(id=str(uuid4()), project_id=project_id, name="Production feedback",
                          source_format="feedback", kind="records", columns=["case_id", "prompt_id"],
                          record_count=0, current_version=0, dataset_metadata={"type": "feedback_manifest"})
        db.add(dataset)
        records = []
    else:
        latest = (await db.execute(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id,
            DatasetVersion.version == dataset.current_version))).scalar_one_or_none()
        records = list(latest.records or []) if latest else []
    if len(records) >= 1000:
        raise HTTPException(409, "Feedback dataset reached its 1000-case safety limit")
    p = Prompt(id=str(uuid4()), prompt_set_id=prompt_set.id, title=c.title,
        prompt=c.prompt_text, expected_output=c.expected_output or "",
        acceptance_criteria=c.acceptance_criteria or {}, tags=c.labels or [],
        notes=f"Feedback case {c.id}; source event {c.source_event_id}",
        description=c.category, author="local-operator", current_version=1, active_version=1)
    db.add(p)
    await prompt_version_service.snapshot(db, p, note=f"Approved feedback case {c.id}")
    version = (dataset.current_version or 0) + 1
    records.append({"case_id": c.id, "prompt_id": p.id, "source_event_id": c.source_event_id})
    db.add(DatasetVersion(dataset_id=dataset.id, version=version, records=records,
                          record_count=len(records), note=f"Approved case {c.id}"))
    dataset.current_version = version
    dataset.record_count = len(records)
    c.state = "approved"
    c.dataset_id = dataset.id
    c.dataset_version = version
    c.evaluation_prompt_id = p.id
    audit(db, project_id, "feedback_case_approved", c.id,
          details={"prompt_id": p.id, "dataset_id": dataset.id, "dataset_version": version})
    await db.commit()
    return _view(c)


@router.post("/cases/{case_id}/replay", status_code=202)
async def replay_case(project_id: str, case_id: str, body: ReplayIn, request: Request,
                      db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    c = await _case(db, project_id, case_id)
    if c.state != "approved" or not c.evaluation_prompt_id:
        raise HTTPException(409, "Only approved cases can be replayed")
    if body.baseline_model and body.max_calls < 2:
        raise HTTPException(422, "Baseline comparison requires two calls")
    from app.feedback_replay import local_runtime_ready
    if not local_runtime_ready():
        raise HTTPException(409, "Replay requires an explicitly selected local runtime provider")
    return await job_service.submit(type="feedback_replay", project_id=project_id,
        target_ref=case_id, max_attempts=1,
        params={"case_id": case_id, "environment": body.environment,
                "candidate_model": body.candidate_model, "baseline_model": body.baseline_model,
                "timeout_seconds": body.timeout_seconds, "max_calls": body.max_calls})
