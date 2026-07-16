"""Dataset Lab API (RedForge V2, Phase 2).

Local-first dataset management: import / preview / analyze / clean / split /
version, attachable to projects. Additive router under ``/api/datasets`` (the
existing ``/api/dataset`` benchmark routes are untouched). Delegates to the
isolated :mod:`app.datasets_lab` service — no runtime/provider/training logic.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.datasets_lab import dataset_service
from app.datasets_lab import parsers
from app.db.database import get_db

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

_UPLOAD_CHUNK = 1 << 20  # 1 MB


def _human(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} MB"


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """Read an upload in bounded chunks, aborting as soon as it exceeds ``limit``.

    Never buffers more than the limit + one chunk, so a hostile/huge file cannot
    exhaust memory. Raises HTTP 413 with a friendly message when too large."""
    buf = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large. The maximum dataset upload is {_human(limit)}. "
                       f"Split the file or raise REDFORGE_MAX_UPLOAD_BYTES.",
            )
    return bytes(buf)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    project_id: Optional[str] = None
    description: str = ""
    records: list[Any] = []
    columns: list[str] = []
    kind: str = "records"


class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    project_id: Optional[str] = None


class CleanRequest(BaseModel):
    operations: list[str]
    save: bool = False


class SplitRequest(BaseModel):
    train: float = 0.8
    val: float = 0.1
    test: float = 0.1
    shuffle: bool = True
    seed: int = 42


class RestoreRequest(BaseModel):
    version: int


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_datasets(
    db: AsyncSession = Depends(get_db),
    project_id: Optional[str] = Query(None),
) -> list[dict]:
    return await dataset_service.list(db, project_id=project_id)


@router.get("/formats")
async def supported_formats() -> dict:
    return {"formats": parsers.SUPPORTED_FORMATS}


@router.post("", status_code=201)
async def create_dataset(req: DatasetCreate, db: AsyncSession = Depends(get_db)) -> dict:
    return await dataset_service.create(
        db, name=req.name, project_id=req.project_id, description=req.description,
        records=req.records, columns=req.columns, kind=req.kind,
    )


@router.post("/import", status_code=201)
async def import_dataset(
    request: Request,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
) -> dict:
    limit = settings.MAX_UPLOAD_BYTES

    # Fast reject via Content-Length before reading a byte, when the client sends it.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + _UPLOAD_CHUNK:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. The maximum dataset upload is {_human(limit)}.",
        )

    fmt = parsers.detect_format(file.filename or "upload.txt")
    if fmt not in parsers.SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{fmt}'.")

    # Streamed, bounded read — never buffers an arbitrarily large file.
    data = await _read_capped(file, limit)
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")

    try:
        return await dataset_service.import_bytes(
            db, name=name or (file.filename or "Imported dataset"),
            filename=file.filename or "upload.txt", data=data, project_id=project_id,
        )
    except parsers.ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    d = await dataset_service.get(db, dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return d


@router.patch("/{dataset_id}")
async def update_dataset(dataset_id: str, req: DatasetUpdate, db: AsyncSession = Depends(get_db)) -> dict:
    d = await dataset_service.update_meta(db, dataset_id, **req.model_dump(exclude_unset=True))
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return d


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    if not await dataset_service.delete(db, dataset_id):
        raise HTTPException(status_code=404, detail="dataset not found")
    return {"deleted": True, "id": dataset_id}


@router.post("/{dataset_id}/duplicate", status_code=201)
async def duplicate_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    d = await dataset_service.duplicate(db, dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return d


# ---------------------------------------------------------------------------
# Preview / analysis / cleaning / split
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/preview")
async def preview_dataset(
    dataset_id: str,
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: str = Query(""),
) -> dict:
    p = await dataset_service.preview(db, dataset_id, offset=offset, limit=limit, search=search)
    if p is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return p


@router.get("/{dataset_id}/analyze")
async def analyze_dataset(dataset_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    r = await dataset_service.analyze(db, dataset_id)
    if r is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return r


@router.post("/{dataset_id}/clean")
async def clean_dataset(dataset_id: str, req: CleanRequest, db: AsyncSession = Depends(get_db)) -> dict:
    r = await dataset_service.clean(db, dataset_id, req.operations, save=req.save)
    if r is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return r


@router.post("/{dataset_id}/split")
async def split_dataset(dataset_id: str, req: SplitRequest, db: AsyncSession = Depends(get_db)) -> dict:
    r = await dataset_service.split(
        db, dataset_id, train=req.train, val=req.val, test=req.test,
        shuffle=req.shuffle, seed=req.seed,
    )
    if r is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    # Return counts + statistics; omit the full split payload's records by default
    # to keep the response light (the UI shows stats; export produces the files).
    return {"statistics": r["statistics"]}


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/versions")
async def list_versions(dataset_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    v = await dataset_service.versions(db, dataset_id)
    if v is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    return v


@router.post("/{dataset_id}/restore")
async def restore_version(dataset_id: str, req: RestoreRequest, db: AsyncSession = Depends(get_db)) -> dict:
    d = await dataset_service.restore(db, dataset_id, req.version)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset or version not found")
    return d


@router.get("/{dataset_id}/compare")
async def compare_versions(
    dataset_id: str,
    a: int = Query(...),
    b: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    r = await dataset_service.compare(db, dataset_id, a, b)
    if r is None:
        raise HTTPException(status_code=404, detail="dataset or version not found")
    return r


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/export", response_class=PlainTextResponse)
async def export_dataset(
    dataset_id: str,
    fmt: str = Query("jsonl", pattern="^(jsonl|json|csv|txt)$"),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    records = await dataset_service._current_records(db, dataset_id)
    if records is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    d = await dataset_service.get(db, dataset_id)
    content = _serialize(records, fmt, d["kind"], d["columns"])
    media = {"json": "application/json", "csv": "text/csv"}.get(fmt, "text/plain")
    return PlainTextResponse(content, media_type=media)


def _serialize(records: list[Any], fmt: str, kind: str, columns: list[str]) -> str:
    if fmt == "json":
        return json.dumps(records, ensure_ascii=False, indent=2)
    if fmt == "jsonl":
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    if fmt == "csv":
        import csv
        import io
        buf = io.StringIO()
        cols = columns or (list(records[0].keys()) if records and isinstance(records[0], dict) else ["value"])
        writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r if isinstance(r, dict) else {"value": r})
        return buf.getvalue()
    # txt
    return parsers.records_to_text(records, kind)
