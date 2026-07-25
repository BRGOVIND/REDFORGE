"""Hardware Compatibility Engine — domain (RedForge V3).

Pure, dependency-free value objects. No SQLAlchemy, no I/O, no provider knowledge —
this is the vocabulary the engine reasons in. Memory is always in MB (ints) so the
whole subsystem speaks one unit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Verdict(str, Enum):
    """Can this (model, strategy, hyperparameters) train on this GPU?"""
    FITS = "fits"            # fits comfortably as requested
    TIGHT = "tight"          # only fits after applying safe (reduced) defaults
    INSUFFICIENT = "insufficient"  # will not fit even at minimum settings → block


@dataclass(frozen=True)
class GpuProfile:
    """What we detected about the training device."""
    available: bool
    name: Optional[str] = None
    total_mb: Optional[int] = None
    free_mb: Optional[int] = None
    backend: Optional[str] = None   # "cuda" / "metal" / …

    def usable_mb(self) -> Optional[int]:
        """VRAM we can realistically allocate for a job right now. Prefer measured
        free memory; fall back to a fraction of total (leave headroom for the
        driver/display/other allocations). None when no GPU."""
        if not self.available:
            return None
        if self.free_mb:
            return self.free_mb
        if self.total_mb:
            return int(self.total_mb * 0.90)
        return None

    def to_dict(self) -> dict:
        return {"available": self.available, "name": self.name, "total_mb": self.total_mb,
                "free_mb": self.free_mb, "backend": self.backend, "usable_mb": self.usable_mb()}


@dataclass(frozen=True)
class MemoryEstimate:
    """A broken-down training-memory estimate (MB) so the reason is auditable, never
    a single opaque number."""
    weights_mb: int
    optimizer_mb: int          # LoRA/optimizer + gradient states
    activations_mb: int        # forward/backward activations (with grad checkpointing)
    overhead_mb: int           # CUDA context + kernels + fragmentation reserve
    total_mb: int

    def to_dict(self) -> dict:
        return {"weights_mb": self.weights_mb, "optimizer_mb": self.optimizer_mb,
                "activations_mb": self.activations_mb, "overhead_mb": self.overhead_mb,
                "total_mb": self.total_mb}


@dataclass(frozen=True)
class SafeDefaults:
    """Hyperparameter overrides the engine chose to make a run fit. Empty when the
    requested settings already fit (or nothing can make it fit)."""
    max_seq_length: Optional[int] = None
    batch_size: Optional[int] = None
    gradient_accumulation: Optional[int] = None
    gradient_checkpointing: Optional[str] = None   # "unsloth" | "true" | None

    def as_overrides(self) -> dict:
        return {k: v for k, v in {
            "max_seq_length": self.max_seq_length, "batch_size": self.batch_size,
            "gradient_accumulation": self.gradient_accumulation,
        }.items() if v is not None}

    def to_dict(self) -> dict:
        return {"max_seq_length": self.max_seq_length, "batch_size": self.batch_size,
                "gradient_accumulation": self.gradient_accumulation,
                "gradient_checkpointing": self.gradient_checkpointing}


@dataclass(frozen=True)
class Assessment:
    """The engine's verdict for a training request on a device."""
    verdict: Verdict
    gpu: GpuProfile
    parameter_billions: Optional[float]
    strategy: str
    estimate_requested: MemoryEstimate
    estimate_safe: MemoryEstimate
    usable_mb: Optional[int]
    headroom_mb: Optional[int]          # usable - estimate we'll actually use (MB)
    safe_defaults: SafeDefaults
    reason: str
    warnings: list[str] = field(default_factory=list)
    recommended_max_billions: Optional[float] = None
    recommended_models: list[str] = field(default_factory=list)

    @property
    def can_launch(self) -> bool:
        return self.verdict in (Verdict.FITS, Verdict.TIGHT)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "can_launch": self.can_launch,
            "gpu": self.gpu.to_dict(),
            "parameter_billions": self.parameter_billions,
            "strategy": self.strategy,
            "estimate_requested": self.estimate_requested.to_dict(),
            "estimate_safe": self.estimate_safe.to_dict(),
            "usable_mb": self.usable_mb,
            "headroom_mb": self.headroom_mb,
            "safe_defaults": self.safe_defaults.to_dict(),
            "reason": self.reason,
            "warnings": list(self.warnings),
            "recommended_max_billions": self.recommended_max_billions,
            "recommended_models": list(self.recommended_models),
        }
