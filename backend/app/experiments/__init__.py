"""Experiment Platform (RedForge V3, Epic 4).

The Experiment is the operator's primary unit of work (Constitution §3.3, §5.3, §7):
the aggregation root that references — never owns — the runs, jobs, and artifacts
produced under it, building its timeline by observing the Event Bus. Additive and
local-only; integrates with every existing context without importing the engines.
"""
from app.experiments.domain import (
    Experiment,
    ExperimentConfiguration,
    ExperimentJobReference,
    ExperimentNote,
    ExperimentSnapshot,
    ExperimentStatus,
    ExperimentTimelineEvent,
)
from app.experiments.repository import (
    ExperimentRepository,
    JobRefRepository,
    NoteRepository,
    SqlExperimentRepository,
    SqlJobRefRepository,
    SqlNoteRepository,
    SqlTimelineRepository,
    TimelineRepository,
)
from app.experiments.service import ExperimentService, experiment_service
from app.experiments.subscriber import register_experiment_subscribers

__all__ = [
    "Experiment", "ExperimentStatus", "ExperimentConfiguration", "ExperimentSnapshot",
    "ExperimentTimelineEvent", "ExperimentNote", "ExperimentJobReference",
    "ExperimentRepository", "TimelineRepository", "NoteRepository", "JobRefRepository",
    "SqlExperimentRepository", "SqlTimelineRepository", "SqlNoteRepository", "SqlJobRefRepository",
    "ExperimentService", "experiment_service", "register_experiment_subscribers",
]
