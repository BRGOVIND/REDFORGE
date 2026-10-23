"""Bounded privacy retention for unapproved trace-derived security drafts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import SecurityCandidate
from app.observability_privacy import audit, get_policy


async def cleanup_expired_security_candidates(db, *, batch_size: int = 100) -> int:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(SecurityCandidate).where(
        SecurityCandidate.state.in_(("draft", "in_review")),
        SecurityCandidate.created_at < now - timedelta(days=1))
        .order_by(SecurityCandidate.created_at).limit(batch_size))).scalars().all()
    policies = {}
    removed = 0
    for row in rows:
        if row.project_id not in policies:
            policies[row.project_id] = await get_policy(db, row.project_id)
        created = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
        if created >= now - timedelta(days=policies[row.project_id].retention_days):
            continue
        row.prompt_text = None
        row.title = "Expired security candidate"
        row.state = "archived"
        audit(db, row.project_id, "security_candidate_retention_archive", row.id)
        removed += 1
    if removed:
        await db.commit()
    return removed
