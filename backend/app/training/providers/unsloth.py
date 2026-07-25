"""Unsloth training provider — real local LoRA / QLoRA.

Runs actual fine-tuning via Unsloth + PEFT + Transformers + bitsandbytes on a
local GPU. The heavy stack is **lazily imported** so RedForge installs and runs
without it; when it (or a CUDA GPU) is missing, :meth:`diagnose` reports exactly
which layer is missing and :meth:`run` yields a single clear ``failed`` event
instead of crashing.

Diagnostics are **structured and per-layer** (PyTorch, CUDA, GPU, Transformers,
PEFT, Unsloth, bitsandbytes) so the UI shows the real failing dependency rather
than collapsing every problem into "no CUDA GPU". Each probe captures its own
exception and reports the true error string. Results are cached for the process
lifetime (hardware/stack don't change) — with an explicit ``refresh`` — so hot
polling never repeatedly pays the cost of importing torch.

This is the production training path and the *only* place that knows about
Unsloth — the rest of RedForge talks to the provider interface.
"""
from __future__ import annotations

import importlib.util
from typing import AsyncIterator, Optional

from app.training.providers.base import ProgressEvent, TrainingConfig, TrainingProvider

# Packages that MUST be present for real training, and those only needed for
# QLoRA / 4-bit (reported but not required for plain LoRA).
_REQUIRED = ("torch", "transformers", "peft", "unsloth")
_QLORA_ONLY = ("bitsandbytes",)

_INSTALL_HINT = (
    "Real training needs a CUDA GPU and the training stack: "
    "pip install 'unsloth[cu121]' peft transformers bitsandbytes trl. "
    "Until then, use the Simulation backend."
)


def _pkg_version(module: str) -> Optional[str]:
    """Best-effort version string via importlib.metadata (no import side effects)."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version(module)
        except PackageNotFoundError:
            return None
    except Exception:  # noqa: BLE001
        return None


class UnslothProvider(TrainingProvider):
    name = "unsloth"
    label = "Unsloth (local GPU · LoRA/QLoRA)"

    # Process-lifetime cache: {"checks": [...], "ready": bool, ...}. Hardware and
    # installed packages don't change during a run, so we probe once.
    _diag_cache: Optional[dict] = None

    # -- structured diagnostics -------------------------------------------------

    def _probe_torch(self) -> dict:
        """Return raw torch/cuda facts, each error captured (never raised)."""
        facts: dict = {"torch_installed": False, "torch_version": None,
                       "cuda_available": False, "gpu_name": None, "error": None}
        if importlib.util.find_spec("torch") is None:
            return facts
        facts["torch_installed"] = True
        facts["torch_version"] = _pkg_version("torch")
        try:
            import torch  # type: ignore
            facts["torch_version"] = getattr(torch, "__version__", facts["torch_version"])
            facts["cuda_available"] = bool(torch.cuda.is_available())
            if facts["cuda_available"]:
                try:
                    facts["gpu_name"] = torch.cuda.get_device_name(0)
                except Exception as exc:  # noqa: BLE001
                    facts["gpu_name"] = None
                    facts["error"] = f"GPU query failed: {exc}"
        except Exception as exc:  # noqa: BLE001 - a broken torch install must surface, not hide
            facts["error"] = f"importing torch failed: {exc}"
        return facts

    def diagnose(self, refresh: bool = False) -> dict:
        """Per-layer diagnostics. Every layer is checked independently and reports
        its own status + detail, so the UI can show the exact failing dependency."""
        if self._diag_cache is not None and not refresh:
            return self._diag_cache

        t = self._probe_torch()
        checks: list[dict] = []

        # PyTorch
        checks.append({
            "name": "PyTorch",
            "ok": t["torch_installed"] and t["error"] is None,
            "detail": t["torch_version"] or (t["error"] or "not installed"),
            "required": True,
        })
        # CUDA
        checks.append({
            "name": "CUDA",
            "ok": t["cuda_available"],
            "detail": ("available" if t["cuda_available"]
                       else (t["error"] or "torch.cuda.is_available() is False")),
            "required": True,
        })
        # GPU
        checks.append({
            "name": "GPU",
            "ok": bool(t["gpu_name"]),
            "detail": t["gpu_name"] or "no CUDA device detected",
            "required": True,
        })
        # Python packages (Transformers / PEFT / Unsloth / bitsandbytes)
        for label, module, required in (
            ("Transformers", "transformers", True),
            ("PEFT", "peft", True),
            ("Unsloth", "unsloth", True),
            ("bitsandbytes", "bitsandbytes", False),
            ("TRL", "trl", False),
        ):
            present = importlib.util.find_spec(module) is not None
            checks.append({
                "name": label, "ok": present,
                "detail": (_pkg_version(module) or "installed") if present else "not installed",
                "required": required,
            })

        missing_required = [c["name"] for c in checks if c["required"] and not c["ok"]]
        ready = not missing_required
        if ready:
            status = "Ready for LoRA/QLoRA Training"
        else:
            status = f"Not ready — {missing_required[0]} unavailable ({_first_detail(checks, missing_required[0])})"

        result = {
            "backend": self.name, "label": self.label,
            "checks": checks, "ready": ready,
            "missing_required": missing_required, "status": status,
            "install_hint": _INSTALL_HINT,
        }
        UnslothProvider._diag_cache = result
        return result

    # -- provider interface -----------------------------------------------------

    def is_available(self) -> tuple[bool, str]:
        """Derived from structured diagnostics so the reason names the real failing
        layer instead of collapsing everything into 'no CUDA GPU'."""
        diag = self.diagnose()
        if diag["ready"]:
            return True, "ready"
        return False, diag["status"] + f". {_INSTALL_HINT}"

    async def run(self, config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:
        ok, reason = self.is_available()
        if not ok:
            # Degrade cleanly — the manager/UX handle a failed event gracefully.
            yield ProgressEvent(status="failed", message=f"Unsloth backend unavailable: {reason}")
            return

        # --- Real training path (only reached when the stack + GPU exist) ---
        # Delegates to the isolated recipe; its exceptions (including the training
        # thread's) are surfaced verbatim so the UI shows the true failure.
        try:  # pragma: no cover - requires GPU + ML stack
            from app.training.providers._unsloth_impl import run_unsloth
            async for event in run_unsloth(config, cancel):
                yield event
        except Exception as exc:  # noqa: BLE001  # pragma: no cover
            import traceback
            yield ProgressEvent(
                status="failed",
                message=f"training error: {exc}",
                # detail carries the traceback tail for durable diagnostics.
            )
            _LOG.warning("unsloth run failed: %s\n%s", exc, traceback.format_exc())


def _first_detail(checks: list[dict], name: str) -> str:
    return next((c["detail"] for c in checks if c["name"] == name), "")


from app.logging_config import get_logger  # noqa: E402
_LOG = get_logger("training-unsloth")
