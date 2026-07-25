"""Hardware Compatibility Engine — pure, deterministic reasoning (RedForge V3).

Estimates the GPU memory a training run needs and decides whether it fits the
detected device, choosing safe defaults or recommending a smaller model when it does
not. It is **provider-agnostic**: it reasons from parameter count + strategy +
hyperparameters, never from Unsloth/HF internals, so it applies to every training
backend. No I/O here (detection + persistence live in the service) — this class is a
pure function of its inputs and is fully unit-testable offline.

The memory model is a transparent, documented sum (all MB):

    total = weights + optimizer/grad states + activations + fixed overhead

with per-strategy coefficients below. It is intentionally *conservative* (it would
rather warn than let a run OOM mid-load). Coefficients are module constants so they
are auditable and tunable, not magic numbers buried in code.
"""
from __future__ import annotations

from typing import Optional

from app.hardware.domain import (
    Assessment, GpuProfile, MemoryEstimate, SafeDefaults, Verdict,
)

_GB = 1024

# --- Memory coefficients (documented, conservative) ------------------------------
# Weight footprint per billion params, by strategy (MB/B).
#   qlora: 4-bit nf4 weights. ~0.5 GB/B for the quantized blocks PLUS bf16
#          embeddings/lm_head, which are large for big-vocab models (e.g. Qwen3's
#          151k vocab, untied head ≈ +2.5 GB on an 8B) — so we use a conservative
#          0.80 GB/B rather than the naive 0.5.
#   lora : 16-bit base weights held in VRAM.
#   sft  : 16-bit base weights (grads/optimizer counted separately).
_WEIGHT_MB_PER_B = {"qlora": int(0.75 * _GB), "lora": int(2.0 * _GB), "sft": int(2.0 * _GB)}
# Gradient + optimizer state per billion params (MB/B).
#   Adapter methods (qlora/lora) ONLY optimize the small LoRA matrices, so grads +
#   8-bit-Adam moments are a small fraction of model size (a rank-16 adapter on an 8B
#   model is ~40M params ≈ 0.25 GB of states) — NOT the full-parameter figure used
#   before, which over-counted LoRA by ~2 GB. sft trains all weights (grads 2B +
#   adamw moments 4B ≈ 6 GB/B in fp16/fp32-mixed).
_STATE_MB_PER_B = {"qlora": int(0.03 * _GB), "lora": int(0.05 * _GB), "sft": int(6.0 * _GB)}
# Activation memory for a 512-token sequence at batch 1, WITH gradient checkpointing,
# for an ~8B model. Scaled linearly by (seq/512) × batch and by model size.
_ACT_MB_PER_512_PER_SAMPLE = int(0.80 * _GB)
# Fixed CUDA context + kernels + fragmentation reserve.
_OVERHEAD_MB = int(0.80 * _GB)
# Fraction of usable VRAM a run may occupy before we call it "tight".
_COMFORT_FRACTION = 0.90

# Minimum settings the engine will fall back to when trying to make a run fit.
_MIN_SEQ_LEN = 512
_MIN_BATCH = 1

# A ladder of common open-model parameter sizes, used to recommend a fitting model.
# Fine-grained around the 8 GB boundary (5B/6B) so the recommendation isn't coarse.
_MODEL_LADDER_B = [0.5, 1.5, 1.7, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 14.0, 32.0, 70.0]
# Friendly example repos per size bucket (illustrative; not a hard mapping).
_EXAMPLE_MODELS = {
    0.5: ["unsloth/Qwen2.5-0.5B-Instruct-bnb-4bit"],
    1.7: ["Qwen/Qwen3-1.7B", "unsloth/Qwen3-1.7B-unsloth-bnb-4bit"],
    3.0: ["Qwen/Qwen2.5-3B", "meta-llama/Llama-3.2-3B"],
    4.0: ["Qwen/Qwen3-4B", "unsloth/Qwen3-4B-unsloth-bnb-4bit"],
    7.0: ["Qwen/Qwen2.5-7B", "mistralai/Mistral-7B-v0.3"],
    8.0: ["meta-llama/Llama-3.1-8B", "Qwen/Qwen3-8B"],
}


class HardwareCompatibilityEngine:
    """Deterministic memory reasoning. One public entry point: :meth:`assess`."""

    def estimate(self, parameter_billions: float, strategy: str,
                 max_seq_length: int, batch_size: int) -> MemoryEstimate:
        """Estimate training VRAM (MB) for one configuration. Deterministic."""
        pb = max(0.1, float(parameter_billions))
        strat = strategy if strategy in _WEIGHT_MB_PER_B else "qlora"
        weights = int(pb * _WEIGHT_MB_PER_B[strat])
        optimizer = int(pb * _STATE_MB_PER_B[strat])
        size_scale = max(0.4, pb / 8.0)
        seq_scale = max(1.0, max_seq_length / 512.0)
        activations = int(_ACT_MB_PER_512_PER_SAMPLE * seq_scale * max(1, batch_size) * size_scale)
        total = weights + optimizer + activations + _OVERHEAD_MB
        return MemoryEstimate(weights_mb=weights, optimizer_mb=optimizer,
                              activations_mb=activations, overhead_mb=_OVERHEAD_MB,
                              total_mb=total)

    def assess(self, *, parameter_billions: Optional[float], strategy: str,
               max_seq_length: int, batch_size: int, gradient_accumulation: int,
               gpu: GpuProfile) -> Assessment:
        """Decide fit for the requested config; if it overflows, try safe defaults;
        if still over, recommend the largest model that fits. Never raises."""
        strat = strategy if strategy in _WEIGHT_MB_PER_B else "qlora"
        warnings: list[str] = []

        # No GPU → real training cannot run here at all.
        if not gpu.available:
            est = self.estimate(parameter_billions or 7.0, strat, max_seq_length, batch_size)
            return Assessment(
                verdict=Verdict.INSUFFICIENT, gpu=gpu, parameter_billions=parameter_billions,
                strategy=strat, estimate_requested=est, estimate_safe=est, usable_mb=None,
                headroom_mb=None, safe_defaults=SafeDefaults(),
                reason="No CUDA/Metal GPU detected — real training cannot run on this machine.",
                warnings=["Install a supported GPU, or use the Simulation backend."])

        usable = gpu.usable_mb() or 0
        if parameter_billions is None:
            warnings.append("Model size could not be determined from its name; assuming ~7B.")
        pb = parameter_billions or 7.0

        requested = self.estimate(pb, strat, max_seq_length, batch_size)
        comfort = int(usable * _COMFORT_FRACTION)

        # 1) Fits comfortably as requested.
        if requested.total_mb <= comfort:
            return Assessment(
                verdict=Verdict.FITS, gpu=gpu, parameter_billions=pb, strategy=strat,
                estimate_requested=requested, estimate_safe=requested, usable_mb=usable,
                headroom_mb=usable - requested.total_mb, safe_defaults=SafeDefaults(),
                reason=(f"~{requested.total_mb} MB needed vs ~{usable} MB usable on "
                        f"{gpu.name or 'GPU'} — fits."),
                warnings=warnings)

        # 2) Try minimum-footprint safe defaults.
        safe_seq = min(max_seq_length, _MIN_SEQ_LEN)
        safe_batch = _MIN_BATCH
        safe = self.estimate(pb, strat, safe_seq, safe_batch)
        safe_defaults = SafeDefaults(
            max_seq_length=safe_seq, batch_size=safe_batch,
            # keep the requested effective batch by raising accumulation
            gradient_accumulation=max(gradient_accumulation, batch_size * gradient_accumulation),
            gradient_checkpointing="unsloth")
        if safe.total_mb <= comfort:
            warnings.append(
                f"Requested settings (~{requested.total_mb} MB) exceed usable VRAM "
                f"(~{usable} MB); reduced to seq_len={safe_seq}, batch=1 (+gradient "
                f"checkpointing) → ~{safe.total_mb} MB.")
            return Assessment(
                verdict=Verdict.TIGHT, gpu=gpu, parameter_billions=pb, strategy=strat,
                estimate_requested=requested, estimate_safe=safe, usable_mb=usable,
                headroom_mb=usable - safe.total_mb, safe_defaults=safe_defaults,
                reason=(f"Fits only with reduced settings: ~{safe.total_mb} MB vs "
                        f"~{usable} MB usable."),
                warnings=warnings)

        # 3) Does not fit even at minimum → recommend a smaller model.
        rec_b, rec_models = self._recommend(strat, usable)
        reason = (f"{pb:g}B {strat.upper()} needs ~{safe.total_mb} MB even at minimum "
                  f"settings, but only ~{usable} MB is usable on "
                  f"{gpu.name or 'the GPU'} ({gpu.total_mb or '?'} MB total). "
                  "This model is too large for this GPU.")
        if rec_b:
            reason += f" The largest model that fits is ~{rec_b:g}B."
        return Assessment(
            verdict=Verdict.INSUFFICIENT, gpu=gpu, parameter_billions=pb, strategy=strat,
            estimate_requested=requested, estimate_safe=safe, usable_mb=usable,
            headroom_mb=usable - safe.total_mb, safe_defaults=safe_defaults, reason=reason,
            warnings=warnings, recommended_max_billions=rec_b, recommended_models=rec_models)

    def _recommend(self, strategy: str, usable_mb: int) -> tuple[Optional[float], list[str]]:
        """Largest ladder size whose minimum-setting estimate fits, + example repos."""
        comfort = int(usable_mb * _COMFORT_FRACTION)
        best: Optional[float] = None
        for pb in _MODEL_LADDER_B:
            est = self.estimate(pb, strategy, _MIN_SEQ_LEN, _MIN_BATCH)
            if est.total_mb <= comfort:
                best = pb
        if best is None:
            return None, []
        # nearest example bucket at or below the recommended size
        examples: list[str] = []
        for size in sorted(_EXAMPLE_MODELS, reverse=True):
            if size <= best:
                examples = _EXAMPLE_MODELS[size]
                break
        return best, examples


hardware_engine = HardwareCompatibilityEngine()
