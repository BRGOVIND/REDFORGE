"""Training provider abstraction — the swappable backend interface.

A provider runs a LoRA/QLoRA job and yields :class:`ProgressEvent`s. The Training
Manager and runner know only this interface; Unsloth/PEFT/etc. live behind
concrete providers so nothing else in the app hardcodes a training backend.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, AsyncIterator, Optional


@dataclass
class TrainingConfig:
    """Canonical training configuration (provider-agnostic)."""

    base_model: str
    method: str = "lora"            # "lora" | "qlora"
    epochs: int = 3
    learning_rate: float = 2e-4
    batch_size: int = 2
    gradient_accumulation: int = 4
    rank: int = 16                  # LoRA r
    alpha: int = 32                 # LoRA alpha
    dropout: float = 0.05
    scheduler: str = "cosine"
    optimizer: str = "adamw_8bit"
    warmup_steps: int = 10
    max_seq_length: int = 2048
    seed: int = 42
    validation_split: float = 0.1
    output_dir: str = ""
    # Dataset payload (records) passed in so providers stay storage-agnostic.
    dataset_records: list[Any] = field(default_factory=list)

    def public(self) -> dict:
        d = asdict(self)
        d.pop("dataset_records", None)  # never echo the data back in config views
        return d


@dataclass
class ProgressEvent:
    """One tick of training progress. Streamed to the live dashboard."""

    status: str                     # running | completed | failed | cancelled | paused
    step: int = 0
    total_steps: int = 0
    epoch: float = 0.0
    total_epochs: int = 0
    loss: Optional[float] = None
    val_loss: Optional[float] = None
    learning_rate: Optional[float] = None
    steps_per_sec: Optional[float] = None
    eta_seconds: Optional[float] = None
    message: str = ""
    checkpoint: Optional[dict] = None   # {step, epoch, loss, val_loss, path, is_best}

    def to_dict(self) -> dict:
        return asdict(self)


class TrainingProvider(ABC):
    """Interface every training backend implements."""

    name: str = "provider"
    label: str = "Provider"

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """(available, reason). ``False`` ⇒ the backend can't run here yet
        (missing ML stack / no GPU) and the reason is shown to the user."""
        ...

    @abstractmethod
    def run(self, config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:
        """Async-generate progress events for one run. ``cancel`` is a callable
        returning True when the run should stop (pause/cancel). Must be
        cancellation-cooperative and never raise raw backend errors — wrap them
        in a failed ProgressEvent."""
        ...
