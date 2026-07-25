"""Execution Platform — pure domain model (RedForge V3, Epic 2).

The Job is the universal unit of long-running, backgrounded, recoverable work
(Constitution §5.22, §8). Every future engine submits Jobs instead of executing
directly; the Execution Platform is domain-agnostic — it knows how to run *a job*,
not how to train or benchmark (that is the registered handler's job).

Pure domain: no SQLAlchemy, no FastAPI, no I/O. The canonical Job state machine
(§8.3) is enforced here so no job kind can invent its own states, and a failed job
can never carry a null reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    """The canonical job lifecycle (Constitution §8.3). Every kind obeys exactly
    this set — no kind defines its own states."""
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"     # process died mid-run; set by recovery

    @property
    def is_terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


def _coerce(enum_cls, value, default):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


@dataclass
class JobProgress:
    """A job's live progress. ``fraction`` is 0–1; step/total are optional detail."""
    fraction: float = 0.0
    step: Optional[int] = None
    total: Optional[int] = None
    message: str = ""
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"fraction": round(self.fraction, 4), "step": self.step, "total": self.total,
                "message": self.message,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


@dataclass
class JobError:
    """A structured, never-null failure reason (Constitution §8.3)."""
    message: str
    kind: str = "error"
    traceback: str = ""

    def to_dict(self) -> dict:
        return {"message": self.message, "kind": self.kind, "traceback": self.traceback}


@dataclass
class JobResult:
    """A handler's outcome. ``artifact_ids`` records artifacts the job produced —
    the Job → Artifact publish flow (Constitution §8, §13)."""
    success: bool = True
    data: dict = field(default_factory=dict)
    artifact_ids: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data,
                "artifact_ids": self.artifact_ids, "message": self.message}


@dataclass
class Job:
    """The aggregate. ``type`` is an extensible kind key; ``concurrency_key`` groups
    jobs for per-kind concurrency limits; ``target_ref`` names what the job acts on."""

    id: str
    type: str
    status: JobStatus = JobStatus.QUEUED
    params: dict = field(default_factory=dict)
    target_ref: Optional[str] = None
    project_id: Optional[str] = None
    experiment_id: Optional[str] = None      # associates the job (+ its artifacts) to an Experiment
    priority: int = 0                                  # higher runs sooner
    progress: JobProgress = field(default_factory=JobProgress)
    result: Optional[JobResult] = None
    error: Optional[JobError] = None
    logs: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 1
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "status": self.status.value,
            "params": self.params or {}, "target_ref": self.target_ref,
            "project_id": self.project_id, "experiment_id": self.experiment_id,
            "priority": self.priority,
            "progress": self.progress.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "error": self.error.to_dict() if self.error else None,
            "logs": self.logs or [], "attempts": self.attempts, "max_attempts": self.max_attempts,
            "metadata": self.metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @staticmethod
    def coerce_status(value) -> JobStatus:
        return _coerce(JobStatus, value, JobStatus.QUEUED)
