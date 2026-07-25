"""Hardware Compatibility Engine — application service (RedForge V3).

Composes real hardware detection (``app.resources``) + model-size inference
(``app.runtime.model_sizes``) with the pure :class:`HardwareCompatibilityEngine`.
This is the seam the rest of the app calls: training launch pre-flight, and a
``/api/hardware`` endpoint for the wizard to check compatibility before a run.

First-class + provider-agnostic: it knows nothing about Unsloth/HF; it reasons about
parameter count, strategy and hyperparameters, so it governs every training backend.
"""
from __future__ import annotations

from typing import Optional

from app.hardware.domain import Assessment, GpuProfile
from app.hardware.engine import hardware_engine
from app.logging_config import get_logger

logger = get_logger("hardware")


def detect_gpu() -> GpuProfile:
    """Detect the training device via the existing resource monitor (never raises)."""
    try:
        from app.resources import detect_resources
        snap = detect_resources().to_dict()
        gpu = snap.get("gpu") or {}
        return GpuProfile(
            available=bool(gpu.get("available")), name=gpu.get("name"),
            total_mb=gpu.get("total_mb"), free_mb=gpu.get("free_mb"),
            backend=gpu.get("backend"))
    except Exception as exc:  # noqa: BLE001 - detection is advisory; never break callers
        logger.warning("GPU detection failed: %s", exc)
        return GpuProfile(available=False)


def _param_billions(model_ref: str) -> Optional[float]:
    try:
        from app.runtime.model_sizes import parse_param_billions
        return parse_param_billions(model_ref)
    except Exception:  # noqa: BLE001
        return None


class HardwareService:
    """Public API of the Hardware Compatibility subsystem."""

    def snapshot(self) -> dict:
        """The detected training hardware (for the UI / diagnostics)."""
        return detect_gpu().to_dict()

    def assess(self, *, base_model: str, strategy: str = "qlora",
               max_seq_length: int = 2048, batch_size: int = 2,
               gradient_accumulation: int = 4, provider: Optional[str] = None) -> Assessment:
        """Assess whether a training request fits the detected GPU. For the guaranteed
        -available Simulation/mock backends there is no GPU requirement, so this always
        returns a trivially-fitting assessment."""
        gpu = detect_gpu()
        pb = _param_billions(base_model)
        return hardware_engine.assess(
            parameter_billions=pb, strategy=strategy, max_seq_length=max_seq_length,
            batch_size=batch_size, gradient_accumulation=gradient_accumulation, gpu=gpu)

    def check(self, *, base_model: str, strategy: str = "qlora",
              hyperparameters: Optional[dict] = None, provider: Optional[str] = None) -> dict:
        """Convenience wrapper returning a plain dict for the API/pre-flight."""
        hp = hyperparameters or {}
        assessment = self.assess(
            base_model=base_model, strategy=strategy,
            max_seq_length=int(hp.get("max_seq_length", 2048)),
            batch_size=int(hp.get("batch_size", 2)),
            gradient_accumulation=int(hp.get("gradient_accumulation", 4)),
            provider=provider)
        return assessment.to_dict()


hardware_service = HardwareService()
