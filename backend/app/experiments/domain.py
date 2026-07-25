"""Experiment Platform — pure domain model (RedForge V3, Epic 4).

The Experiment is the operator's primary unit of work (Constitution §3.3, §5.3, §7):
a single line of inquiry that owns a subject (foundation model + dataset), a
configuration, and — by *reference* — the training runs, jobs, artifacts, timeline,
metrics, notes, and reports produced under it.

Crucially, an Experiment **references and contextualizes**; it never produces or
stores the entities themselves (those live in their own contexts). Pure: no
SQLAlchemy, no FastAPI. Associations are learned from the Event Bus, not by importing
the engines (§14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CONCLUDED = "concluded"
    ARCHIVED = "archived"


def _coerce(enum_cls, value, default):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


@dataclass
class ExperimentConfiguration:
    """The experiment's subject + intended training plan (the recipe)."""
    foundation_model_id: Optional[str] = None
    base_model: str = ""
    dataset_id: Optional[str] = None
    dataset_version: Optional[int] = None
    strategy: str = "lora"
    provider: Optional[str] = None
    hyperparameters: dict = field(default_factory=dict)
    adapter: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"foundation_model_id": self.foundation_model_id, "base_model": self.base_model,
                "dataset_id": self.dataset_id, "dataset_version": self.dataset_version,
                "strategy": self.strategy, "provider": self.provider,
                "hyperparameters": self.hyperparameters, "adapter": self.adapter}

    @staticmethod
    def from_dict(d: dict) -> "ExperimentConfiguration":
        d = d or {}
        return ExperimentConfiguration(
            foundation_model_id=d.get("foundation_model_id"), base_model=d.get("base_model", ""),
            dataset_id=d.get("dataset_id"), dataset_version=d.get("dataset_version"),
            strategy=d.get("strategy", "lora"), provider=d.get("provider"),
            hyperparameters=d.get("hyperparameters", {}), adapter=d.get("adapter", {}))


@dataclass
class ExperimentSnapshot:
    """A point-in-time capture that makes the experiment reproducible: the exact
    subject + plan + environment at the moment of capture (Constitution §7 snapshots)."""
    foundation_model: dict = field(default_factory=dict)
    dataset_version: Optional[int] = None
    dataset_content_hash: str = ""
    strategy: str = ""
    provider: str = ""
    hyperparameters: dict = field(default_factory=dict)
    resource_estimate: dict = field(default_factory=dict)
    gpu: dict = field(default_factory=dict)
    redforge_version: str = ""
    platform: dict = field(default_factory=dict)
    captured_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"foundation_model": self.foundation_model, "dataset_version": self.dataset_version,
                "dataset_content_hash": self.dataset_content_hash, "strategy": self.strategy,
                "provider": self.provider, "hyperparameters": self.hyperparameters,
                "resource_estimate": self.resource_estimate, "gpu": self.gpu,
                "redforge_version": self.redforge_version, "platform": self.platform,
                "captured_at": self.captured_at.isoformat() if self.captured_at else None}


@dataclass
class ExperimentTimelineEvent:
    id: str
    experiment_id: str
    kind: str                              # e.g. training.started, checkpoint.created, note
    title: str
    payload: dict = field(default_factory=dict)
    source: str = "system"                 # "system" | "user"
    at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "experiment_id": self.experiment_id, "kind": self.kind,
                "title": self.title, "payload": self.payload, "source": self.source,
                "at": self.at.isoformat() if self.at else None}


@dataclass
class ExperimentNote:
    id: str
    experiment_id: str
    body: str                              # Markdown
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "experiment_id": self.experiment_id, "body": self.body,
                "created_at": self.created_at.isoformat() if self.created_at else None}


@dataclass
class ExperimentJobReference:
    experiment_id: str
    job_id: str
    job_type: str = ""
    status: str = ""
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"experiment_id": self.experiment_id, "job_id": self.job_id,
                "job_type": self.job_type, "status": self.status,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


@dataclass
class Experiment:
    id: str
    name: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    description: str = ""
    configuration: ExperimentConfiguration = field(default_factory=ExperimentConfiguration)
    snapshot: Optional[ExperimentSnapshot] = None
    tags: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)      # {key: value}
    project_id: Optional[str] = None
    parent_experiment_id: Optional[str] = None       # set for clones
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    concluded_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "status": self.status.value,
            "description": self.description, "configuration": self.configuration.to_dict(),
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "tags": self.tags or [], "metrics": self.metrics or {}, "project_id": self.project_id,
            "parent_experiment_id": self.parent_experiment_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "concluded_at": self.concluded_at.isoformat() if self.concluded_at else None,
        }

    @staticmethod
    def coerce_status(value) -> ExperimentStatus:
        return _coerce(ExperimentStatus, value, ExperimentStatus.DRAFT)
