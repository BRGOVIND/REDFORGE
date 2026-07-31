"""Detect the managed training runtime and plan what installing it would do.

Two independent questions, deliberately kept separate:

  1. **What hardware is this?**  → ``detect_gpu_info()`` (nvidia-smi, no torch needed)
  2. **What is installed in the managed venv?** → ``inspect_runtime()``

(2) runs *inside* the managed interpreter as a subprocess, because the backend
process has no torch and must never import one. A single probe script reports
every package's version as JSON, so one subprocess answers the whole matrix.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import paths
from .domain import GpuInfo, InstallPlan, PackageCheck, RuntimeReport

# Importing torch (and CUDA init) is genuinely slow on first run and on cold
# filesystems. Presence checks avoid importing entirely (see _PROBE_SRC); only the
# CUDA probe imports torch, so this budget covers that one import.
PROBE_TIMEOUT_S = 180.0
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# (import name, label, required for real training)
RUNTIME_PACKAGES: list[tuple[str, str, bool]] = [
    ("torch", "PyTorch", True),
    ("transformers", "Transformers", True),
    ("peft", "PEFT", True),
    ("unsloth", "Unsloth", True),
    ("trl", "TRL", True),
    ("accelerate", "Accelerate", True),
    ("datasets", "datasets", True),
    ("safetensors", "safetensors", True),
    ("huggingface_hub", "huggingface_hub", True),
    # 4-bit QLoRA only; plain LoRA works without it.
    ("bitsandbytes", "bitsandbytes", False),
]

# Executed by the MANAGED interpreter, not this one.
#
# Presence is checked with find_spec + importlib.metadata — deliberately WITHOUT
# importing. Importing `unsloth` alone takes over a minute (it patches
# transformers at import time), which made a naive probe time out and report a
# perfectly good runtime as broken. Only torch is imported, and only to answer
# "can it see the GPU?", which nothing else can tell us.
_PROBE_SRC = r"""
import importlib.metadata as md, importlib.util, json, platform, sys
names = %(names)s
out = {"python": platform.python_version(), "executable": sys.executable, "packages": {}}
for name in names:
    entry = {"installed": False, "version": None, "detail": ""}
    try:
        spec = importlib.util.find_spec(name)
        entry["installed"] = spec is not None
        if spec is None:
            entry["detail"] = "not installed"
    except Exception as exc:
        entry["detail"] = f"{type(exc).__name__}: {exc}"[:200]
    if entry["installed"]:
        for dist in (name, name.replace("_", "-")):
            try:
                entry["version"] = md.version(dist)
                break
            except Exception:
                continue
    out["packages"][name] = entry
try:
    import torch
    out["cuda_available"] = bool(torch.cuda.is_available())
    out["torch_cuda"] = getattr(torch.version, "cuda", None)
    if out["cuda_available"]:
        out["gpu_name"] = torch.cuda.get_device_name(0)
        out["vram_mb"] = int(torch.cuda.get_device_properties(0).total_memory / (1024*1024))
except Exception as exc:
    out["cuda_available"] = False
    out["torch_error"] = f"{type(exc).__name__}: {exc}"[:200]
print("__REDFORGE_PROBE__" + json.dumps(out))
"""


def _run(cmd: list[str], timeout: float = PROBE_TIMEOUT_S) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, creationflags=_NO_WINDOW)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)


# --- hardware ---------------------------------------------------------------

def detect_gpu_info() -> GpuInfo:
    """GPU facts from nvidia-smi — deliberately torch-free, so this works before
    anything is installed and drives the install plan."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return GpuInfo(available=False)
    code, out, _ = _run(
        [smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
        timeout=15.0,
    )
    if code != 0 or not out.strip():
        return GpuInfo(available=False)
    first = out.strip().splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    name = parts[0] if parts else None
    vram = None
    if len(parts) > 1:
        try:
            vram = int(float(parts[1]))
        except ValueError:
            vram = None
    driver = parts[2] if len(parts) > 2 else None

    # `nvidia-smi` (no args) reports the maximum CUDA version the driver supports.
    cuda = None
    code, out, _ = _run([smi], timeout=15.0)
    if code == 0:
        match = re.search(r"CUDA Version:\s*([0-9]+\.[0-9]+)", out)
        if match:
            cuda = match.group(1)
    return GpuInfo(available=True, name=name, vram_mb=vram,
                   cuda_version=cuda, driver_version=driver)


def _disk_free_mb(path: Path) -> int | None:
    try:
        probe = path
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        return int(shutil.disk_usage(probe).free / (1024 * 1024))
    except OSError:
        return None


# --- install plan -----------------------------------------------------------

# PyTorch publishes per-CUDA wheel indexes. Pick the newest the driver supports;
# a driver reporting CUDA 12.4 cannot run cu126 wheels.
_CUDA_WHEELS = [
    (12.6, "cu126", "https://download.pytorch.org/whl/cu126"),
    (12.4, "cu124", "https://download.pytorch.org/whl/cu124"),
    (12.1, "cu121", "https://download.pytorch.org/whl/cu121"),
    (11.8, "cu118", "https://download.pytorch.org/whl/cu118"),
]
_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def build_plan(gpu: GpuInfo | None = None) -> InstallPlan:
    """Choose the wheel variant this machine can actually run."""
    gpu = gpu or detect_gpu_info()
    warnings: list[str] = []

    base = ["transformers", "peft", "trl", "accelerate", "datasets",
            "safetensors", "huggingface_hub", "unsloth"]

    if not gpu.available:
        return InstallPlan(
            variant="cpu",
            torch_index_url=_CPU_INDEX,
            packages=["torch", *base],
            download_mb_estimate=900,
            minutes_estimate="3–8 minutes",
            reason="No NVIDIA GPU detected — installing the CPU build.",
            warnings=["Without a CUDA GPU, real fine-tuning is impractically slow. "
                      "Simulation mode is usually the better choice on this machine."],
        )

    driver_cuda = 0.0
    try:
        driver_cuda = float(gpu.cuda_version or 0)
    except ValueError:
        driver_cuda = 0.0

    variant, index = "cu121", _CUDA_WHEELS[-2][2]
    reason = ""
    for min_cuda, name, url in _CUDA_WHEELS:
        if driver_cuda >= min_cuda:
            variant, index = name, url
            reason = f"Driver supports CUDA {gpu.cuda_version}; using {name} wheels."
            break
    else:
        if driver_cuda:
            variant, index = "cu118", _CUDA_WHEELS[-1][2]
            reason = f"Driver reports CUDA {gpu.cuda_version}; falling back to cu118 wheels."
            warnings.append("Your NVIDIA driver is old. Updating it enables faster CUDA builds.")
        else:
            reason = "CUDA version could not be read from the driver; using cu121 wheels."
            warnings.append("Could not determine the driver's CUDA version — if training "
                            "fails to start, update your NVIDIA driver.")

    if gpu.vram_mb and gpu.vram_mb < 6000:
        warnings.append(f"{gpu.vram_mb} MB of VRAM is tight. Expect small models "
                        "(≤3B) with QLoRA only.")

    return InstallPlan(
        variant=variant,
        torch_index_url=index,
        packages=["torch", *base, "bitsandbytes"],
        download_mb_estimate=2800,
        minutes_estimate="5–15 minutes",
        reason=reason,
        warnings=warnings,
    )


# --- managed runtime inspection --------------------------------------------

def _probe_managed(python_exe: Path) -> dict | None:
    """Ask the managed interpreter what it has. Returns None if it cannot run."""
    names = json.dumps([n for n, _, _ in RUNTIME_PACKAGES])
    code, out, err = _run([str(python_exe), "-c", _PROBE_SRC % {"names": names}])
    if code != 0 and "__REDFORGE_PROBE__" not in out:
        return {"_error": (err or out or "probe failed").strip()[:400]}
    for line in out.splitlines():
        if line.startswith("__REDFORGE_PROBE__"):
            try:
                return json.loads(line[len("__REDFORGE_PROBE__"):])
            except json.JSONDecodeError:
                return {"_error": "probe returned malformed JSON"}
    return {"_error": (err or "probe produced no output").strip()[:400]}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def inspect_runtime(root: Path | None = None) -> RuntimeReport:
    """The full picture: status, packages, hardware and what an install would do."""
    root = root or paths.runtime_root()
    python_exe = paths.python_executable(root)
    gpu = detect_gpu_info()
    plan = build_plan(gpu)
    disk = _disk_free_mb(root)
    state = _read_json(paths.state_file())
    marker = _read_json(paths.marker_file())

    def absent(message: str, status: str = "absent", resumable: bool = False) -> RuntimeReport:
        return RuntimeReport(
            status=status, root=str(root), python_executable=None, python_version=None,
            gpu=gpu, plan=plan, disk_free_mb=disk, message=message, resumable=resumable,
            packages=[PackageCheck(n, label, req) for n, label, req in RUNTIME_PACKAGES],
        )

    if not python_exe.exists():
        if state.get("started_at") and not state.get("completed_at"):
            return absent(
                "A previous installation was interrupted before the environment was created.",
                status="partial", resumable=True,
            )
        return absent("The training runtime is not installed.")

    probe = _probe_managed(python_exe)
    if probe is None or "_error" in (probe or {}):
        detail = (probe or {}).get("_error", "unknown error")
        return RuntimeReport(
            status="broken", root=str(root), python_executable=str(python_exe),
            python_version=None, gpu=gpu, plan=plan, disk_free_mb=disk,
            message=f"The managed environment exists but could not be started: {detail}",
            resumable=True,
            packages=[PackageCheck(n, label, req) for n, label, req in RUNTIME_PACKAGES],
        )

    reported = probe.get("packages", {})
    checks: list[PackageCheck] = []
    for name, label, required in RUNTIME_PACKAGES:
        info = reported.get(name, {})
        checks.append(PackageCheck(
            name=name, label=label, required=required,
            installed=bool(info.get("installed")),
            version=info.get("version"),
            detail=info.get("detail", ""),
        ))

    missing = [c for c in checks if c.required and not c.installed]
    if missing:
        status = "partial" if state.get("started_at") and not state.get("completed_at") else "broken"
        return RuntimeReport(
            status=status, root=str(root), python_executable=str(python_exe),
            python_version=probe.get("python"), gpu=gpu, packages=checks, plan=plan,
            disk_free_mb=disk, resumable=True,
            message=f"Incomplete installation — missing {', '.join(c.label for c in missing)}.",
        )

    # Everything imports. CUDA is only *required* when a GPU is present.
    if gpu.available and not probe.get("cuda_available"):
        return RuntimeReport(
            status="broken", root=str(root), python_executable=str(python_exe),
            python_version=probe.get("python"), gpu=gpu, packages=checks, plan=plan,
            disk_free_mb=disk, resumable=True,
            message=("PyTorch is installed but cannot see your GPU "
                     f"({probe.get('torch_error') or 'torch.cuda.is_available() is False'}). "
                     "Reinstalling the runtime usually fixes a CUDA/driver mismatch."),
        )

    return RuntimeReport(
        status="ready", root=str(root), python_executable=str(python_exe),
        python_version=probe.get("python"), gpu=gpu, packages=checks, plan=plan,
        disk_free_mb=disk, installed_at=marker.get("installed_at"),
        message="Training runtime ready — real LoRA and QLoRA are available.",
    )
