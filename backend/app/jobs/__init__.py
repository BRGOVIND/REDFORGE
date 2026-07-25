"""Execution Platform / Job System (RedForge V3, Epic 2).

The unified, domain-agnostic engine for all long-running work (Constitution §8).
Future engines submit Jobs instead of executing directly. A Platform Service
(Layer ③): depended upon by domain engines, depends on none of them.

Layering: domain (pure) → repository (persistence) → service (scheduler/worker).
Handlers are registered per kind (provider pattern); a new kind is a new handler.
"""
from app.jobs.domain import Job, JobError, JobProgress, JobResult, JobStatus
from app.jobs.handlers import JobContext, JobHandlerRegistry, handler_registry
from app.jobs.job_types import JobTypeDef, get_job_type, list_job_types, register_job_type
from app.jobs.repository import JobRepository, SqlJobRepository
from app.jobs.service import JobService, job_service

__all__ = [
    "Job", "JobStatus", "JobProgress", "JobResult", "JobError",
    "JobContext", "JobHandlerRegistry", "handler_registry",
    "JobTypeDef", "get_job_type", "list_job_types", "register_job_type",
    "JobRepository", "SqlJobRepository",
    "JobService", "job_service",
]
