"""Dataset persistence + versioning service.

Async CRUD over ``datasets`` / ``dataset_versions``, plus preview (pagination +
search), analysis caching, cleaning-as-a-new-version, splitting, restore, and
compare. Content is stored as JSON in SQLite — fully local, no cloud. Every
mutation that changes records creates a NEW version; nothing is overwritten.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datasets_lab import analysis, cleaning, parsers, splitting
from app.db.models import Dataset, DatasetVersion


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dataset_dict(d: Dataset) -> dict:
    return {
        "id": d.id,
        "project_id": d.project_id,
        "name": d.name,
        "description": d.description or "",
        "source_format": d.source_format,
        "kind": d.kind,
        "columns": d.columns or [],
        "record_count": d.record_count or 0,
        "byte_size": d.byte_size or 0,
        "current_version": d.current_version or 1,
        "metadata": d.dataset_metadata or {},
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


class DatasetService:
    # -- read --------------------------------------------------------------

    async def list(self, db: AsyncSession, *, project_id: Optional[str] = None) -> list[dict]:
        stmt = select(Dataset).order_by(Dataset.updated_at.desc())
        if project_id is not None:
            stmt = stmt.where(Dataset.project_id == project_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [_dataset_dict(d) for d in rows]

    async def get(self, db: AsyncSession, dataset_id: str) -> Optional[dict]:
        d = await db.get(Dataset, dataset_id)
        return _dataset_dict(d) if d else None

    async def _current_records(self, db: AsyncSession, dataset_id: str) -> Optional[list[Any]]:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        v = (await db.execute(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.version == d.current_version,
            )
        )).scalar_one_or_none()
        return list(v.records) if v else []

    # -- create / import ---------------------------------------------------

    async def create(
        self, db: AsyncSession, *, name: str, project_id: Optional[str] = None,
        description: str = "", records: Optional[list[Any]] = None,
        columns: Optional[list[str]] = None, kind: str = "records",
        source_format: str = "json",
    ) -> dict:
        records = records or []
        d = Dataset(
            id=str(uuid4()), project_id=project_id,
            name=name.strip() or "Untitled Dataset", description=description or "",
            source_format=source_format, kind=kind, columns=columns or [],
            record_count=len(records), current_version=1,
        )
        db.add(d)
        db.add(DatasetVersion(dataset_id=d.id, version=1, records=records,
                              record_count=len(records), note="created"))
        await db.commit()
        await db.refresh(d)
        return _dataset_dict(d)

    async def import_bytes(
        self, db: AsyncSession, *, name: str, filename: str, data: bytes,
        project_id: Optional[str] = None,
    ) -> dict:
        fmt = parsers.detect_format(filename)
        parsed = parsers.parse(data, fmt)
        d = await self.create(
            db, name=name, project_id=project_id,
            records=parsed["records"], columns=parsed["columns"],
            kind=parsed["kind"], source_format=parsed["format"],
        )
        # Record byte size + cache stats.
        obj = await db.get(Dataset, d["id"])
        obj.byte_size = len(data)
        obj.dataset_metadata = analysis.statistics(parsed["records"], parsed["kind"], len(data))
        await db.commit()
        await db.refresh(obj)
        return _dataset_dict(obj)

    # -- update / lifecycle ------------------------------------------------

    async def update_meta(self, db: AsyncSession, dataset_id: str, **fields) -> Optional[dict]:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        for key in ("name", "description", "project_id"):
            if key in fields and fields[key] is not None:
                setattr(d, key, fields[key])
        await db.commit()
        await db.refresh(d)
        return _dataset_dict(d)

    async def delete(self, db: AsyncSession, dataset_id: str) -> bool:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return False
        await db.delete(d)
        await db.commit()
        return True

    async def duplicate(self, db: AsyncSession, dataset_id: str) -> Optional[dict]:
        src = await db.get(Dataset, dataset_id)
        if src is None:
            return None
        records = await self._current_records(db, dataset_id) or []
        return await self.create(
            db, name=f"{src.name} (copy)", project_id=src.project_id,
            description=src.description or "", records=records,
            columns=list(src.columns or []), kind=src.kind, source_format=src.source_format,
        )

    async def save_version(
        self, db: AsyncSession, dataset_id: str, records: list[Any], note: str = "",
    ) -> Optional[dict]:
        """Append a new version and make it current. Never overwrites history."""
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        new_version = (d.current_version or 1) + 1
        db.add(DatasetVersion(
            dataset_id=dataset_id, version=new_version, records=records,
            record_count=len(records), note=note or "saved",
        ))
        d.current_version = new_version
        d.record_count = len(records)
        d.dataset_metadata = analysis.statistics(records, d.kind, d.byte_size or 0)
        await db.commit()
        await db.refresh(d)
        return _dataset_dict(d)

    # -- preview -----------------------------------------------------------

    async def preview(
        self, db: AsyncSession, dataset_id: str, *,
        offset: int = 0, limit: int = 50, search: str = "",
    ) -> Optional[dict]:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        records = await self._current_records(db, dataset_id) or []
        if search:
            s = search.lower()
            records = [r for r in records if s in _row_text(r).lower()]
        total = len(records)
        page = records[offset:offset + limit]
        return {
            "dataset_id": dataset_id,
            "kind": d.kind,
            "columns": d.columns or [],
            "total": total,
            "offset": offset,
            "limit": limit,
            "rows": page,
        }

    # -- analysis ----------------------------------------------------------

    async def analyze(self, db: AsyncSession, dataset_id: str) -> Optional[dict]:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        records = await self._current_records(db, dataset_id) or []
        report = analysis.analyze(records, d.kind, d.columns or [], d.byte_size or 0)
        # Cache the summary so the Project overview + Assistant can read it cheaply.
        d.dataset_metadata = {**(d.dataset_metadata or {}), **report["statistics"],
                              "quality_score": report["score"], "quality_grade": report["grade"],
                              "issues": report["issues"]}
        await db.commit()
        return report

    # -- cleaning (preview or save) ---------------------------------------

    async def clean(
        self, db: AsyncSession, dataset_id: str, operations: list[str], *,
        save: bool = False,
    ) -> Optional[dict]:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        records = await self._current_records(db, dataset_id) or []
        cleaned, notes = cleaning.clean(records, operations)
        result = {
            "dataset_id": dataset_id,
            "before_count": len(records),
            "after_count": len(cleaned),
            "notes": notes,
            "preview": cleaned[:20],
            "saved": False,
        }
        if save:
            await self.save_version(db, dataset_id, cleaned, note="; ".join(notes)[:300])
            result["saved"] = True
        return result

    # -- split -------------------------------------------------------------

    async def split(
        self, db: AsyncSession, dataset_id: str, *,
        train: float, val: float, test: float, shuffle: bool = True, seed: int = 42,
    ) -> Optional[dict]:
        records = await self._current_records(db, dataset_id)
        if records is None:
            return None
        return splitting.split(records, train=train, val=val, test=test,
                               shuffle=shuffle, seed=seed)

    # -- versions ----------------------------------------------------------

    async def versions(self, db: AsyncSession, dataset_id: str) -> Optional[list[dict]]:
        d = await db.get(Dataset, dataset_id)
        if d is None:
            return None
        rows = (await db.execute(
            select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version.desc())
        )).scalars().all()
        return [{
            "version": v.version,
            "record_count": v.record_count,
            "note": v.note,
            "is_current": v.version == d.current_version,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        } for v in rows]

    async def restore(self, db: AsyncSession, dataset_id: str, version: int) -> Optional[dict]:
        """Restore an old version by copying its records forward as a new version
        (so the restore itself is also reversible)."""
        v = (await db.execute(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id, DatasetVersion.version == version)
        )).scalar_one_or_none()
        if v is None:
            return None
        return await self.save_version(db, dataset_id, list(v.records),
                                       note=f"restored from v{version}")

    async def compare(self, db: AsyncSession, dataset_id: str, a: int, b: int) -> Optional[dict]:
        va = (await db.execute(select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id, DatasetVersion.version == a))).scalar_one_or_none()
        vb = (await db.execute(select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id, DatasetVersion.version == b))).scalar_one_or_none()
        if va is None or vb is None:
            return None
        set_a = {_row_text(r).strip().lower() for r in va.records}
        set_b = {_row_text(r).strip().lower() for r in vb.records}
        return {
            "a": a, "b": b,
            "count_a": va.record_count, "count_b": vb.record_count,
            "added": len(set_b - set_a),
            "removed": len(set_a - set_b),
            "delta": vb.record_count - va.record_count,
        }


def _row_text(row: Any) -> str:
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        return " ".join(str(v) for v in row.values() if v is not None)
    return str(row)


dataset_service = DatasetService()
