"""Training-runtime domain — pure data, no I/O, no SQLAlchemy.

Models "is the real training engine installed, and if not, what exactly is
missing and what will it cost the user to fix it?" Detection lives in
``detector.py`` and installation in ``installer.py``; keeping this layer pure is
what lets the whole decision matrix be unit-tested without a 4 GB download.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# The user-visible state of the managed runtime.
#   absent      — never installed
#   partial     — an install was interrupted; resumable
#   broken      — installed but verification failed (bad wheel, missing CUDA…)
#   ready       — verified; real LoRA/QLoRA is available
#   installing  — an install Job is currently running
STATUSES = ("absent", "partial", "broken", "ready", "installing")


@dataclass(frozen=True)
class PackageCheck:
    """One dependency inside the managed runtime."""

    name: str
    label: str
    required: bool
    installed: bool = False
    version: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "required": self.required,
            "installed": self.installed, "version": self.version, "detail": self.detail,
        }


@dataclass(frozen=True)
class GpuInfo:
    available: bool = False
    name: Optional[str] = None
    vram_mb: Optional[int] = None
    cuda_version: Optional[str] = None
    driver_version: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "available": self.available, "name": self.name, "vram_mb": self.vram_mb,
            "cuda_version": self.cuda_version, "driver_version": self.driver_version,
        }


@dataclass(frozen=True)
class InstallPlan:
    """What installing would actually do — shown before the user commits."""

    variant: str                       # e.g. "cu121" | "cu124" | "cpu"
    torch_index_url: str
    packages: list[str] = field(default_factory=list)
    download_mb_estimate: int = 0
    minutes_estimate: str = ""
    reason: str = ""                   # why this variant was chosen
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "variant": self.variant, "torch_index_url": self.torch_index_url,
            "packages": self.packages, "download_mb_estimate": self.download_mb_estimate,
            "minutes_estimate": self.minutes_estimate, "reason": self.reason,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class RuntimeReport:
    status: str
    root: str
    python_executable: Optional[str]
    python_version: Optional[str]
    gpu: GpuInfo
    packages: list[PackageCheck]
    plan: Optional[InstallPlan] = None
    disk_free_mb: Optional[int] = None
    message: str = ""
    # Set when a previous install stopped part-way.
    resumable: bool = False
    installed_at: Optional[str] = None
    # Whether torch *inside the managed runtime* can see the GPU. Distinct from
    # ``gpu.available`` (which comes from nvidia-smi and needs no runtime): a
    # machine can have a working GPU while the installed torch build cannot use
    # it — the classic CUDA/driver mismatch. None means "not determined yet".
    cuda_available: Optional[bool] = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def missing_required(self) -> list[str]:
        return [p.label for p in self.packages if p.required and not p.installed]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "ready": self.ready,
            "root": self.root,
            "python_executable": self.python_executable,
            "python_version": self.python_version,
            "gpu": self.gpu.to_dict(),
            "packages": [p.to_dict() for p in self.packages],
            "plan": self.plan.to_dict() if self.plan else None,
            "disk_free_mb": self.disk_free_mb,
            "message": self.message,
            "resumable": self.resumable,
            "installed_at": self.installed_at,
            "cuda_available": self.cuda_available,
            "missing_required": self.missing_required,
        }
