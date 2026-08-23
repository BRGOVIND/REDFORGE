"""Composed engineering report for a finished training run.

Read-only: stitches together data the platform already stored — training
summary, dataset, security timeline, checkpoint comparison, recommendations,
registered models, benchmarks and evaluation — into a single payload. Stores
nothing new and computes no new scores.

This lived inside the HTTP handler in `app.api.training`, which meant ~160 lines
of ORM queries and aggregation in the transport layer. It is domain work and
belongs beside the rest of the training domain.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def build_run_report(db: AsyncSession, run_id: str) -> Optional[dict]:
    """The report payload, or ``None`` when the run does not exist.

    Returning ``None`` keeps HTTP status decisions in the transport layer.
    """
    from sqlalchemy import select

    from app.db.models import (
        BenchmarkResult, CheckpointSecurity, Dataset, Recommendation, RegisteredModel,
        TrainingRun, WorkbenchSession,
    )

    run = await db.get(TrainingRun, run_id)
    if run is None:
        return None

    # Dataset summary.
    dataset = None
    if run.dataset_id:
        d = await db.get(Dataset, run.dataset_id)
        if d is not None:
            meta = d.dataset_metadata or {}
            dataset = {"id": d.id, "name": d.name, "record_count": d.record_count,
                       "quality_score": meta.get("quality_score")}

    # Security timeline + comparison (first vs last completed).
    sec = (await db.execute(
        select(CheckpointSecurity)
        .where(CheckpointSecurity.run_id == run_id, CheckpointSecurity.status == "completed")
        .order_by(CheckpointSecurity.step)
    )).scalars().all()
    timeline = [{"step": s.step, "score": s.score, "runtime_id": s.runtime_id,
                 "provider": s.provider, "categories": s.categories or []} for s in sec]
    scored = [s for s in sec if s.score is not None]
    comparison = None
    if len(scored) >= 2:
        comparison = {
            "first": {"step": scored[0].step, "score": scored[0].score},
            "last": {"step": scored[-1].step, "score": scored[-1].score},
            "delta": round(scored[-1].score - scored[0].score, 2),
        }

    # Recommendations (predicted vs actual).
    recs = (await db.execute(
        select(Recommendation).where(Recommendation.run_id == run_id)
    )).scalars().all()
    recommendations = [{
        "id": r.id, "status": r.status,
        "predicted": (r.payload or {}).get("prediction", {}).get("expected_security_gain"),
        "outcome": r.outcome,
        "hyperparameters": (r.payload or {}).get("hyperparameters"),
    } for r in recs]
    accepted = [r for r in recommendations if r["status"] in ("accepted", "applied")]
    rejected = [r for r in recommendations if r["status"] == "rejected"]

    # Registered (runnable) models.
    registered = (await db.execute(
        select(RegisteredModel).where(RegisteredModel.run_id == run_id,
                                      RegisteredModel.status == "registered")
    )).scalars().all()
    final_models = [{"id": m.id, "label": m.label, "runtime_model": m.runtime_model,
                     "fallback": bool(m.fallback)} for m in registered]

    # Benchmark results for this run's models (Phase 3) — reuse existing data, no
    # separate report. Latest completed result per model, with per-suite scores.
    bench_rows = (await db.execute(
        select(BenchmarkResult)
        .where(BenchmarkResult.run_id == run_id, BenchmarkResult.status == "completed")
        .order_by(BenchmarkResult.created_at.desc())
    )).scalars().all()
    seen_models: set[str] = set()
    benchmarks = []
    for b in bench_rows:
        if b.target_model in seen_models:
            continue
        seen_models.add(b.target_model)
        benchmarks.append({
            "id": b.id, "label": b.label or b.target_model, "target_model": b.target_model,
            "registry_id": b.registry_id, "overall_score": b.overall_score,
            "scores": b.scores or {}, "suites": b.suites or [],
        })
    best_benchmark = max(
        (b for b in benchmarks if b["overall_score"] is not None),
        key=lambda b: b["overall_score"], default=None,
    )

    # Evaluation Workbench (Phase 4) — latest completed session for this run or its
    # project. Reuses stored session data; nothing new is computed or stored.
    eval_stmt = select(WorkbenchSession).where(WorkbenchSession.status == "completed")
    if run.project_id:
        eval_stmt = eval_stmt.where(
            (WorkbenchSession.run_id == run_id) | (WorkbenchSession.project_id == run.project_id))
    else:
        eval_stmt = eval_stmt.where(WorkbenchSession.run_id == run_id)
    eval_session = (await db.execute(
        eval_stmt.order_by(WorkbenchSession.created_at.desc()).limit(1))).scalar_one_or_none()
    evaluation = None
    deployment_recommendation = None
    if eval_session is not None:
        summ = eval_session.summary or {}
        best = summ.get("best_model")
        evaluation = {
            "session_id": eval_session.id, "name": eval_session.name,
            "pass_rate": summ.get("pass_rate"), "fail_rate": summ.get("fail_rate"),
            "regression_score": summ.get("regression_score"),
            "consistency_score": summ.get("consistency_score"),
            "quality_score": summ.get("quality_score"),
            "overall_score": summ.get("overall_score"),
            "regression_breakdown": summ.get("regression_breakdown", {}),
            "best_model": best, "closest_to_baseline": summ.get("closest_to_baseline"),
            "models": summ.get("models", []),
        }
        pr = summ.get("pass_rate")
        if best and pr is not None:
            if pr >= 80 and not summ.get("regression_breakdown"):
                deployment_recommendation = (
                    f"Deploy **{best['label']}** — {pr:.0f}% pass rate with no regressions.")
            elif pr >= 80:
                deployment_recommendation = (
                    f"**{best['label']}** leads ({pr:.0f}% pass) but has regressions — "
                    f"review them before deploying.")
            else:
                deployment_recommendation = (
                    f"Hold deployment — best model **{best['label']}** only passed "
                    f"{pr:.0f}% of prompts. Consider retraining.")

    exec_summary = (
        f"{run.name}: {run.method.upper()} on {run.base_model} ({run.backend}), status {run.status}. "
        + (f"Security {comparison['first']['score']} → {comparison['last']['score']} "
           f"({comparison['delta']:+.0f} over {len(scored)} checkpoints). "
           if comparison else "No security timeline recorded. ")
        + f"{len(accepted)} recommendation(s) accepted, {len(rejected)} rejected."
    )
    remaining = []
    if scored:
        for c in (scored[-1].categories or []):
            if (c.get("risk_level") or "none") not in ("none",):
                remaining.append(c.get("category"))

    return {
        "run_id": run_id,
        "executive_summary": exec_summary,
        "training_summary": {
            "name": run.name, "base_model": run.base_model, "method": run.method,
            "backend": run.backend, "status": run.status, "metrics": run.metrics or {},
            "duration_seconds": run.duration_seconds,
        },
        "final_configuration": run.config or {},
        "dataset_summary": dataset,
        "security_timeline": timeline,
        "checkpoint_comparison": comparison,
        "recommendations": recommendations,
        "accepted_recommendations": accepted,
        "rejected_recommendations": rejected,
        "final_models": final_models,
        "benchmarks": benchmarks,
        "best_benchmark": best_benchmark,
        "evaluation": evaluation,
        "deployment_recommendation": deployment_recommendation,
        "remaining_risks": sorted(set(remaining)),
    }

