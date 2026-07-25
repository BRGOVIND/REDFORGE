"""Training resource estimation (RedForge V3, Epic 3).

Before a run launches, estimate VRAM / disk / duration / checkpoint & adapter size
and warn if the configuration exceeds available hardware (Constitution §10, resource
estimation). Deterministic and dependency-light — reuses the existing model-size
table and hardware detection. Rough by design (a UI ballpark), and honestly labeled.
"""
from __future__ import annotations

from app.training.domain import TrainingConfiguration, TrainingEstimate
from app.training.strategies import get_strategy

# VRAM multipliers over the model's rough weight footprint, by strategy family.
_VRAM_FACTOR = {"qlora": 0.35, "lora": 0.7, "sft": 1.6}
# Adapter size is small and rank-driven; full fine-tune checkpoint ≈ model size.
_ADAPTER_BASE_MB = 40


def estimate(config: TrainingConfiguration, *, record_count: int = 0) -> TrainingEstimate:
    from app.runtime.model_sizes import estimate_model_ram_mb

    model_mb = estimate_model_ram_mb(config.base_model)
    strat = get_strategy(config.strategy)
    factor = _VRAM_FACTOR.get(config.strategy, 0.7)
    vram_mb = int(model_mb * factor)

    if strat.adapter_based:
        adapter_mb = _ADAPTER_BASE_MB + config.adapter.rank * 4
        checkpoint_mb = adapter_mb           # adapter checkpoints are small
    else:
        adapter_mb = 0
        checkpoint_mb = model_mb             # full fine-tune saves full weights

    # Disk: a few checkpoints + the final adapter/model + logs headroom.
    disk_mb = checkpoint_mb * 4 + adapter_mb + 200

    # Duration: rough — steps ≈ records/effective_batch × epochs, ~0.3s/step (sim),
    # scaled up for real backends. Purely a ballpark.
    hp = config.hyperparameters
    eff_batch = max(1, hp.batch_size * hp.gradient_accumulation)
    steps = max(1, (record_count or 100) // eff_batch) * max(1, hp.epochs)
    per_step = 0.3 if config.provider in ("simulation", "mock") else 2.5
    duration = steps * per_step

    warnings: list[str] = []
    fits = True
    try:
        from app.resources import detect_resources
        snap = detect_resources().to_dict()
        gpu = snap.get("gpu") or {}
        gpu_total = gpu.get("total_mb")
        if config.provider not in ("simulation", "mock"):
            if not gpu.get("available"):
                warnings.append("No GPU detected — real training will not run on this machine.")
                fits = False
            elif gpu_total and vram_mb > gpu_total:
                warnings.append(f"Estimated VRAM ({vram_mb} MB) exceeds detected GPU ({gpu_total} MB). "
                                "Try QLoRA, a smaller model, or lower batch size.")
                fits = False
        disk_free = snap.get("disk_free_mb")
        if disk_free and disk_mb > disk_free:
            warnings.append(f"Estimated disk ({disk_mb} MB) exceeds free space ({disk_free} MB).")
    except Exception:  # noqa: BLE001 - estimation must never break launch
        pass

    if not strat.implemented:
        warnings.append(f"Strategy '{config.strategy}' is architecture-only and not yet runnable.")

    return TrainingEstimate(
        vram_mb=vram_mb, disk_mb=disk_mb, duration_seconds=duration,
        checkpoint_size_mb=checkpoint_mb, adapter_size_mb=adapter_mb,
        fits_hardware=fits, warnings=warnings)
