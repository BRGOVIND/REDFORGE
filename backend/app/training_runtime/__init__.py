"""Training Runtime (bounded context).

Owns the **optional** 2–4 GB training engine (PyTorch + CUDA + Unsloth + friends)
that the installer deliberately excludes to keep downloads small.

Responsibilities:
  • detect what is installed in the RedForge-managed virtual environment,
  • plan a hardware-appropriate install (CUDA wheel variant, size, warnings),
  • install it as a resumable Job visible in the Global Task Manager,
  • verify it before ever reporting "ready".

Isolation is the core invariant: the runtime lives in its own venv, the backend
process never imports torch, and training executes as a subprocess of the managed
interpreter (see ``worker.py`` and ``app.training.providers.managed``).

Public surface:
    runtime_service.report(refresh=False) -> RuntimeReport
    register_training_runtime_handlers()
"""
from .domain import GpuInfo, InstallPlan, PackageCheck, RuntimeReport
from .installer import RuntimeInstaller, register_training_runtime_handlers, uninstall
from .service import TrainingRuntimeService, runtime_service

__all__ = [
    "GpuInfo",
    "InstallPlan",
    "PackageCheck",
    "RuntimeReport",
    "RuntimeInstaller",
    "TrainingRuntimeService",
    "register_training_runtime_handlers",
    "runtime_service",
    "uninstall",
]
