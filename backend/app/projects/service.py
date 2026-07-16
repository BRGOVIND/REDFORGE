"""Project (workspace) persistence service.

Async CRUD over the ``projects`` table, plus duplicate and "recent" ordering.
Pure data layer — takes an ``AsyncSession`` and returns plain dicts so the API
layer owns serialization. No runtime/provider coupling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description or "",
        "models": p.models or [],
        "datasets": p.datasets or [],
        "settings": p.settings or {},
        "last_scan": p.last_scan,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
    }


class ProjectService:
    async def list(self, db: AsyncSession, *, limit: Optional[int] = None) -> list[dict]:
        """All projects, most-recently-opened first (drives Recent Projects)."""
        stmt = select(Project).order_by(Project.opened_at.desc())
        if limit:
            stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return [_to_dict(p) for p in rows]

    async def get(self, db: AsyncSession, project_id: str) -> Optional[dict]:
        p = await db.get(Project, project_id)
        return _to_dict(p) if p else None

    async def create(
        self, db: AsyncSession, *, name: str,
        description: str = "", models: Optional[list] = None,
        settings: Optional[dict] = None,
    ) -> dict:
        p = Project(
            id=str(uuid4()),
            name=name.strip() or "Untitled Project",
            description=description or "",
            models=models or [],
            datasets=[],
            settings=settings or {},
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return _to_dict(p)

    async def update(self, db: AsyncSession, project_id: str, **fields) -> Optional[dict]:
        p = await db.get(Project, project_id)
        if p is None:
            return None
        for key in ("name", "description", "models", "datasets", "settings", "last_scan"):
            if key in fields and fields[key] is not None:
                setattr(p, key, fields[key])
        await db.commit()
        await db.refresh(p)
        return _to_dict(p)

    async def touch(self, db: AsyncSession, project_id: str) -> Optional[dict]:
        """Mark a project opened → moves it to the top of Recent Projects."""
        p = await db.get(Project, project_id)
        if p is None:
            return None
        p.opened_at = _utcnow()
        await db.commit()
        await db.refresh(p)
        return _to_dict(p)

    async def delete(self, db: AsyncSession, project_id: str) -> bool:
        p = await db.get(Project, project_id)
        if p is None:
            return False
        await db.delete(p)
        await db.commit()
        return True

    async def duplicate(self, db: AsyncSession, project_id: str) -> Optional[dict]:
        src = await db.get(Project, project_id)
        if src is None:
            return None
        copy = Project(
            id=str(uuid4()),
            name=f"{src.name} (copy)",
            description=src.description or "",
            models=list(src.models or []),
            datasets=list(src.datasets or []),
            settings=dict(src.settings or {}),
        )
        db.add(copy)
        await db.commit()
        await db.refresh(copy)
        return _to_dict(copy)


project_service = ProjectService()
