"""RedForge Assistant — HTTP transport.

Answering lives in :mod:`app.assistant`; this module only translates between
HTTP and that service. Keep it that way: the knowledge base, the answer chain
and the per-source follow-up suggestions all belong to the domain, not here.

Privacy: this endpoint never uploads user models, datasets, or conversations
anywhere. Optional web search (HuggingFace / GitHub / docs / ArXiv) is a
future, explicitly opt-in capability and is intentionally not enabled here.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import AssistantQuery, answer as answer_question
from app.assistant.knowledge import _SUGGESTIONS
from app.db.database import get_db

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AskRequest(BaseModel):
    question: str
    # Optional page/context hint so the retriever can be biased later (RAG-ready).
    context: str | None = None
    # Optional dataset to answer against, using ONLY its local cached metadata.
    dataset_id: Optional[str] = None
    # Optional training run to answer against, using ONLY local run metadata.
    run_id: Optional[str] = None
    # Optional recommendation to answer against, using ONLY its local payload.
    recommendation_id: Optional[str] = None
    # Optional project to scope benchmark answers, using ONLY local results.
    project_id: Optional[str] = None
    # Optional evaluation session to answer against, using ONLY its local results.
    session_id: Optional[str] = None


class Source(BaseModel):
    id: str
    title: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    suggestions: list[str]


@router.get("/suggestions")
async def suggestions() -> dict:
    return {"suggestions": _SUGGESTIONS}


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    result = await answer_question(
        db,
        AssistantQuery(
            question=req.question,
            context=req.context,
            dataset_id=req.dataset_id,
            run_id=req.run_id,
            recommendation_id=req.recommendation_id,
            project_id=req.project_id,
            session_id=req.session_id,
        ),
    )
    return AskResponse(
        answer=result.text,
        sources=[Source(id=s.id, title=s.title) for s in result.sources],
        suggestions=result.suggestions,
    )
