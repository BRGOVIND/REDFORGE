"""Primary evaluation API — the intelligent pipeline entry point.

``POST /api/evaluate`` is the one call a client needs: give it a model and a
profile and it creates a session, profiles the model, plans, executes
adaptively, analyzes, and builds a report. It returns immediately with a session
id (the heavy work runs in the background) so polling never 404s. The GET
endpoints expose the planner and analyzer outputs stored on the session.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.database import AsyncSessionLocal
from app.pipeline.evaluation_pipeline import EvaluationPipeline, PipelineError
from app.sessions.session_manager import SessionManager

router = APIRouter(tags=["evaluation-pipeline"])

# Default pipeline bound to the app's real session factory. Tests override the
# dependency to inject deterministic generate/judge/metadata functions.
_default_pipeline = EvaluationPipeline(AsyncSessionLocal)


def get_pipeline() -> EvaluationPipeline:
    return _default_pipeline


class EvaluateRequest(BaseModel):
    profile: str
    model: Optional[str] = None
    models: list[str] = Field(default_factory=list)

    def resolved_models(self) -> list[str]:
        if self.models:
            return self.models
        return [self.model] if self.model else []


class EvaluateResponse(BaseModel):
    session_id: str
    status: str
    profile: str
    models: list[str]


async def _load_session_metadata(session_id: str, manager: SessionManager):
    session = await manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return dict(session.session_metadata or {}), session


@router.post("/api/evaluate", response_model=EvaluateResponse)
async def evaluate(
    req: EvaluateRequest,
    background_tasks: BackgroundTasks,
    pipeline: EvaluationPipeline = Depends(get_pipeline),
) -> EvaluateResponse:
    models = req.resolved_models()
    try:
        session_id = await pipeline.create_session_shell(req.profile, models)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Heavy work (profile -> plan -> execute -> analyze -> report) runs in the
    # background; the session is already durably persisted.
    background_tasks.add_task(pipeline.run, session_id)

    return EvaluateResponse(
        session_id=session_id, status="pending", profile=req.profile, models=models,
    )


def _manager_for(pipeline: EvaluationPipeline) -> SessionManager:
    return SessionManager(pipeline.session_factory)


@router.get("/api/plans/{session_id}")
async def get_plan(
    session_id: str,
    pipeline: EvaluationPipeline = Depends(get_pipeline),
) -> dict:
    meta, session = await _load_session_metadata(session_id, _manager_for(pipeline))
    plan = meta.get("evaluation_plan")
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not generated yet")
    return {"session_id": session_id, "stage": meta.get("stage"), "plan": plan}


@router.get("/api/findings/{session_id}")
async def get_findings(
    session_id: str,
    pipeline: EvaluationPipeline = Depends(get_pipeline),
) -> dict:
    meta, session = await _load_session_metadata(session_id, _manager_for(pipeline))
    if "analyses" not in meta and not meta.get("findings"):
        raise HTTPException(status_code=404, detail="Findings not available yet")
    return {
        "session_id": session_id,
        "stage": meta.get("stage"),
        "findings": meta.get("findings", []),
        "analyses": meta.get("analyses", {}),
        "leaderboard": meta.get("leaderboard"),
    }


@router.get("/api/report/{session_id}")
async def get_report(
    session_id: str,
    pipeline: EvaluationPipeline = Depends(get_pipeline),
) -> dict:
    meta, session = await _load_session_metadata(session_id, _manager_for(pipeline))
    report = meta.get("report")
    if report is None:
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return {"session_id": session_id, "report": report}
