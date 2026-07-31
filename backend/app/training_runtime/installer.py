"""Install the managed training runtime.

Runs as a Job, so it appears in the Global Task Manager with progress, ETA, logs,
cancel and retry like every other long-running operation — no terminal.

Durability requirements from the brief, and how each is met:

  • **Survives application restart** — every phase records itself in
    ``install-state.json`` before starting. A restart re-reads it and resumes at
    the first incomplete phase instead of re-downloading gigabytes.
  • **Survives network interruption** — pip is invoked per package group with
    retries, and its HTTP cache is kept inside the runtime directory, so a retry
    reuses what already downloaded.
  • **Survives power failure** — the READY marker is written last, only after
    verification. A half-installed environment is therefore never reported ready;
    it is reported ``partial`` and is resumable.

The backend process never imports torch. pip runs as a subprocess of the managed
interpreter, which is what keeps the environments isolated.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.logging_config import get_logger

from . import paths
from .detector import build_plan, detect_gpu_info, inspect_runtime

logger = get_logger("training-runtime")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# Ordered phases. Each is recorded on completion so a resume can skip it.
PHASES = ["environment", "torch", "packages", "verify"]

# Weight of each phase in the overall progress bar (torch is the big download).
_PHASE_WEIGHT = {"environment": 0.05, "torch": 0.55, "packages": 0.30, "verify": 0.10}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class InstallState:
    """Crash-safe install bookkeeping (write-then-rename)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.state_file()

    def read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def write(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.warning("could not persist install state: %s", exc)

    def merge(self, **patch) -> dict:
        data = self.read()
        data.update(patch)
        self.write(data)
        return data

    def complete_phase(self, phase: str) -> None:
        data = self.read()
        done = set(data.get("completed_phases", []))
        done.add(phase)
        data["completed_phases"] = sorted(done)
        data["updated_at"] = _utcnow()
        self.write(data)

    def completed(self) -> set[str]:
        return set(self.read().get("completed_phases", []))

    def reset(self) -> None:
        self.write({"started_at": _utcnow(), "completed_phases": []})


def _stream_subprocess(cmd: list[str], cwd: Path | None, env: dict,
                       on_line, should_cancel) -> int:
    """Run a command, pushing stdout lines to ``on_line``. Blocking — call via a thread.

    Cancellation kills the whole process tree; pip spawns children and orphaning
    them would leave a multi-gigabyte download running invisibly.
    """
    proc = subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, creationflags=_NO_WINDOW,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            on_line(line.rstrip())
            if should_cancel():
                _kill_tree(proc)
                return 130
        return proc.wait()
    finally:
        if proc.poll() is None:
            _kill_tree(proc)


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=_NO_WINDOW)
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception as exc:  # noqa: BLE001 - cleanup must never raise
        logger.warning("failed to kill install subprocess: %s", exc)


def _pip_env(root: Path) -> dict:
    """Keep pip's cache inside the runtime dir so a retry reuses partial downloads
    and uninstalling the runtime reclaims every byte."""
    env = dict(os.environ)
    env["PIP_CACHE_DIR"] = str(root / "pip-cache")
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # Never let a user's global config redirect our installs.
    env.pop("PIP_TARGET", None)
    env.pop("PYTHONPATH", None)
    return env


def _host_python() -> str | None:
    """An interpreter capable of creating a venv.

    The frozen backend cannot create one (it is not a real interpreter), so we look
    for a system Python. This is the one genuine external prerequisite, and the UI
    states it plainly rather than failing halfway through.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    return None


class RuntimeInstaller:
    """Orchestrates the phased, resumable install."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or paths.runtime_root()
        self.state = InstallState(paths.state_file())

    # -- phases -------------------------------------------------------------

    def _create_environment(self, emit, should_cancel) -> None:
        host = _host_python()
        if host is None:
            raise RuntimeError(
                "No system Python found. Installing the training runtime requires "
                "Python 3.10+ on your PATH — install it from python.org, then retry."
            )
        emit(f"creating isolated environment with {host}")
        self.root.mkdir(parents=True, exist_ok=True)
        code = _stream_subprocess(
            [host, "-m", "venv", str(paths.venv_dir())],
            cwd=self.root, env=_pip_env(self.root), on_line=emit, should_cancel=should_cancel,
        )
        if code == 130:
            raise asyncio.CancelledError()
        if code != 0:
            raise RuntimeError(f"could not create the virtual environment (exit {code})")
        python_exe = paths.python_executable(self.root)
        if not python_exe.exists():
            raise RuntimeError(f"virtual environment created but {python_exe} is missing")
        # A current pip is required for correct wheel resolution.
        _stream_subprocess(
            [str(python_exe), "-m", "pip", "install", "--upgrade", "pip", "wheel"],
            cwd=self.root, env=_pip_env(self.root), on_line=emit, should_cancel=should_cancel,
        )

    def _pip_install(self, args: list[str], emit, should_cancel, attempts: int = 3) -> None:
        python_exe = paths.python_executable(self.root)
        cmd = [str(python_exe), "-m", "pip", "install", *args]
        last = 0
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                emit(f"retrying (attempt {attempt}/{attempts}) — previous attempt exited {last}")
                time.sleep(min(10, 2 ** attempt))
            last = _stream_subprocess(cmd, cwd=self.root, env=_pip_env(self.root),
                                      on_line=emit, should_cancel=should_cancel)
            if last == 0:
                return
            if last == 130:
                raise asyncio.CancelledError()
        raise RuntimeError(f"pip install failed after {attempts} attempts (exit {last}): {' '.join(args)}")

    def _install_torch(self, plan, emit, should_cancel) -> None:
        emit(f"installing PyTorch ({plan.variant}) from {plan.torch_index_url}")
        self._pip_install(["torch", "--index-url", plan.torch_index_url], emit, should_cancel)

    def _install_packages(self, plan, emit, should_cancel) -> None:
        rest = [p for p in plan.packages if p != "torch"]
        emit(f"installing {len(rest)} training packages")
        # Unsloth pins its own torch; --no-deps on torch is handled by installing
        # it first from the CUDA index, so plain resolution is correct here.
        self._pip_install(rest, emit, should_cancel)

    def _verify(self, emit) -> None:
        emit("verifying installation — importing every dependency")
        report = inspect_runtime(self.root)
        if not report.ready:
            raise RuntimeError(f"verification failed: {report.message}")
        emit(report.message)

    # -- driver -------------------------------------------------------------

    def run(self, emit, progress, should_cancel, force: bool = False) -> dict:
        """Blocking install. Call from a worker thread (see ``install_job``)."""
        gpu = detect_gpu_info()
        plan = build_plan(gpu)

        if force:
            self.state.reset()
        data = self.state.read()
        if not data.get("started_at"):
            self.state.merge(started_at=_utcnow(), completed_phases=[], variant=plan.variant)
        done = self.state.completed()
        if done:
            emit(f"resuming installation — already completed: {', '.join(sorted(done))}")

        emit(f"plan: {plan.variant} · {plan.reason}")
        for warning in plan.warnings:
            emit(f"warning: {warning}")

        completed_weight = sum(_PHASE_WEIGHT[p] for p in done if p in _PHASE_WEIGHT)

        steps = [
            ("environment", "Creating isolated environment",
             lambda: self._create_environment(emit, should_cancel)),
            ("torch", f"Installing PyTorch ({plan.variant})",
             lambda: self._install_torch(plan, emit, should_cancel)),
            ("packages", "Installing training packages",
             lambda: self._install_packages(plan, emit, should_cancel)),
            ("verify", "Verifying installation", lambda: self._verify(emit)),
        ]

        for phase, label, action in steps:
            if phase in done:
                continue
            if should_cancel():
                raise asyncio.CancelledError()
            progress(completed_weight, label)
            action()
            self.state.complete_phase(phase)
            completed_weight += _PHASE_WEIGHT[phase]
            progress(completed_weight, f"{label} — done")

        self.state.merge(completed_at=_utcnow(), variant=plan.variant)
        marker = {
            "installed_at": _utcnow(),
            "variant": plan.variant,
            "gpu": gpu.to_dict(),
        }
        try:
            paths.marker_file().write_text(json.dumps(marker, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("could not write READY marker: %s", exc)
        progress(1.0, "Training runtime ready")
        return marker


def uninstall(root: Path | None = None) -> bool:
    """Delete the managed runtime. User data lives elsewhere and is untouched."""
    target = root or paths.runtime_root()
    if not target.exists():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()


# --- Job handler ------------------------------------------------------------

def register_training_runtime_handlers() -> None:
    from app.jobs.handlers import handler_registry
    handler_registry.register("training_runtime_install", _handle_install)


async def _handle_install(job, ctx):
    """The ``training_runtime_install`` Job handler.

    pip is blocking and long-running, so it runs on a worker thread and
    communicates through a queue; the async side drains it and reports progress.
    Doing the install inline would freeze the entire single-process backend.
    """
    from app.jobs.domain import JobResult

    params = job.params or {}
    force = bool(params.get("force"))
    installer = RuntimeInstaller()

    events: "queue.Queue[tuple[str, object]]" = queue.Queue()
    holder: dict = {}

    def emit(line: str) -> None:
        if line:
            events.put(("log", line))

    def progress(fraction: float, message: str) -> None:
        events.put(("progress", (max(0.0, min(1.0, fraction)), message)))

    def should_cancel() -> bool:
        return ctx.is_cancelled()

    def worker() -> None:
        try:
            holder["result"] = installer.run(emit, progress, should_cancel, force=force)
        except asyncio.CancelledError:
            holder["cancelled"] = True
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the user
            holder["error"] = str(exc)
        finally:
            events.put(("done", None))

    thread = threading.Thread(target=worker, name="training-runtime-install", daemon=True)
    thread.start()

    await ctx.report_progress(0.0, "Preparing training runtime installation…")
    finished = False
    while not finished:
        drained = 0
        while drained < 200:
            try:
                kind, payload = events.get_nowait()
            except queue.Empty:
                break
            drained += 1
            if kind == "log":
                await ctx.log(str(payload))
            elif kind == "progress":
                fraction, message = payload  # type: ignore[misc]
                await ctx.report_progress(fraction, message)
            elif kind == "done":
                finished = True
                break
        if not finished:
            await asyncio.sleep(0.1)

    thread.join(timeout=10)

    if holder.get("cancelled"):
        return JobResult(success=False, message="Installation cancelled. Progress was saved — "
                                                "starting again will resume where it stopped.")
    if holder.get("error"):
        return JobResult(
            success=False,
            message=f"Training runtime installation failed: {holder['error']}",
            data={"resumable": True},
        )

    report = await asyncio.to_thread(inspect_runtime)
    return JobResult(
        success=True,
        message="Training runtime installed — real LoRA/QLoRA is now available.",
        data={"runtime": report.to_dict()},
    )
