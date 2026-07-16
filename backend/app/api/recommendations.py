"""Recommendation Engine API (RedForge V2, Phase 2.4).

Generate / list / accept / reject improvement recommendations. Additive router;
delegates to the isolated :mod:`app.recommendations` engine, which reads existing
security/training/dataset metadata. Nothing is downloaded or launched here — it
only suggests.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.recommendations import recommendation_service

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


class AnalyzeRequest(BaseModel):
    target_model: str = Field(..., min_length=1)
    run_id: Optional[str] = None
    project_id: Optional[str] = None
    source: str = "security"
    persist: bool = True


class DecisionRequest(BaseModel):
    status: str = Field(..., pattern="^(accepted|rejected|applied)$")


class OutcomeRequest(BaseModel):
    outcome: dict


class FeedbackRequest(BaseModel):
    applied_run_id: str


@router.post("/analyze")
async def analyze(req: AnalyzeRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Analyze a model's local metadata and return improvement recommendations."""
    return await recommendation_service.analyze(
        db, target_model=req.target_model, run_id=req.run_id,
        project_id=req.project_id, source=req.source, persist=req.persist,
    )


@router.get("")
async def list_recommendations(
    db: AsyncSession = Depends(get_db),
    project_id: Optional[str] = Query(None),
) -> list[dict]:
    return await recommendation_service.list(db, project_id=project_id)


@router.get("/accuracy")
async def accuracy(db: AsyncSession = Depends(get_db),
                   project_id: Optional[str] = Query(None)) -> dict:
    """Aggregate historical recommendation accuracy (declared before /{rec_id})."""
    return await recommendation_service.accuracy_summary(db, project_id=project_id)


@router.get("/{rec_id}")
async def get_recommendation(rec_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    r = await recommendation_service.get(db, rec_id)
    if r is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return r


@router.post("/{rec_id}/decision")
async def decide(rec_id: str, req: DecisionRequest, db: AsyncSession = Depends(get_db)) -> dict:
    r = await recommendation_service.decide(db, rec_id, req.status)
    if r is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return r


@router.post("/{rec_id}/outcome")
async def set_outcome(rec_id: str, req: OutcomeRequest, db: AsyncSession = Depends(get_db)) -> dict:
    r = await recommendation_service.set_outcome(db, rec_id, req.outcome)
    if r is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return r


@router.post("/{rec_id}/feedback")
async def record_feedback(rec_id: str, req: FeedbackRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Compare predicted vs actual improvement for the run that applied this
    recommendation and store accuracy (local prediction history)."""
    r = await recommendation_service.record_outcome(db, rec_id, req.applied_run_id)
    if r is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return r
