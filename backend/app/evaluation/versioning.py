"""Prompt version history for the Evaluation Workbench.

Each save can snapshot a prompt's fields into an immutable :class:`PromptVersion`.
Regression reports use versions to tell whether a difference came from the prompt
changing or the model changing. Operates on a passed-in async session so it
composes with the CRUD service and stays testable.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.db.models import Prompt, PromptVersion

# The prompt fields captured in a version snapshot.
_SNAPSHOT_FIELDS = (
    "title", "prompt", "system_prompt", "context", "expected_behavior",
    "expected_output", "golden_response", "acceptance_criteria", "tags",
    "priority", "difficulty", "notes",
)


def snapshot_of(prompt: Prompt) -> dict:
    return {f: getattr(prompt, f) for f in _SNAPSHOT_FIELDS}


class PromptVersionService:
    async def snapshot(self, db, prompt: Prompt, note: str = "") -> PromptVersion:
        """Persist the prompt's current fields as a new version. Caller commits."""
        pv = PromptVersion(
            prompt_id=prompt.id, version=prompt.current_version,
            snapshot=snapshot_of(prompt), note=note,
        )
        db.add(pv)
        return pv

    async def list(self, db, prompt_id: str) -> list[dict]:
        rows = (await db.execute(
            select(PromptVersion).where(PromptVersion.prompt_id == prompt_id)
            .order_by(PromptVersion.version)
        )).scalars().all()
        return [{"id": v.id, "version": v.version, "note": v.note,
                 "snapshot": v.snapshot, "created_at": v.created_at.isoformat() if v.created_at else None}
                for v in rows]

    async def get_version(self, db, prompt_id: str, version: int) -> Optional[dict]:
        row = (await db.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_id == prompt_id, PromptVersion.version == version)
        )).scalar_one_or_none()
        return row.snapshot if row else None

    async def compare(self, db, prompt_id: str, a: int, b: int) -> Optional[dict]:
        """Field-level diff between two prompt versions."""
        sa = await self.get_version(db, prompt_id, a)
        sb = await self.get_version(db, prompt_id, b)
        if sa is None or sb is None:
            return None
        changed = {f: {"a": sa.get(f), "b": sb.get(f)}
                   for f in _SNAPSHOT_FIELDS if sa.get(f) != sb.get(f)}
        return {"prompt_id": prompt_id, "a": a, "b": b,
                "changed_fields": list(changed.keys()), "diff": changed}


prompt_version_service = PromptVersionService()
