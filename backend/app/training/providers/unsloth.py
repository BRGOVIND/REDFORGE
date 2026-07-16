"""Unsloth training provider — real local LoRA / QLoRA.

Runs actual fine-tuning via Unsloth + PEFT + Transformers + bitsandbytes on a
local GPU. The heavy stack is **lazily imported** so RedForge installs and runs
without it; when it (or a CUDA GPU) is missing, :meth:`is_available` reports why
and :meth:`run` yields a single clear ``failed`` event instead of crashing.

This is the production training path. It is intentionally the *only* place that
knows about Unsloth — the rest of RedForge talks to the provider interface.
"""
from __future__ import annotations

from typing import AsyncIterator

from app.training.providers.base import ProgressEvent, TrainingConfig, TrainingProvider

# Minimum stack required for real training.
_REQUIRED = ("torch", "transformers", "peft", "unsloth")

_INSTALL_HINT = (
    "Real training needs a CUDA GPU and the training stack: "
    "pip install 'unsloth[cu121]' peft transformers bitsandbytes trl. "
    "Until then, use the Simulation backend."
)


class UnslothProvider(TrainingProvider):
    name = "unsloth"
    label = "Unsloth (local GPU · LoRA/QLoRA)"

    def _missing(self) -> list[str]:
        import importlib.util
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
            return False, f"missing packages: {', '.join(missing)}. {_INSTALL_HINT}"
        if not self._has_cuda():
            return False, "no CUDA GPU detected. LoRA/QLoRA training needs a GPU."
        return True, "ready"

    async def run(self, config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:
        ok, reason = self.is_available()
        if not ok:
            # Degrade cleanly — the manager/UX handle a failed event gracefully.
            yield ProgressEvent(status="failed", message=f"Unsloth backend unavailable: {reason}")
            return

        # --- Real training path (only reached when the stack + GPU exist) ---
        # Implemented against the provider interface; executes the standard
        # Unsloth LoRA/QLoRA recipe and translates its callbacks into
        # ProgressEvents. Not exercised in CI (no GPU), hence pragma.
        try:  # pragma: no cover - requires GPU + ML stack
            from app.training.providers._unsloth_impl import run_unsloth
            async for event in run_unsloth(config, cancel):
                yield event
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            yield ProgressEvent(status="failed", message=f"training error: {exc}")
