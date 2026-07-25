"""Hardware Compatibility Engine (RedForge V3) — a first-class, provider-agnostic
subsystem that detects the GPU, estimates a training run's VRAM need, chooses safe
defaults, and blocks/recommends before an impossible job ever reaches a provider."""
from __future__ import annotations

from app.hardware.domain import Assessment, GpuProfile, MemoryEstimate, SafeDefaults, Verdict
from app.hardware.engine import HardwareCompatibilityEngine, hardware_engine
from app.hardware.service import HardwareService, hardware_service, detect_gpu

__all__ = [
    "Assessment", "GpuProfile", "MemoryEstimate", "SafeDefaults", "Verdict",
    "HardwareCompatibilityEngine", "hardware_engine",
    "HardwareService", "hardware_service", "detect_gpu",
]
