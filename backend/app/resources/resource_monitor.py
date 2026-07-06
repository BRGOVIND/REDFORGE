"""Cross-platform resource detection and plan safety assessment.

Detects available RAM, CPU, GPU, and disk on Windows, Linux, and macOS without
requiring any third-party package. If ``psutil`` happens to be installed it is
used for richer/faster memory data, otherwise platform-native fallbacks kick in
(``/proc/meminfo``, ``GlobalMemoryStatusEx``, ``sysctl``/``vm_stat``).

Everything here is best-effort and never raises: unknown values come back as
``None`` and the assessment simply skips the corresponding warning. GPU probing
(the one potentially slow call) is cached for the process lifetime.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from app.config import settings

_MB = 1024 * 1024


@dataclass
class GpuInfo:
    available: bool
    name: Optional[str] = None
    total_mb: Optional[int] = None
    free_mb: Optional[int] = None
    backend: Optional[str] = None  # "cuda" / "metal"


@dataclass
class ResourceSnapshot:
    platform: str
    source: str  # "psutil" or "stdlib"
    ram_total_mb: Optional[int]
    ram_available_mb: Optional[int]
    cpu_count: Optional[int]
    load_avg_1m: Optional[float]
    disk_total_mb: Optional[int]
    disk_free_mb: Optional[int]
    gpu: GpuInfo

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


# ---------------------------------------------------------------------------
# Optional psutil accelerator
# ---------------------------------------------------------------------------

def _try_psutil_memory() -> Optional[tuple[int, int]]:
    try:
        import psutil  # type: ignore
    except Exception:
        return None
    try:
        vm = psutil.virtual_memory()
        return int(vm.total // _MB), int(vm.available // _MB)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Memory (stdlib, per-platform)
# ---------------------------------------------------------------------------

def _linux_memory() -> Optional[tuple[int, int]]:
    try:
        info: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            kb = int(rest.strip().split()[0])
            info[key] = kb
        total = info.get("MemTotal")
        avail = info.get("MemAvailable", info.get("MemFree"))
        if total is None:
            return None
        return total // 1024, (avail // 1024 if avail is not None else total // 1024)
    except Exception:
        return None


def _windows_memory() -> Optional[tuple[int, int]]:
    class _MemStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        stat = _MemStatus()
        stat.dwLength = ctypes.sizeof(_MemStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)) == 0:
            return None
        return int(stat.ullTotalPhys // _MB), int(stat.ullAvailPhys // _MB)
    except Exception:
        return None


def _macos_memory() -> Optional[tuple[int, int]]:
    try:
        total = int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2).strip()
        )
        total_mb = total // _MB
    except Exception:
        return None

    # Available memory from vm_stat (free + inactive pages).
    available_mb = total_mb
    try:
        out = subprocess.check_output(["vm_stat"], timeout=2).decode()
        page_size = 4096
        m = re.search(r"page size of (\d+) bytes", out)
        if m:
            page_size = int(m.group(1))
        free = re.search(r"Pages free:\s+(\d+)", out)
        inactive = re.search(r"Pages inactive:\s+(\d+)", out)
        pages = 0
        if free:
            pages += int(free.group(1))
        if inactive:
            pages += int(inactive.group(1))
        if pages:
            available_mb = (pages * page_size) // _MB
    except Exception:
        pass
    return total_mb, available_mb


def _sysconf_total() -> Optional[int]:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")  # type: ignore[attr-defined]
        page_size = os.sysconf("SC_PAGE_SIZE")  # type: ignore[attr-defined]
        return (pages * page_size) // _MB
    except (ValueError, AttributeError, OSError):
        return None


def _detect_memory() -> tuple[Optional[int], Optional[int], str]:
    via_psutil = _try_psutil_memory()
    if via_psutil is not None:
        return via_psutil[0], via_psutil[1], "psutil"

    system = platform.system()
    result: Optional[tuple[int, int]] = None
    if system == "Linux":
        result = _linux_memory()
    elif system == "Windows":
        result = _windows_memory()
    elif system == "Darwin":
        result = _macos_memory()

    if result is None:
        total = _sysconf_total()
        return total, total, "stdlib"
    return result[0], result[1], "stdlib"


# ---------------------------------------------------------------------------
# GPU (cached — presence does not change during a process)
# ---------------------------------------------------------------------------

_gpu_cache: Optional[GpuInfo] = None


def _probe_nvidia() -> Optional[GpuInfo]:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            timeout=settings.GPU_PROBE_TIMEOUT,
            stderr=subprocess.DEVNULL,
        ).decode()
    except Exception:
        return None
    line = out.strip().splitlines()[0] if out.strip() else ""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None
    try:
        return GpuInfo(
            available=True,
            name=parts[0],
            total_mb=int(float(parts[1])),
            free_mb=int(float(parts[2])),
            backend="cuda",
        )
    except ValueError:
        return GpuInfo(available=True, name=parts[0], backend="cuda")


def _probe_apple_metal() -> Optional[GpuInfo]:
    if platform.system() != "Darwin":
        return None
    if platform.machine() != "arm64":
        return None
    # Apple Silicon shares system memory with the GPU (unified memory).
    total_mb, _, _ = _detect_memory()
    return GpuInfo(
        available=True,
        name="Apple Silicon (unified memory)",
        total_mb=total_mb,
        backend="metal",
    )


def detect_gpu(refresh: bool = False) -> GpuInfo:
    global _gpu_cache
    if _gpu_cache is not None and not refresh:
        return _gpu_cache
    gpu = _probe_nvidia() or _probe_apple_metal() or GpuInfo(available=False)
    _gpu_cache = gpu
    return gpu


# ---------------------------------------------------------------------------
# Snapshot + assessment
# ---------------------------------------------------------------------------

def detect_resources(path: Optional[str | os.PathLike] = None) -> ResourceSnapshot:
    total_mb, avail_mb, source = _detect_memory()

    load_avg: Optional[float] = None
    try:
        load_avg = os.getloadavg()[0]  # not available on Windows
    except (AttributeError, OSError):
        load_avg = None

    disk_total = disk_free = None
    try:
        usage = shutil.disk_usage(str(path) if path else Path.cwd())
        disk_total = usage.total // _MB
        disk_free = usage.free // _MB
    except Exception:
        pass

    return ResourceSnapshot(
        platform=platform.system() or "unknown",
        source=source,
        ram_total_mb=total_mb,
        ram_available_mb=avail_mb,
        cpu_count=os.cpu_count(),
        load_avg_1m=load_avg,
        disk_total_mb=disk_total,
        disk_free_mb=disk_free,
        gpu=detect_gpu(),
    )


def assess_plan(estimate: dict, snapshot: ResourceSnapshot) -> list[str]:
    """Compare an estimate against a snapshot and return non-blocking warnings.

    Warnings never prevent execution; they exist so the UI can surface risk.
    """
    warnings: list[str] = []

    est_ram = estimate.get("estimated_ram_mb")
    if est_ram and snapshot.ram_available_mb is not None:
        if est_ram > snapshot.ram_available_mb:
            warnings.append(
                f"Estimated memory ({est_ram} MB) exceeds available RAM "
                f"({snapshot.ram_available_mb} MB). The run may swap or fail to "
                "load the model. Consider a smaller model or a lighter profile."
            )

    est_gpu = estimate.get("estimated_gpu_mb")
    if est_gpu:
        if not snapshot.gpu.available:
            warnings.append(
                "No GPU detected; inference will run on CPU and be substantially "
                "slower than the time estimate assumes."
            )
        elif snapshot.gpu.total_mb is not None and est_gpu > snapshot.gpu.total_mb:
            warnings.append(
                f"Estimated GPU memory ({est_gpu} MB) exceeds detected VRAM "
                f"({snapshot.gpu.total_mb} MB); the model may spill to system RAM."
            )

    est_disk = estimate.get("estimated_disk_mb")
    if est_disk and snapshot.disk_free_mb is not None:
        if est_disk > snapshot.disk_free_mb:
            warnings.append(
                f"Estimated disk usage ({est_disk:.1f} MB) exceeds free disk space "
                f"({snapshot.disk_free_mb} MB)."
            )

    return warnings
