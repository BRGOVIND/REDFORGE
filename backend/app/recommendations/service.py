"""Recommendation persistence + context assembly.

Reads existing local metadata — Continuous Security results (``checkpoint_security``),
training config (``training_runs``), and dataset quality (``datasets``) — assembles
a :class:`ModelContext`, runs the pure engine, and stores the result with
accept/reject history. No duplication of the security/training/dataset engines.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CheckpointSecurity, Dataset, Recommendation, TrainingRun
from app.recommendations.engine import ModelContext, recommend


async def _actual_security_gain(db: AsyncSession, run_id: str) -> Optional[float]:
    """Actual security improvement over a run's checkpoint timeline (last-first)."""
    rows = (await db.execute(
        select(CheckpointSecurity)
        .where(CheckpointSecurity.run_id == run_id, CheckpointSecurity.status == "completed")
        .order_by(CheckpointSecurity.step)
    )).scalars().all()
    scored = [r.score for r in rows if r.score is not None]
    if len(scored) < 2:
        return None
    return round(scored[-1] - scored[0], 2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_dict(r: Recommendation) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "run_id": r.run_id,
        "target_model": r.target_model,
        "source": r.source,
        "status": r.status,
        "payload": r.payload or {},
        "outcome": r.outcome,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    }


class RecommendationService:
    async def _build_context(
        self, db: AsyncSession, *, target_model: str,
        run_id: Optional[str], project_id: Optional[str],
    ) -> ModelContext:
        ctx = ModelContext(target_model=target_model)

        # Security: the latest completed checkpoint evaluation for this run.
        if run_id:
            sec_rows = (await db.execute(
                select(CheckpointSecurity)
                .where(CheckpointSecurity.run_id == run_id,
                       CheckpointSecurity.status == "completed")
                .order_by(CheckpointSecurity.step)
            )).scalars().all()
            completed = [s for s in sec_rows if s.score is not None]
            if completed:
                latest = completed[-1]
                ctx.security_score = latest.score
                ctx.categories = latest.categories or []
                ctx.findings = latest.findings or []
                ctx.total_tests = 30 if len(ctx.categories) >= 2 else 10  # coverage proxy
                if len(completed) >= 2:
                    ctx.score_trend = completed[-1].score - completed[0].score

            # Training config (prior run).
            run = await db.get(TrainingRun, run_id)
            if run is not None:
                ctx.last_training = run.config or {}
                if project_id is None:
                    project_id = run.project_id
                # Dataset attached to the run.
                if run.dataset_id:
                    d = await db.get(Dataset, run.dataset_id)
                    if d is not None:
                        meta = d.dataset_metadata or {}
                        ctx.dataset = {
                            "quality_score": meta.get("quality_score"),
                            "record_count": d.record_count,
                            "issues": meta.get("issues"),
                        }

        # Existing project datasets (suggestion candidates).
        if project_id:
            ds = (await db.execute(
                select(Dataset).where(Dataset.project_id == project_id)
            )).scalars().all()
            ctx.project_datasets = [
                {"id": d.id, "name": d.name,
                 "quality": (d.dataset_metadata or {}).get("quality_score"),
                 "records": d.record_count}
                for d in ds
            ]
        return ctx

    async def analyze(
        self, db: AsyncSession, *, target_model: str,
        run_id: Optional[str] = None, project_id: Optional[str] = None,
        source: str = "security", persist: bool = True,
    ) -> dict:
        """Generate (and optionally store) a recommendation for a model."""
        ctx = await self._build_context(db, target_model=target_model, run_id=run_id, project_id=project_id)
        payload = recommend(ctx)
        if not persist:
            return {"payload": payload, "run_id": run_id, "project_id": project_id,
                    "target_model": target_model}
        rec = Recommendation(
            id=str(uuid4()), project_id=project_id, run_id=run_id,
            target_model=target_model, source=source, status="proposed", payload=payload,
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        return _to_dict(rec)

    async def list(self, db: AsyncSession, *, project_id: Optional[str] = None) -> list[dict]:
        stmt = select(Recommendation).order_by(Recommendation.created_at.desc())
        if project_id is not None:
            stmt = stmt.where(Recommendation.project_id == project_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [_to_dict(r) for r in rows]

    async def get(self, db: AsyncSession, rec_id: str) -> Optional[dict]:
        r = await db.get(Recommendation, rec_id)
        return _to_dict(r) if r else None

    async def decide(self, db: AsyncSession, rec_id: str, status: str) -> Optional[dict]:
        r = await db.get(Recommendation, rec_id)
        if r is None:
            return None
        r.status = status
        r.decided_at = _utcnow()
        await db.commit()
        await db.refresh(r)
        return _to_dict(r)

    async def set_outcome(self, db: AsyncSession, rec_id: str, outcome: dict) -> Optional[dict]:
        r = await db.get(Recommendation, rec_id)
        if r is None:
            return None
        r.outcome = outcome
        await db.commit()
        await db.refresh(r)
        return _to_dict(r)

    async def record_outcome(self, db: AsyncSession, rec_id: str, applied_run_id: str) -> Optional[dict]:
        """Compare predicted vs actual improvement for the run that applied this
        recommendation, compute accuracy, and store it (local prediction history).
        Marks the recommendation ``applied``. Actual gain comes from that run's
        Continuous Security timeline — no new evaluation is run."""
        r = await db.get(Recommendation, rec_id)
        if r is None:
            return None
        predicted = (r.payload or {}).get("prediction", {}).get("expected_security_gain")
        confidence = (r.payload or {}).get("prediction", {}).get("confidence")
        actual = await _actual_security_gain(db, applied_run_id)

        accuracy = None
        if predicted is not None and actual is not None:
            denom = max(abs(predicted), abs(actual), 1.0)
            accuracy = round(max(0.0, 1.0 - abs(predicted - actual) / denom), 3)

        r.outcome = {
            "applied_run_id": applied_run_id,
            "predicted_security_gain": predicted,
            "actual_security_gain": actual,
            "recommendation_accuracy": accuracy,
            "confidence": confidence,
            # confidence accuracy: was the confidence justified by the accuracy?
            "confidence_accuracy": (round(1.0 - abs((confidence or 0) - (accuracy or 0)), 3)
                                    if accuracy is not None else None),
        }
        r.status = "applied"
        r.decided_at = _utcnow()
        await db.commit()
        await db.refresh(r)
        return _to_dict(r)

    async def accuracy_summary(self, db: AsyncSession, *, project_id: Optional[str] = None) -> dict:
        """Aggregate historical recommendation accuracy (drives Assistant answers +
        future confidence calibration)."""
        stmt = select(Recommendation).where(Recommendation.outcome.isnot(None))
        if project_id is not None:
            stmt = stmt.where(Recommendation.project_id == project_id)
        rows = (await db.execute(stmt)).scalars().all()
        accs = [(_r.outcome or {}).get("recommendation_accuracy") for _r in rows]
        accs = [a for a in accs if a is not None]
        best = max(
            (r for r in rows if (r.outcome or {}).get("actual_security_gain") is not None),
            key=lambda r: r.outcome["actual_security_gain"], default=None,
        )
        return {
            "count": len(accs),
            "mean_accuracy": round(sum(accs) / len(accs), 3) if accs else None,
            "best_recommendation": (_to_dict(best) if best is not None else None),
        }


recommendation_service = RecommendationService()
