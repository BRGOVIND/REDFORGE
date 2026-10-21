"""Bounded cleanup of unapproved feedback drafts under trace capture retention."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import FeedbackCase
from app.observability_privacy import audit, get_policy


async def cleanup_expired_feedback(db, *, batch_size: int = 100) -> int:
    if not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be 1..100")
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(FeedbackCase).where(
        FeedbackCase.state.in_(("draft", "in_review", "rejected")),
        FeedbackCase.created_at < now - timedelta(days=1)
    ).order_by(FeedbackCase.created_at).limit(batch_size))).scalars().all()
    policies = {}
    removed = 0
    for row in rows:
        if row.project_id not in policies:
            policies[row.project_id] = await get_policy(db, row.project_id)
        created = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
        if created >= now - timedelta(days=policies[row.project_id].retention_days):
            continue
        row.prompt_text = None
        row.expected_output = None
        row.notes = ""
        row.title = "Expired feedback case"
        row.labels = []
        row.state = "archived"
        audit(db, row.project_id, "feedback_case_retention_archive", row.id)
        removed += 1
    if removed:
        await db.commit()
    return removed
