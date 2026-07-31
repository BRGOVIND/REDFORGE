"""Managed-runtime training provider — real LoRA/QLoRA via the installed runtime.

The packaged backend deliberately ships without PyTorch, so it can never import
the training stack. This provider therefore runs training as a **subprocess of the
managed runtime's interpreter** and streams its line protocol back as
ProgressEvents.

That subprocess boundary is the whole point:

  • the frozen backend stays small and torch-free,
  • a broken/incompatible training install cannot crash the backend,
  • cancellation kills a process tree instead of trying to interrupt a thread
    stuck inside a CUDA kernel.

``unsloth`` (in-process) remains the provider for source installs that already
have the stack; this one covers the packaged app. Both produce identical events.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import AsyncIterator

from app.logging_config import get_logger
from app.training.providers.base import ProgressEvent, TrainingConfig, TrainingProvider

logger = get_logger("training-managed")

PREFIX = "@@RF@@"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _worker_path() -> Path:
    """The worker script on disk.

    It must exist as a real file — the managed interpreter executes it directly
    and cannot read it out of a PyInstaller archive. ``stage-backend.py`` ships it
    with ``--add-data`` for exactly this reason.
    """
    return Path(__file__).resolve().parents[2] / "training_runtime" / "worker.py"


class ManagedRuntimeProvider(TrainingProvider):
    name = "managed"
    label = "Managed Runtime (local GPU · LoRA/QLoRA)"

    def _report(self, refresh: bool = False):
        from app.training_runtime import runtime_service
        return runtime_service.report_sync(refresh=refresh)

    def diagnose(self, refresh: bool = False) -> dict:
        report = self._report(refresh=refresh)
        checks = [
            {"name": "Managed runtime", "ok": report.ready,
             "detail": report.message, "required": True},
            {"name": "GPU", "ok": report.gpu.available,
             "detail": report.gpu.name or "no CUDA device detected", "required": True},
        ]
        for pkg in report.packages:
            checks.append({
                "name": pkg.label, "ok": pkg.installed,
                "detail": pkg.version or pkg.detail or ("installed" if pkg.installed else "not installed"),
                "required": pkg.required,
            })
        worker_ok = _worker_path().is_file()
        checks.append({"name": "Worker script", "ok": worker_ok,
                       "detail": str(_worker_path()) if worker_ok else "missing from this build",
                       "required": True})
        missing = [c["name"] for c in checks if c["required"] and not c["ok"]]
        return {
            "backend": self.name, "label": self.label, "checks": checks,
            "ready": not missing, "missing_required": missing,
            "status": ("Ready for LoRA/QLoRA Training" if not missing
                       else f"Not ready — {missing[0]} unavailable"),
            "install_hint": "Install the training runtime from Training → Runtime, "
                            "or Settings → Training.",
            "runtime": report.to_dict(),
        }

    def is_available(self) -> tuple[bool, str]:
        diag = self.diagnose()
        if diag["ready"]:
            return True, "ready"
        return False, diag["status"]

    async def run(self, config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:
        ok, reason = self.is_available()
        if not ok:
            yield ProgressEvent(status="failed", message=f"Managed runtime unavailable: {reason}")
            return

        report = self._report()
        python_exe = report.python_executable
        worker = _worker_path()
        if not python_exe or not worker.is_file():
            yield ProgressEvent(status="failed",
                                message="Managed runtime is incomplete (interpreter or worker missing).")
            return

        payload = {
            "base_model": config.base_model,
            "method": config.method,
            "epochs": config.epochs,
            "learning_rate": config.learning_rate,
            "batch_size": config.batch_size,
            "gradient_accumulation": config.gradient_accumulation,
            "rank": config.rank,
            "alpha": config.alpha,
            "dropout": config.dropout,
            "scheduler": config.scheduler,
            "optimizer": config.optimizer,
            "warmup_steps": config.warmup_steps,
            "max_seq_length": config.max_seq_length,
            "seed": config.seed,
            "output_dir": config.output_dir,
            "dataset_records": config.dataset_records,
            "cache_dir": str(Path(report.root) / "cache"),
        }

        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(payload, tmp)
            tmp.close()

            yield ProgressEvent(status="running", message="starting managed training runtime…")
            async for event in self._stream(python_exe, worker, tmp.name, cancel):
                yield event
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    async def _stream(self, python_exe: str, worker: Path, config_path: str,
                      cancel) -> AsyncIterator[ProgressEvent]:
        proc = await asyncio.create_subprocess_exec(
            python_exe, str(worker), config_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(worker.parent),
            creationflags=_NO_WINDOW,
        )
        saw_terminal = False
        try:
            assert proc.stdout is not None
            while True:
                if cancel and cancel():
                    await self._kill(proc)
                    yield ProgressEvent(status="cancelled", message="training cancelled")
                    return
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line.startswith(PREFIX):
                    # Library chatter — useful in logs, not a protocol event.
                    if line.strip():
                        logger.debug("worker: %s", line[:300])
                    continue
                try:
                    data = json.loads(line[len(PREFIX):])
                except json.JSONDecodeError:
                    continue
                status = data.get("status", "running")
                if status in ("completed", "failed"):
                    saw_terminal = True
                yield self._to_event(status, data)

            code = await proc.wait()
            if not saw_terminal:
                # The worker died without reporting — never report success.
                yield ProgressEvent(
                    status="failed",
                    message=f"training runtime exited unexpectedly (code {code})",
                )
        finally:
            if proc.returncode is None:
                await self._kill(proc)

    @staticmethod
    def _to_event(status: str, data: dict) -> ProgressEvent:
        """Map the worker's line protocol onto the provider-agnostic event.

        ``starting`` and ``checkpoint`` are not terminal statuses in the
        ProgressEvent vocabulary, so both surface as ``running`` — a checkpoint
        additionally carries its payload in the ``checkpoint`` field.
        """
        checkpoint = None
        if status == "checkpoint":
            checkpoint = {
                "step": data.get("step", 0),
                "epoch": data.get("epoch", 0.0),
                "loss": data.get("loss"),
                "val_loss": data.get("val_loss"),
                "path": data.get("path", ""),
                "is_best": data.get("is_best", 0),
            }
        return ProgressEvent(
            status="running" if status in ("starting", "checkpoint") else status,
            step=int(data.get("step") or 0),
            total_steps=int(data.get("total") or 0),
            epoch=float(data.get("epoch") or 0.0),
            loss=data.get("loss"),
            val_loss=data.get("val_loss"),
            learning_rate=data.get("learning_rate"),
            message=data.get("message", ""),
            checkpoint=checkpoint,
        )

    @staticmethod
    async def _kill(proc) -> None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, creationflags=_NO_WINDOW)
            else:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
        except Exception as exc:  # noqa: BLE001 - cleanup must never raise
            logger.warning("failed to kill training subprocess: %s", exc)
