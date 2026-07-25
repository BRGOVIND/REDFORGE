"""Evaluation Workbench API (RedForge V2 Phase 4).

Collections → Prompt Sets → Prompts (version-tracked), plus Evaluation Sessions
that run prompt sets against selected models through the async queue. Additive;
delegates to :mod:`app.evaluation`. Mounted at ``/api/evaluation-workbench``.

Route order: literal paths are declared before parameterized ones, and each
resource lives under a distinct prefix (``/collections``, ``/prompt-sets``,
``/prompts``, ``/sessions``) so none shadow each other.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.evaluation import (
    REGRESSION_TYPES,
    evaluation_sessions,
    evaluation_workbench,
    golden_comparator,
    list_similarity,
)
from app.runtime_registry import runtime_registry

router = APIRouter(prefix="/api/evaluation-workbench", tags=["evaluation-workbench"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    project_id: Optional[str] = None
    category: str = "custom"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class PromptSetCreate(BaseModel):
    collection_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    category: str = "custom"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    priority: str = "normal"
    owner: str = ""
    project_id: Optional[str] = None


class PromptSetUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    priority: Optional[str] = None
    owner: Optional[str] = None


class PromptCreate(BaseModel):
    prompt_set_id: str
    prompt: str = Field(..., min_length=1)
    title: str = ""
    system_prompt: str = ""
    context: str = ""
    expected_behavior: str = ""
    expected_output: str = ""
    golden_response: str = ""
    acceptance_criteria: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    priority: str = "normal"
    difficulty: str = "normal"
    notes: str = ""


class PromptUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    system_prompt: Optional[str] = None
    context: Optional[str] = None
    expected_behavior: Optional[str] = None
    expected_output: Optional[str] = None
    golden_response: Optional[str] = None
    acceptance_criteria: Optional[dict] = None
    tags: Optional[list[str]] = None
    priority: Optional[str] = None
    difficulty: Optional[str] = None
    notes: Optional[str] = None
    enabled: Optional[bool] = None
    version_note: str = ""


class SessionCreate(BaseModel):
    prompt_set_ids: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)          # raw model names
    registry_ids: list[str] = Field(default_factory=list)    # registered checkpoints
    project_id: Optional[str] = None
    run_id: Optional[str] = None
    name: str = ""
    similarity: str = "text"
    config: dict = Field(default_factory=dict)


class DiffRequest(BaseModel):
    reference: str = ""
    candidate: str = ""


async def _resolve_targets(db: AsyncSession, models: list[str], registry_ids: list[str],
                           project_id: Optional[str]) -> list[dict]:
    """Expand raw names + registry ids + whole-project into concrete model targets."""
    provider = settings.RUNTIME_PROVIDER.lower()
    targets: list[dict] = []
    seen: set[str] = set()

    def add(target_model: str, **extra):
        key = f"{extra.get('registry_id') or ''}|{target_model}"
        if key in seen or not target_model:
            return
        seen.add(key)
        targets.append({"target_model": target_model, **extra})

    for name in models:
        add(name, provider=provider, runtime=provider, label=name)
    for rid in registry_ids:
        m = await runtime_registry.get(db, rid)
        if m is not None:
            add(m["runtime_model"], registry_id=m["id"], provider=m.get("provider") or provider,
                runtime=m.get("provider") or provider, label=m.get("label"))
    if project_id and not models and not registry_ids:
        for m in await runtime_registry.list(db, project_id=project_id):
            add(m["runtime_model"], registry_id=m["id"], provider=m.get("provider") or provider,
                runtime=m.get("provider") or provider, label=m.get("label"))
        from app.db.models import Project
        proj = await db.get(Project, project_id)
        if proj is not None:
            for name in (proj.models or []):
                add(name, provider=provider, runtime=provider, label=name)
    return targets


# ---------------------------------------------------------------------------
# Top-level literal routes
# ---------------------------------------------------------------------------

@router.get("/similarity-providers")
async def similarity_providers() -> list[dict]:
    return list_similarity()


@router.get("/regression-types")
async def regression_types() -> list[dict]:
    return [{"type": k, "label": v} for k, v in REGRESSION_TYPES.items()]


@router.get("/queue")
async def queue() -> dict:
    return evaluation_sessions.queue_status()


@router.post("/diff")
async def diff(req: DiffRequest) -> dict:
    return golden_comparator.compare(req.reference, req.candidate)


@router.get("/compare")
async def compare(ids: str = Query(..., description="comma-separated result ids")) -> dict:
    id_list = [i for i in ids.split(",") if i]
    if not id_list:
        raise HTTPException(status_code=400, detail="no ids provided")
    return await evaluation_sessions.compare_results(id_list)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

@router.get("/collections")
async def list_collections(project_id: Optional[str] = Query(None)) -> list[dict]:
    return await evaluation_workbench.list_collections(project_id=project_id)


@router.post("/collections", status_code=201)
async def create_collection(req: CollectionCreate) -> dict:
    return await evaluation_workbench.create_collection(**req.model_dump())


@router.get("/collections/{cid}")
async def get_collection(cid: str) -> dict:
    c = await evaluation_workbench.get_collection(cid)
    if c is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return c


@router.patch("/collections/{cid}")
async def update_collection(cid: str, req: CollectionUpdate) -> dict:
    c = await evaluation_workbench.update_collection(cid, **req.model_dump(exclude_none=True))
    if c is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return c


@router.delete("/collections/{cid}")
async def delete_collection(cid: str) -> dict:
    ok = await evaluation_workbench.delete_collection(cid)
    if not ok:
        raise HTTPException(status_code=404, detail="collection not found")
    return {"deleted": True, "id": cid}


# ---------------------------------------------------------------------------
# Prompt sets
# ---------------------------------------------------------------------------

@router.get("/prompt-sets")
async def list_prompt_sets(collection_id: Optional[str] = Query(None),
                           project_id: Optional[str] = Query(None)) -> list[dict]:
    return await evaluation_workbench.list_prompt_sets(
        collection_id=collection_id, project_id=project_id)


@router.post("/prompt-sets", status_code=201)
async def create_prompt_set(req: PromptSetCreate) -> dict:
    s = await evaluation_workbench.create_prompt_set(**req.model_dump())
    if s is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return s


@router.get("/prompt-sets/{sid}")
async def get_prompt_set(sid: str) -> dict:
    s = await evaluation_workbench.get_prompt_set(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="prompt set not found")
    return s


@router.patch("/prompt-sets/{sid}")
async def update_prompt_set(sid: str, req: PromptSetUpdate) -> dict:
    s = await evaluation_workbench.update_prompt_set(sid, **req.model_dump(exclude_none=True))
    if s is None:
        raise HTTPException(status_code=404, detail="prompt set not found")
    return s


@router.delete("/prompt-sets/{sid}")
async def delete_prompt_set(sid: str) -> dict:
    ok = await evaluation_workbench.delete_prompt_set(sid)
    if not ok:
        raise HTTPException(status_code=404, detail="prompt set not found")
    return {"deleted": True, "id": sid}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@router.post("/prompts", status_code=201)
async def create_prompt(req: PromptCreate) -> dict:
    p = await evaluation_workbench.create_prompt(**req.model_dump())
    if p is None:
        raise HTTPException(status_code=404, detail="prompt set not found")
    return p


@router.get("/prompts/{pid}")
async def get_prompt(pid: str) -> dict:
    p = await evaluation_workbench.get_prompt(pid)
    if p is None:
        raise HTTPException(status_code=404, detail="prompt not found")
    return p


@router.patch("/prompts/{pid}")
async def update_prompt(pid: str, req: PromptUpdate) -> dict:
    p = await evaluation_workbench.update_prompt(pid, **req.model_dump(exclude_none=True))
    if p is None:
        raise HTTPException(status_code=404, detail="prompt not found")
    return p


@router.delete("/prompts/{pid}")
async def delete_prompt(pid: str) -> dict:
    ok = await evaluation_workbench.delete_prompt(pid)
    if not ok:
        raise HTTPException(status_code=404, detail="prompt not found")
    return {"deleted": True, "id": pid}


@router.get("/prompts/{pid}/versions")
async def prompt_versions(pid: str) -> list[dict]:
    return await evaluation_workbench.prompt_versions(pid)


@router.get("/prompts/{pid}/versions/compare")
async def compare_prompt_versions(pid: str, a: int = Query(...), b: int = Query(...)) -> dict:
    cmp = await evaluation_workbench.compare_prompt_versions(pid, a, b)
    if cmp is None:
        raise HTTPException(status_code=404, detail="prompt version(s) not found")
    return cmp


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(project_id: Optional[str] = Query(None),
                        run_id: Optional[str] = Query(None),
                        limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    return await evaluation_sessions.history(project_id=project_id, run_id=run_id, limit=limit)


@router.post("/sessions", status_code=201)
async def create_session(req: SessionCreate, db: AsyncSession = Depends(get_db)) -> dict:
    if not req.prompt_set_ids:
        raise HTTPException(status_code=400, detail="no prompt sets selected")
    targets = await _resolve_targets(db, req.models, req.registry_ids, req.project_id)
    if not targets:
        raise HTTPException(status_code=400, detail="no models resolved")
    return await evaluation_sessions.schedule(
        models=targets, prompt_set_ids=req.prompt_set_ids, project_id=req.project_id,
        run_id=req.run_id, name=req.name, similarity=req.similarity, config=req.config)


@router.get("/sessions/{sid}")
async def get_session(sid: str) -> dict:
    s = await evaluation_sessions.get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return s


@router.delete("/sessions/{sid}")
async def cancel_session(sid: str) -> dict:
    await evaluation_sessions.cancel(sid)
    return {"cancelled": True, "id": sid}


@router.get("/sessions/{sid}/results")
async def session_results(sid: str, verdict: Optional[str] = Query(None),
                          regression_type: Optional[str] = Query(None)) -> list[dict]:
    return await evaluation_sessions.results(sid, verdict=verdict, regression_type=regression_type)


@router.get("/sessions/{sid}/regressions")
async def session_regressions(sid: str) -> dict:
    return await evaluation_sessions.regressions(sid)
