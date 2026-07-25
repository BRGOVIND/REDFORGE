"""Execution Platform — repository layer (RedForge V3, Epic 2).

Dependency inversion: the JobService/execution engine depend on
:class:`JobRepository`, never on SQLAlchemy. Maps ``JobRecord`` rows ↔ pure
:class:`Job` domain objects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import select

from app.jobs.domain import Job, JobError, JobProgress, JobResult, JobStatus


class JobRepository(ABC):
    @abstractmethod
    async def add(self, job: Job) -> Job: ...

    @abstractmethod
    async def get(self, job_id: str) -> Optional[Job]: ...

    @abstractmethod
    async def update(self, job: Job) -> Optional[Job]: ...

    @abstractmethod
    async def list(self, *, status: Optional[str] = None, type: Optional[str] = None,
                   project_id: Optional[str] = None, limit: int = 200) -> list[Job]: ...

    @abstractmethod
    async def count_active_by_type(self) -> dict[str, int]: ...


class SqlJobRepository(JobRepository):
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    @staticmethod
    def _to_domain(row) -> Job:
        progress = JobProgress(
            fraction=row.progress_fraction or 0.0, step=row.progress_step,
            total=row.progress_total, message=row.progress_message or "")
        result = None
        if row.result is not None:
            result = JobResult(success=row.result.get("success", True),
                               data=row.result.get("data", {}),
                               artifact_ids=row.result.get("artifact_ids", []),
                               message=row.result.get("message", ""))
        error = None
        if row.error:
            detail = row.error_detail or {}
            error = JobError(message=row.error, kind=detail.get("kind", "error"),
                             traceback=detail.get("traceback", ""))
        md = dict(row.job_metadata or {})
        return Job(
            id=row.id, type=row.type, status=Job.coerce_status(row.status),
            params=dict(row.params or {}), target_ref=row.target_ref, project_id=row.project_id,
            experiment_id=md.get("experiment_id"),
            priority=row.priority or 0, progress=progress, result=result, error=error,
            logs=list(row.logs or []), attempts=row.attempts or 0, max_attempts=row.max_attempts or 1,
            metadata=md,
            created_at=row.created_at, started_at=row.started_at, completed_at=row.completed_at,
        )

    @staticmethod
    def _apply(row, j: Job) -> None:
        row.type = j.type
        row.status = j.status.value
        row.params = j.params or {}
        row.target_ref = j.target_ref
        row.project_id = j.project_id
        row.priority = j.priority
        row.progress_fraction = j.progress.fraction
        row.progress_step = j.progress.step
        row.progress_total = j.progress.total
        row.progress_message = j.progress.message
        row.result = j.result.to_dict() if j.result else None
        row.error = j.error.message if j.error else None
        row.error_detail = {"kind": j.error.kind, "traceback": j.error.traceback} if j.error else None
        row.logs = j.logs or []
        row.attempts = j.attempts
        row.max_attempts = j.max_attempts
        # experiment_id rides in job_metadata (no schema change to the jobs table).
        md = dict(j.metadata or {})
        if j.experiment_id:
            md["experiment_id"] = j.experiment_id
        row.job_metadata = md
        row.started_at = j.started_at
        row.completed_at = j.completed_at

    async def add(self, job: Job) -> Job:
        from app.db.models import JobRecord
        row = JobRecord(id=job.id, created_at=job.created_at)
        self._apply(row, job)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, job_id: str) -> Optional[Job]:
        from app.db.models import JobRecord
        async with self._factory()() as db:
            row = await db.get(JobRecord, job_id)
            return self._to_domain(row) if row else None

    async def update(self, job: Job) -> Optional[Job]:
        from app.db.models import JobRecord
        async with self._factory()() as db:
            row = await db.get(JobRecord, job.id)
            if row is None:
                return None
            self._apply(row, job)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def list(self, *, status=None, type=None, project_id=None, limit: int = 200) -> list[Job]:
        from app.db.models import JobRecord
        stmt = select(JobRecord).order_by(JobRecord.created_at.desc())
        if status is not None:
            stmt = stmt.where(JobRecord.status == status)
        if type is not None:
            stmt = stmt.where(JobRecord.type == type)
        if project_id is not None:
            stmt = stmt.where(JobRecord.project_id == project_id)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def delete(self, job_id: str) -> bool:
        """Remove a job record (task-history delete). Additive; callers gate this to
        terminal jobs."""
        from app.db.models import JobRecord
        async with self._factory()() as db:
            row = await db.get(JobRecord, job_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def count_active_by_type(self) -> dict[str, int]:
        from app.db.models import JobRecord
        async with self._factory()() as db:
            rows = (await db.execute(
                select(JobRecord).where(JobRecord.status == JobStatus.RUNNING.value))).scalars().all()
        counts: dict[str, int] = {}
        for r in rows:
            counts[r.type] = counts.get(r.type, 0) + 1
        return counts
