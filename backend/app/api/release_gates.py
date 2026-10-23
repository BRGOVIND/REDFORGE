"""Local, versioned release policies and evidence-backed gate reports."""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.db.database import get_db
from app.db.models import (Project, Prompt, PromptSet, PromptVersion, ReleaseGateDecision,
                           ReleaseGatePolicy)
from app.observability_privacy import _scrub, audit
from app.release_gates import (CandidateIdentity, EvidenceSelection, GateRules,
                               evaluate_gate)

router = APIRouter(prefix="/api/projects/{project_id}/release-gates", tags=["release-gates"])


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=80)
    rules: GateRules


class GateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: CandidateIdentity
    baseline: CandidateIdentity | None = None
    evidence: EvidenceSelection = Field(default_factory=EvidenceSelection)
    dry_run: bool = True


class OverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1, max_length=120)
    justification: str = Field(min_length=10, max_length=1000)


async def _project(db: AsyncSession, project_id: str, request: Request) -> None:
    _local(request)
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


async def _policy(db: AsyncSession, project_id: str, policy_id: str) -> ReleaseGatePolicy:
    row = (await db.execute(select(ReleaseGatePolicy).where(
        ReleaseGatePolicy.id == policy_id,
        ReleaseGatePolicy.project_id == project_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Project release policy not found")
    return row


async def _decision(db: AsyncSession, project_id: str, decision_id: str) -> ReleaseGateDecision:
    row = (await db.execute(select(ReleaseGateDecision).where(
        ReleaseGateDecision.id == decision_id,
        ReleaseGateDecision.project_id == project_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Project gate decision not found")
    return row


def _policy_view(row: ReleaseGatePolicy) -> dict:
    return {"id": row.id, "project_id": row.project_id, "name": row.name,
            "environment": row.environment, "version": row.version,
            "rules": row.rules, "created_at": row.created_at}


def _decision_view(row: ReleaseGateDecision) -> dict:
    return {"format": "redforge.release-gate/1", "id": row.id,
            "project_id": row.project_id, "policy_id": row.policy_id,
            "policy_version": row.policy_version, "candidate": row.candidate,
            "baseline": row.baseline, "evidence_ids": row.evidence_ids,
            "checks": row.checks, "outcome": row.outcome,
            "effective_outcome": "pass" if row.override_actor else row.outcome,
            "dry_run": row.dry_run,
            "override": {"actor": row.override_actor,
                         "justification": row.override_justification,
                         "at": row.override_at} if row.override_actor else None,
            "created_at": row.created_at,
            "deployment_performed": False}


@router.post("/policies", status_code=201)
async def create_policy(project_id: str, body: PolicyCreate, request: Request,
                        db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    existing = (await db.execute(select(ReleaseGatePolicy).where(
        ReleaseGatePolicy.project_id == project_id,
        ReleaseGatePolicy.name == body.name,
        ReleaseGatePolicy.environment == body.environment)
        .order_by(ReleaseGatePolicy.version.desc()).limit(1))).scalar_one_or_none()
    row = ReleaseGatePolicy(id=str(uuid4()), project_id=project_id,
        name=body.name, environment=body.environment,
        version=(existing.version + 1 if existing else 1), rules=body.rules.model_dump())
    db.add(row)
    audit(db, project_id, "release_policy_published", row.id,
          details={"name": row.name, "environment": row.environment, "version": row.version})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Concurrent policy version published; retry") from None
    return _policy_view(row)


@router.get("/policies")
async def list_policies(project_id: str, request: Request,
                        limit: int = Query(50, ge=1, le=100),
                        db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    rows = (await db.execute(select(ReleaseGatePolicy).where(
        ReleaseGatePolicy.project_id == project_id)
        .order_by(ReleaseGatePolicy.created_at.desc()).limit(limit))).scalars().all()
    return [_policy_view(row) for row in rows]


@router.post("/policies/{policy_id}/evaluate")
async def evaluate_policy(project_id: str, policy_id: str, body: GateEvaluation,
                          request: Request, db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    policy = await _policy(db, project_id, policy_id)
    result = await evaluate_gate(db, project_id=project_id, policy=policy,
        candidate=body.candidate, evidence=body.evidence, baseline=body.baseline)
    row = ReleaseGateDecision(id=str(uuid4()), project_id=project_id,
        policy_id=policy.id, policy_version=policy.version,
        candidate=body.candidate.model_dump(),
        baseline=body.baseline.model_dump() if body.baseline else None,
        evidence_ids={"selected": body.evidence.model_dump(),
                      "accepted": result["accepted_evidence_ids"],
                      "rejected": result["rejected_evidence_ids"]},
        checks=result["checks"], outcome=result["outcome"], dry_run=body.dry_run)
    db.add(row)
    audit(db, project_id, "release_gate_evaluated", row.id,
          details={"outcome": row.outcome, "dry_run": row.dry_run,
                   "policy_id": policy.id, "policy_version": policy.version})
    await db.commit()
    return _decision_view(row)


@router.get("/decisions")
async def list_decisions(project_id: str, request: Request,
                         limit: int = Query(50, ge=1, le=100),
                         db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    rows = (await db.execute(select(ReleaseGateDecision).where(
        ReleaseGateDecision.project_id == project_id)
        .order_by(ReleaseGateDecision.created_at.desc()).limit(limit))).scalars().all()
    return [_decision_view(row) for row in rows]


@router.get("/decisions/{decision_id}")
async def get_decision(project_id: str, decision_id: str, request: Request,
                       db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    return _decision_view(await _decision(db, project_id, decision_id))


@router.post("/decisions/{decision_id}/override")
async def override_decision(project_id: str, decision_id: str,
                            body: OverrideRequest, request: Request,
                            x_redforge_confirm_action: str | None = Header(default=None),
                            db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    if x_redforge_confirm_action != "override-release-gate":
        raise HTTPException(403, "Explicit release override confirmation required")
    row = await _decision(db, project_id, decision_id)
    if row.dry_run:
        raise HTTPException(409, "Dry-run decision cannot be overridden")
    if row.override_actor:
        raise HTTPException(409, "Decision already overridden")
    if row.outcome == "pass":
        raise HTTPException(409, "Passing decision needs no override")
    from datetime import datetime, timezone
    row.override_actor = _scrub(body.actor, 120)
    row.override_justification = _scrub(body.justification, 1000)
    row.override_at = datetime.now(timezone.utc)
    audit(db, project_id, "release_gate_overridden", row.id,
          details={"actor": row.override_actor, "original_outcome": row.outcome,
                   "justification": row.override_justification})
    await db.commit()
    return _decision_view(row)


@router.get("/decisions/{decision_id}/rollback-plan")
async def rollback_plan(project_id: str, decision_id: str, request: Request,
                        target_version: int = Query(ge=1),
                        db: AsyncSession = Depends(get_db)):
    await _project(db, project_id, request)
    row = await _decision(db, project_id, decision_id)
    candidate = CandidateIdentity.model_validate(row.candidate)
    if candidate.artifact_type != "prompt":
        raise HTTPException(409, "Only versioned prompt rollback is supported")
    prompt = (await db.execute(select(Prompt).join(Prompt.prompt_set).where(
        Prompt.id == candidate.artifact_id,
        PromptSet.project_id == project_id))).scalar_one_or_none()
    if prompt is None or prompt.archived_at:
        raise HTTPException(404, "Active project prompt not found")
    target = (await db.execute(select(PromptVersion).where(
        PromptVersion.prompt_id == prompt.id,
        PromptVersion.version == target_version))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "Rollback target version not found")
    if target_version == prompt.active_version:
        raise HTTPException(409, "Target version already active")
    return {"status": "recommended_only", "executed": False,
            "prompt_id": prompt.id, "current_version": prompt.active_version,
            "target_version": target_version,
            "activation_endpoint": f"/api/v1/projects/{project_id}/prompt-registry/{prompt.id}/activate/{target_version}",
            "warning": "Activation changes active prompt; it never deletes traces, tests, or audit history"}
