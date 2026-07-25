"""Global Task Manager — the unified Task view over the Execution Platform.

RedForge has exactly ONE execution engine: the Job System (``app/jobs``). This module
is a thin, read-only PROJECTION of a Job into the professional "Task" shape the UI
needs (Docker-Desktop-style): a human label, integer percent, current step, elapsed +
estimated-remaining time, cancel/retry eligibility, and a log tail. It adds NO new
state — every field derives from the Job — so there is a single source of truth.

ETA is computed from the Job's rolling progress samples (a moving average of the real
progress rate), never a fabricated countdown.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Human-friendly labels for the job kinds RedForge runs. Unknown kinds fall back to a
# title-cased version of the type, so a new kind needs no change here to appear.
_LABELS = {
    "training": "Training",
    "export": "Export",
    "dataset_processing": "Dataset processing",
    "dataset_import": "Dataset import",
    "runtime_discovery": "Runtime scan",
    "runtime_model_discovery": "Model discovery",
    "benchmark": "Benchmark",
    "evaluation": "Evaluation",
    "red_team": "Red-team attack",
    "security_scan": "Security scan",
    "model_download": "Model download",
    "gguf_export": "GGUF export",
    "ollama_export": "Ollama export",
    "report": "Report generation",
    "workspace_index": "Workspace indexing",
    "health_check": "Health check",
}

_ACTIVE = ("queued", "running", "paused")
_RETRYABLE = ("failed", "cancelled", "interrupted")


def label_for(job_type: str) -> str:
    return _LABELS.get(job_type, (job_type or "task").replace("_", " ").title())


def _parse(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _elapsed_seconds(job: dict, now: datetime) -> Optional[float]:
    start = _parse(job.get("started_at")) or _parse(job.get("created_at"))
    if start is None:
        return None
    end = _parse(job.get("completed_at")) or now
    return max(0.0, (end - start).total_seconds())


def estimate_eta_seconds(job: dict, now: datetime) -> Optional[float]:
    """Remaining seconds from the moving-average progress rate. None when unknown
    (not enough samples, stalled, or not running)."""
    if job.get("status") != "running":
        return None
    fraction = float((job.get("progress") or {}).get("fraction") or 0.0)
    if fraction <= 0.0 or fraction >= 1.0:
        return None
    samples = (job.get("metadata") or {}).get("_eta_samples") or []
    pts = [(_parse(ts), float(f)) for ts, f in samples if _parse(ts) is not None]
    pts = [p for p in pts if p[0] is not None]
    if len(pts) >= 2:
        # Rate over the sampled window (oldest → newest), robust to per-step jitter.
        (t0, f0), (t1, f1) = pts[0], pts[-1]
        dt = (t1 - t0).total_seconds()
        df = f1 - f0
        if dt > 0 and df > 1e-6:
            return max(0.0, (1.0 - f1) / (df / dt))
    # Fallback: average rate since the run started.
    elapsed = _elapsed_seconds(job, now)
    if elapsed and elapsed > 0 and fraction > 0:
        return max(0.0, (1.0 - fraction) / (fraction / elapsed))
    return None


def to_task(job: dict, now: Optional[datetime] = None) -> dict:
    """Project one Job dict into a Task dict (all fields derived from the Job)."""
    now = now or _now()
    prog = job.get("progress") or {}
    status = job.get("status", "queued")
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 1)
    retryable = status in _RETRYABLE and not (status == "failed" and attempts >= max_attempts)
    title = job.get("target_ref") or (job.get("params") or {}).get("name") \
        or (job.get("metadata") or {}).get("title") or label_for(job.get("type", ""))
    return {
        "id": job.get("id"),
        "kind": job.get("type"),
        "label": label_for(job.get("type", "")),
        "title": title,
        "status": status,
        "progress": int(round(float(prog.get("fraction") or 0.0) * 100)),  # 0–100
        "step": prog.get("step"),
        "total": prog.get("total"),
        "current_step": prog.get("message") or "",
        "elapsed_seconds": _elapsed_seconds(job, now),
        "eta_seconds": estimate_eta_seconds(job, now),
        "cancellable": status in _ACTIVE,
        "retryable": retryable,
        "logs_tail": (job.get("logs") or [])[-3:],
        "error": (job.get("error") or {}).get("message") if job.get("error") else None,
        "artifact_ids": (job.get("result") or {}).get("artifact_ids") or [],
        "project_id": job.get("project_id"),
        "experiment_id": job.get("experiment_id"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
    }


def summarize(tasks: list[dict]) -> dict:
    """Aggregate counts for the top-bar indicator ("Running (N)")."""
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    return {
        "running": counts.get("running", 0),
        "queued": counts.get("queued", 0),
        "paused": counts.get("paused", 0),
        "active": counts.get("running", 0) + counts.get("queued", 0) + counts.get("paused", 0),
        "failed": counts.get("failed", 0),
        "completed": counts.get("completed", 0),
        "by_status": counts,
    }
