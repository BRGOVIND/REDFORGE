"""Versioned prompt workflows on the Evaluation Workbench's existing prompt tables."""
from __future__ import annotations

import re
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.traces import _local
from app.db.database import get_db
from app.db.models import EvaluationResult, Project, Prompt, PromptSet, PromptVersion, TraceEvent, WorkbenchSession
from app.evaluation.versioning import prompt_version_service, snapshot_of
from app.observability_privacy import audit

router = APIRouter(prefix="/api/v1/projects/{project_id}/prompt-registry", tags=["prompt-registry"])
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_PLACEHOLDER = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")


class Variable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=64)
    type: Literal["string", "integer", "number", "boolean"] = "string"
    required: bool = True
    default: str | int | float | bool | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("Use an identifier such as customer_name")
        return value

    @model_validator(mode="after")
    def valid_default(self):
        if self.default is not None and not _validate_value(self, self.default):
            raise ValueError(f"Default for {self.name} must be {self.type}")
        return self


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=32_000)
    system_prompt: str = Field(default="", max_length=32_000)
    context: str = Field(default="", max_length=32_000)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    variables_schema: list[Variable] = Field(default_factory=list, max_length=32)
    expected_behavior: str = Field(default="", max_length=32_000)
    expected_output: str = Field(default="", max_length=32_000)
    golden_response: str = Field(default="", max_length=32_000)
    acceptance_criteria: dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"
    difficulty: str = "normal"
    notes: str = Field(default="", max_length=2000)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_template(self):
        if any(len(tag) > 80 or not tag.strip() for tag in self.tags):
            raise ValueError("Tags must be non-empty and at most 80 characters")
        if len(json.dumps(self.acceptance_criteria).encode("utf-8")) > 4096:
            raise ValueError("Acceptance criteria exceed 4 KiB")
        names = [x.name for x in self.variables_schema]
        if len(names) != len(set(names)):
            raise ValueError("Variable names must be unique")
        for body in (self.prompt, self.system_prompt, self.context):
            remaining = _PLACEHOLDER.sub("", body)
            if "{{" in remaining or "}}" in remaining:
                raise ValueError("Only simple {{ variable_name }} placeholders are supported")
            missing = {x.group(1) for x in _PLACEHOLDER.finditer(body)} - set(names)
            if missing:
                raise ValueError("Missing variable definitions: " + ", ".join(sorted(missing)))
        return self


class RegistryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_set_id: str
    definition: Definition
    author: str = Field(default="", max_length=120)


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: Definition
    author: str = Field(default="", max_length=120)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=120)


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_set_id: str
    definition: dict[str, Any]
    confirm_existing: bool = False
    author: str = Field(default="", max_length=120)


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variables: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, ge=1)


def _validate_value(variable: Variable, value: Any) -> bool:
    return {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
    }[variable.type](value)


def render(definition: Definition, values: dict[str, Any]) -> dict[str, str]:
    allowed = {v.name: v for v in definition.variables_schema}
    extra = set(values) - set(allowed)
    if extra:
        raise HTTPException(422, "Unknown variables: " + ", ".join(sorted(extra)))
    resolved: dict[str, str] = {}
    for name, variable in allowed.items():
        value = values.get(name, variable.default)
        if value is None:
            if variable.required:
                raise HTTPException(422, f"Missing variable: {name}")
            value = ""
        if not _validate_value(variable, value):
            raise HTTPException(422, f"Invalid {name}: expected {variable.type}")
        resolved[name] = str(value).lower() if isinstance(value, bool) else str(value)
    return {key: _PLACEHOLDER.sub(lambda match: resolved[match.group(1)], getattr(definition, key))
            for key in ("prompt", "system_prompt", "context")}


async def _prompt(db: AsyncSession, project_id: str, prompt_id: str) -> Prompt:
    row = (await db.execute(select(Prompt).join(PromptSet).where(
        Prompt.id == prompt_id, PromptSet.project_id == project_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Prompt not found in project")
    return row


async def _project(db: AsyncSession, project_id: str) -> None:
    if await db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")


def _definition(row: Prompt) -> dict[str, Any]:
    data = snapshot_of(row)
    data["variables_schema"] = data.get("variables_schema") or []
    data["description"] = data.get("description") or ""
    return data


def _published_definition(snapshot: dict[str, Any]) -> Definition:
    # Earlier Workbench snapshots did not contain registry-only fields.
    return Definition.model_validate({
        **snapshot,
        "title": snapshot.get("title") or "Untitled prompt",
        "description": snapshot.get("description") or "",
        "variables_schema": snapshot.get("variables_schema") or [],
        "enabled": snapshot.get("enabled", True),
    })


def _apply(row: Prompt, definition: Definition) -> None:
    for key, value in definition.model_dump().items():
        setattr(row, key, value)


def _view(row: Prompt) -> dict[str, Any]:
    return {"id": row.id, "prompt_set_id": row.prompt_set_id, "title": row.title,
            "description": row.description or "", "tags": row.tags or [],
            "current_version": row.current_version or 0, "active_version": row.active_version or 0,
            "draft": row.draft, "archived_at": row.archived_at, "updated_at": row.updated_at}


@router.get("")
async def search(project_id: str, request: Request, q: str = Query("", max_length=200),
                 tag: str = Query("", max_length=80), include_archived: bool = False,
                 limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0, le=100_000),
                 db: AsyncSession = Depends(get_db)):
    _local(request)
    await _project(db, project_id)
    where = [PromptSet.project_id == project_id]
    if not include_archived:
        where.append(Prompt.archived_at.is_(None))
    if q:
        where.append(Prompt.title.ilike(f"%{q}%"))
    if tag:
        each = func.json_each(Prompt.tags).table_valued("value")
        where.append(exists(select(1).select_from(each).where(each.c.value == tag)))
    rows = (await db.execute(select(Prompt).join(PromptSet).where(and_(*where))
        .order_by(Prompt.updated_at.desc(), Prompt.id).offset(offset).limit(limit + 1))).scalars().all()
    items = [_view(x) for x in rows]
    return {"items": items[:limit], "next_offset": offset + limit if len(items) > limit else None}


@router.post("", status_code=201)
async def create(project_id: str, body: RegistryCreate, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    await _project(db, project_id)
    ps = await db.get(PromptSet, body.prompt_set_id)
    if ps is None or ps.project_id != project_id:
        raise HTTPException(404, "Prompt set not found in project")
    row = Prompt(id=str(uuid.uuid4()), prompt_set_id=ps.id, title=body.definition.title,
                 prompt="", enabled=0, current_version=0, active_version=0,
                 draft=body.definition.model_dump(), author=body.author)
    db.add(row)
    await db.commit()
    return _view(row)


@router.get("/{prompt_id}")
async def get(project_id: str, prompt_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    row = await _prompt(db, project_id, prompt_id)
    return {**_view(row), "active_definition": _definition(row) if row.active_version else None}


@router.put("/{prompt_id}/draft")
async def save_draft(project_id: str, prompt_id: str, body: DraftUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    row = await _prompt(db, project_id, prompt_id)
    if row.archived_at:
        raise HTTPException(409, "Archived prompt cannot be edited")
    row.draft = body.definition.model_dump()
    row.author = body.author
    await db.commit()
    return _view(row)


@router.post("/{prompt_id}/publish")
async def publish(project_id: str, prompt_id: str, body: PublishRequest, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    row = await _prompt(db, project_id, prompt_id)
    if row.archived_at or row.draft is None:
        raise HTTPException(409, "No editable draft available")
    definition = Definition.model_validate(row.draft)
    _apply(row, definition)
    row.author = body.author or row.author
    row.current_version = (row.current_version or 0) + 1
    row.active_version = row.current_version
    row.draft = None
    await prompt_version_service.snapshot(db, row, note=body.note or "published")
    audit(db, project_id, "prompt.published", row.id, details={"version": row.current_version}, actor=row.author or "local-operator")
    await db.commit()
    return _view(row)


@router.get("/{prompt_id}/versions")
async def versions(project_id: str, prompt_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    await _prompt(db, project_id, prompt_id)
    return await prompt_version_service.list(db, prompt_id)


@router.get("/{prompt_id}/compare")
async def compare(project_id: str, prompt_id: str, request: Request, a: int = Query(ge=1), b: int = Query(ge=1), db: AsyncSession = Depends(get_db)):
    _local(request)
    await _prompt(db, project_id, prompt_id)
    result = await prompt_version_service.compare(db, prompt_id, a, b)
    if result is None:
        raise HTTPException(404, "Version not found")
    return result


@router.post("/{prompt_id}/activate/{version}")
async def activate(project_id: str, prompt_id: str, version: int, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    row = await _prompt(db, project_id, prompt_id)
    if row.archived_at:
        raise HTTPException(409, "Archived prompt cannot be activated")
    snapshot = await prompt_version_service.get_version(db, prompt_id, version)
    if snapshot is None:
        raise HTTPException(404, "Version not found")
    previous_version = row.active_version
    _apply(row, _published_definition(snapshot))
    row.active_version = version
    audit(db, project_id, "prompt.activated", prompt_id,
          details={"previous_version": previous_version, "version": version})
    await db.commit()
    return _view(row)


@router.post("/{prompt_id}/render")
async def render_prompt(project_id: str, prompt_id: str, body: RenderRequest, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    row = await _prompt(db, project_id, prompt_id)
    version = body.version or row.active_version
    if not version:
        raise HTTPException(409, "Publish a version before rendering")
    snapshot = await prompt_version_service.get_version(db, prompt_id, version)
    if snapshot is None:
        raise HTTPException(404, "Version not found")
    definition = _published_definition(snapshot)
    return {"prompt_id": prompt_id, "version": version, **render(definition, body.variables)}


@router.get("/{prompt_id}/export")
async def export(project_id: str, prompt_id: str, request: Request,
                 x_redforge_sensitive_access: str | None = Header(default=None),
                 db: AsyncSession = Depends(get_db)):
    _local(request)
    if x_redforge_sensitive_access != "allow":
        raise HTTPException(403, "Explicit sensitive-data export header required")
    row = await _prompt(db, project_id, prompt_id)
    versions = await prompt_version_service.list(db, prompt_id)
    audit(db, project_id, "prompt.exported", prompt_id)
    await db.commit()
    return {"format": "redforge.prompt/1", "id": row.id, "title": row.title,
            "active_version": row.active_version or 0, "versions": versions}


@router.post("/import", status_code=201)
async def import_definition(project_id: str, body: ImportRequest, request: Request, db: AsyncSession = Depends(get_db)):
    _local(request)
    await _project(db, project_id)
    ps = await db.get(PromptSet, body.prompt_set_id)
    if ps is None or ps.project_id != project_id:
        raise HTTPException(404, "Prompt set not found in project")
    source = body.definition
    if len(json.dumps(source, ensure_ascii=False).encode("utf-8")) > 1_048_576:
        raise HTTPException(413, "Prompt definition exceeds 1 MiB")
    if source.get("format") != "redforge.prompt/1" or not isinstance(source.get("versions"), list) or len(source["versions"]) > 100:
        raise HTTPException(422, "Unsupported or oversized prompt definition")
    versions = source["versions"]
    if not versions:
        raise HTTPException(422, "Definition has no published versions")
    parsed = []
    seen_versions: set[int] = set()
    for item in versions:
        if not isinstance(item, dict) or not isinstance(item.get("snapshot"), dict):
            raise HTTPException(422, "Invalid version snapshot")
        number = item.get("version")
        if not isinstance(number, int) or number < 1 or number in seen_versions:
            raise HTTPException(422, "Version numbers must be unique positive integers")
        seen_versions.add(number)
        snapshot = item["snapshot"]
        if item.get("content_hash") and hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest() != item["content_hash"]:
            raise HTTPException(422, "Version checksum mismatch")
        parsed.append(_published_definition(snapshot))
    if seen_versions != set(range(1, len(versions) + 1)):
        raise HTTPException(422, "Version numbers must be consecutive from 1")
    ordered = sorted(zip(versions, parsed), key=lambda pair: pair[0]["version"])
    versions = [item for item, _ in ordered]
    parsed = [definition for _, definition in ordered]
    selected = next((definition for item, definition in zip(versions, parsed) if item.get("version") == source.get("active_version")), None)
    if selected is None:
        raise HTTPException(422, "Active version missing")
    source_id = source.get("id")
    try:
        source_id = str(uuid.UUID(source_id)) if isinstance(source_id, str) else None
    except ValueError:
        source_id = None
    if source_id is None:
        raise HTTPException(422, "Invalid prompt ID")
    existing = await db.get(Prompt, source_id)
    if existing and not body.confirm_existing:
        raise HTTPException(409, "Prompt ID exists; confirm_existing is required")
    if existing:
        row = await _prompt(db, project_id, source_id)
        _apply(row, selected)
        row.current_version = (row.current_version or 0) + 1
        row.active_version = row.current_version
        row.author = body.author
        await prompt_version_service.snapshot(db, row, note="imported")
    else:
        row = Prompt(id=source_id, prompt_set_id=ps.id, prompt=selected.prompt,
                     title=selected.title, enabled=1, current_version=0, active_version=0, author=body.author)
        db.add(row)
        for item, definition in zip(versions, parsed):
            _apply(row, definition)
            row.current_version += 1
            row.author = item.get("author") or body.author
            await prompt_version_service.snapshot(db, row, note="imported")
        _apply(row, selected)
        row.active_version = next(i + 1 for i, item in enumerate(versions) if item.get("version") == source.get("active_version"))
    audit(db, project_id, "prompt.imported", row.id, details={"versions": len(versions)}, actor=body.author or "local-operator")
    await db.commit()
    return _view(row)


@router.delete("/{prompt_id}")
async def archive(project_id: str, prompt_id: str, request: Request,
                  x_redforge_confirm_action: str | None = Header(default=None),
                  db: AsyncSession = Depends(get_db)):
    _local(request)
    if x_redforge_confirm_action != "archive":
        raise HTTPException(403, "Explicit archive confirmation header required")
    row = await _prompt(db, project_id, prompt_id)
    row.archived_at = datetime.now(timezone.utc)
    row.enabled = 0
    audit(db, project_id, "prompt.archived", prompt_id)
    await db.commit()
    return _view(row)


@router.get("/{prompt_id}/links")
async def links(project_id: str, prompt_id: str, request: Request, limit: int = Query(30, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    _local(request)
    await _prompt(db, project_id, prompt_id)
    traces = (await db.execute(select(TraceEvent).where(TraceEvent.project_id == project_id,
        TraceEvent.prompt_template_id == prompt_id).order_by(TraceEvent.id.desc()).limit(limit))).scalars().all()
    results = (await db.execute(select(EvaluationResult, WorkbenchSession).join(WorkbenchSession,
        EvaluationResult.session_id == WorkbenchSession.id).where(EvaluationResult.prompt_id == prompt_id,
        WorkbenchSession.project_id == project_id).order_by(EvaluationResult.created_at.desc()).limit(limit))).all()
    return {"traces": [{"event_id": t.event_id, "version": t.prompt_version_id, "status": t.status,
                         "received_at": t.received_at} for t in traces],
            "evaluations": [{"result_id": r.id, "session_id": s.id, "version": r.prompt_version,
                             "verdict": r.verdict, "created_at": r.created_at} for r, s in results]}
