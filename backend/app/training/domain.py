"""Training Platform — pure V3 domain model (RedForge V3, Epic 3).

The V3 training domain (Constitution §5.6–§5.8, §10). Pure: no SQLAlchemy, no
FastAPI. Distinct from the legacy ``app/training/service.py`` + ``training_runs``
table (strangler-fig) — additive, driven by the Job System, publishing Artifacts.

The three axes are separated (§10.2): **strategy** (what algorithm — this module +
``strategies.py``), **provider** (who executes — reuses the existing
``TrainingProvider`` implementations), and **execution** (how — ``execution.py``,
via the Job System).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _coerce(enum_cls, value, default):
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


@dataclass
class HyperparameterSet:
    """Strategy-agnostic hyperparameters. Strategy-specific ones (rank/alpha for
    LoRA, beta for DPO) live in the strategy spec's ``params`` — see strategies.py."""
    epochs: int = 3
    learning_rate: float = 2e-4
    batch_size: int = 2
    gradient_accumulation: int = 4
    warmup_steps: int = 10
    max_seq_length: int = 2048
    scheduler: str = "cosine"
    optimizer: str = "adamw_8bit"
    seed: int = 42
    validation_split: float = 0.1

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "epochs", "learning_rate", "batch_size", "gradient_accumulation", "warmup_steps",
            "max_seq_length", "scheduler", "optimizer", "seed", "validation_split")}

    @staticmethod
    def from_dict(d: dict) -> "HyperparameterSet":
        return HyperparameterSet(**{k: v for k, v in (d or {}).items()
                                    if k in HyperparameterSet().to_dict()})


@dataclass
class AdapterConfiguration:
    """LoRA/QLoRA adapter parameters (empty for full-finetune strategies)."""
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05

    def to_dict(self) -> dict:
        return {"rank": self.rank, "alpha": self.alpha, "dropout": self.dropout}


@dataclass
class TrainingEstimate:
    """A resource estimate produced before launch (Constitution §10, resource est.)."""
    vram_mb: int = 0
    disk_mb: int = 0
    duration_seconds: float = 0.0
    checkpoint_size_mb: int = 0
    adapter_size_mb: int = 0
    fits_hardware: bool = True
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"vram_mb": self.vram_mb, "disk_mb": self.disk_mb,
                "duration_seconds": round(self.duration_seconds, 1),
                "checkpoint_size_mb": self.checkpoint_size_mb, "adapter_size_mb": self.adapter_size_mb,
                "fits_hardware": self.fits_hardware, "warnings": self.warnings}


@dataclass
class TrainingCheckpoint:
    id: str
    run_id: str
    step: int
    epoch: float = 0.0
    loss: Optional[float] = None
    val_loss: Optional[float] = None
    path: str = ""
    is_best: bool = False
    artifact_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "run_id": self.run_id, "step": self.step, "epoch": self.epoch,
                "loss": self.loss, "val_loss": self.val_loss, "path": self.path,
                "is_best": self.is_best, "artifact_id": self.artifact_id,
                "created_at": self.created_at.isoformat() if self.created_at else None}


@dataclass
class TrainingConfiguration:
    """The full, provider-agnostic configuration for a run: what to train, on what,
    with which strategy and hyperparameters."""
    foundation_model_id: Optional[str]
    base_model: str
    dataset_id: Optional[str]
    dataset_version: Optional[int]
    strategy: str = "lora"
    provider: str = "simulation"
    hyperparameters: HyperparameterSet = field(default_factory=HyperparameterSet)
    adapter: AdapterConfiguration = field(default_factory=AdapterConfiguration)
    strategy_params: dict = field(default_factory=dict)     # DPO beta, PPO kl_coef, etc.

    def to_dict(self) -> dict:
        return {"foundation_model_id": self.foundation_model_id, "base_model": self.base_model,
                "dataset_id": self.dataset_id, "dataset_version": self.dataset_version,
                "strategy": self.strategy, "provider": self.provider,
                "hyperparameters": self.hyperparameters.to_dict(),
                "adapter": self.adapter.to_dict(), "strategy_params": self.strategy_params}


@dataclass
class TrainingRun:
    """A V3 training run aggregate."""
    id: str
    name: str
    configuration: TrainingConfiguration
    status: TrainingStatus = TrainingStatus.CREATED
    metrics: dict = field(default_factory=dict)
    estimate: Optional[TrainingEstimate] = None
    job_id: Optional[str] = None
    project_id: Optional[str] = None
    output_dir: str = ""
    logs: list[str] = field(default_factory=list)
    error: Optional[str] = None
    run_artifact_id: Optional[str] = None
    adapter_artifact_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "configuration": self.configuration.to_dict(),
            "status": self.status.value, "metrics": self.metrics or {},
            "estimate": self.estimate.to_dict() if self.estimate else None,
            "job_id": self.job_id, "project_id": self.project_id, "output_dir": self.output_dir,
            "logs": self.logs or [], "error": self.error,
            "run_artifact_id": self.run_artifact_id, "adapter_artifact_id": self.adapter_artifact_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @staticmethod
    def coerce_status(value) -> TrainingStatus:
        return _coerce(TrainingStatus, value, TrainingStatus.CREATED)
