"""Transformers training provider (RedForge V3, Epic 3) — fallback real provider.

Runs SFT/LoRA via Hugging Face ``transformers`` + ``peft`` + ``trl`` when a CUDA GPU
+ the stack are present. Like ``UnslothProvider`` it is lazily imported and honestly
degrades (a single ``failed`` event) when unavailable, so RedForge installs and runs
without it. Registered into the training manager from the V3 layer, so the existing
``providers/__init__`` (and its tests) are untouched.

This is a fallback for hardware/models Unsloth doesn't support. The concrete GPU
recipe is isolated and never exercised in CI (no GPU) — ``# pragma: no cover``.
"""
from __future__ import annotations

import importlib.util
from typing import AsyncIterator

from app.training.providers.base import ProgressEvent, TrainingConfig, TrainingProvider

_REQUIRED = ("torch", "transformers", "peft", "trl")

_HINT = ("Real training needs a CUDA GPU and: pip install transformers peft trl "
         "accelerate bitsandbytes. Until then, use the Simulation backend.")


class TransformersProvider(TrainingProvider):
    name = "transformers"
    label = "Hugging Face Transformers (local GPU)"

    def _missing(self) -> list[str]:
        return [m for m in _REQUIRED if importlib.util.find_spec(m) is None]

    def _has_cuda(self) -> bool:
        try:
            import torch  # type: ignore
            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            return False

    def is_available(self) -> tuple[bool, str]:
        missing = self._missing()
        if missing:
            return False, f"missing packages: {', '.join(missing)}. {_HINT}"
        if not self._has_cuda():
            return False, "no CUDA GPU detected. Transformers training needs a GPU."
        return True, "ready"

    async def run(self, config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:
        ok, reason = self.is_available()
        if not ok:
            yield ProgressEvent(status="failed", message=f"Transformers backend unavailable: {reason}")
            return
        try:  # pragma: no cover - requires GPU + ML stack
            from app.training.providers._transformers_impl import run_transformers
            async for event in run_transformers(config, cancel):
                yield event
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            import traceback
            yield ProgressEvent(status="failed", message=f"training error: {exc}\n{traceback.format_exc()[-600:]}")
