#!/usr/bin/env python3
"""Stage the backend for desktop packaging (run in CI before electron-builder).

Pipeline:
  1) Build the frontend → backend/app/static (single-process serving).
  2) PyInstaller-freeze the backend → a self-contained ``redforge-backend`` binary
     (so end users need NO system Python).
  3) Assemble ``desktop/resources/backend/`` with the binary + app/static + datasets.

electron-builder then copies ``resources/backend`` into the app's resources, where the
BackendSupervisor finds and launches it.

Usage:
    python desktop/scripts/stage-backend.py [--skip-frontend] [--skip-freeze]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]      # repo root
DESKTOP = ROOT / "desktop"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
STATIC = BACKEND / "app" / "static"
RESOURCES = DESKTOP / "resources" / "backend"
EXE = "redforge-backend.exe" if os.name == "nt" else "redforge-backend"

# Heavy, GPU-only deps are excluded from the frozen backend (kept optional/lazy) so
# the installer stays small. Real training installs them separately (experimental).
EXCLUDES = ["torch", "unsloth", "unsloth_zoo", "bitsandbytes", "xformers", "triton",
            "transformers", "peft", "trl", "datasets", "accelerate", "flash_attn"]


def run(cmd, cwd=None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def build_frontend():
    npm = "npm.cmd" if os.name == "nt" else "npm"
    run([npm, "ci"], cwd=FRONTEND)
    run([npm, "run", "build"], cwd=FRONTEND)
    dist = FRONTEND / "dist"
    if STATIC.exists():
        shutil.rmtree(STATIC)
    shutil.copytree(dist, STATIC)
    print(f"staged frontend → {STATIC}")


def freeze_backend():
    entry = DESKTOP / "backend_entry.py"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", "redforge-backend", "--onedir", "--console",
        "--paths", str(BACKEND),
        "--collect-submodules", "app",
        "--collect-data", "app",
        "--hidden-import", "uvicorn", "--hidden-import", "aiosqlite",
        "--hidden-import", "app.main",
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    args += ["--distpath", str(DESKTOP / "build" / "pyi"), "--workpath", str(DESKTOP / "build" / "pyi-work"),
             "--specpath", str(DESKTOP / "build"), str(entry)]
    run(args, cwd=BACKEND)


def assemble():
    if RESOURCES.exists():
        shutil.rmtree(RESOURCES)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    frozen = DESKTOP / "build" / "pyi" / "redforge-backend"
    if frozen.is_dir():
        # copy the PyInstaller onedir contents (binary + libs) into resources/backend
        shutil.copytree(frozen, RESOURCES, dirs_exist_ok=True)
    else:
        print("WARNING: frozen backend not found — the desktop app will fall back to system Python.")
    # bundled frontend + datasets alongside the binary
    if STATIC.exists():
        shutil.copytree(STATIC, RESOURCES / "app" / "static", dirs_exist_ok=True)
    if (ROOT / "datasets").exists():
        shutil.copytree(ROOT / "datasets", RESOURCES / "datasets", dirs_exist_ok=True)
    print(f"assembled desktop backend → {RESOURCES}")
    print("contains binary:", (RESOURCES / EXE).exists())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-frontend", action="store_true")
    ap.add_argument("--skip-freeze", action="store_true")
    a = ap.parse_args()
    if not a.skip_frontend:
        build_frontend()
    if not a.skip_freeze:
        freeze_backend()
    assemble()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
