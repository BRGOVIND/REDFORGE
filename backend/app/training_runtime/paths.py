"""Where the managed training runtime lives.

The training stack (PyTorch + CUDA + Unsloth + friends) is 2–4 GB, so it is **not**
bundled in the installer. It is installed on demand into a RedForge-owned virtual
environment, completely isolated from:

  • the user's global/system Python  — we never `pip install` outside our venv,
  • the frozen backend               — which has no torch and never imports one,
  • other RedForge data              — so it can be deleted without losing work.

Per-OS conventions (honours REDFORGE_HOME / portable installs first, so a portable
copy keeps its runtime beside the executable and leaves no trace on the host):

  Windows  %LOCALAPPDATA%\\RedForge\\training-runtime
  macOS    ~/Library/Application Support/RedForge/training-runtime
  Linux    ~/.local/share/redforge/training-runtime
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

DIR_NAME = "training-runtime"


def _platform_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "RedForge"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RedForge"
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "redforge"


def runtime_root() -> Path:
    """The managed runtime directory. Explicit override wins, then a portable /
    configured REDFORGE_HOME, then the OS convention."""
    override = os.environ.get("REDFORGE_TRAINING_RUNTIME")
    if override:
        return Path(override)
    home = os.environ.get("REDFORGE_HOME")
    if home:
        return Path(home) / DIR_NAME
    return _platform_data_dir() / DIR_NAME


def venv_dir() -> Path:
    return runtime_root() / "venv"


def python_executable(root: Path | None = None) -> Path:
    """The managed interpreter. Training runs as a subprocess of *this*, never
    in the backend process — that is what keeps the two environments isolated."""
    base = (root or runtime_root()) / "venv"
    if sys.platform == "win32":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def state_file() -> Path:
    """Install bookkeeping — lets an interrupted install resume instead of restarting."""
    return runtime_root() / "install-state.json"


def log_file() -> Path:
    return runtime_root() / "install.log"


def marker_file() -> Path:
    """Written only after verification passes; its absence means 'not usable'."""
    return runtime_root() / "READY.json"
