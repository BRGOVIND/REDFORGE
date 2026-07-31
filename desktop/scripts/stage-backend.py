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
# PyInstaller scratch lives OUTSIDE desktop/build — that directory is
# electron-builder's `buildResources` (icon.png, entitlements) and must stay clean.
PYI = DESKTOP / ".pyinstaller"
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
    # The training worker is EXECUTED BY THE MANAGED RUNTIME's interpreter, so it
    # must exist as a real .py file on disk. PyInstaller would otherwise compile it
    # into the archive, where no external interpreter can read it.
    worker = BACKEND / "app" / "training_runtime" / "worker.py"
    sep = ";" if os.name == "nt" else ":"
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", "redforge-backend", "--onedir", "--console",
        "--paths", str(BACKEND),
        "--collect-submodules", "app",
        "--collect-data", "app",
        "--add-data", f"{worker}{sep}app/training_runtime",
        "--hidden-import", "uvicorn", "--hidden-import", "aiosqlite",
        "--hidden-import", "app.main",
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    PYI.mkdir(parents=True, exist_ok=True)
    args += ["--distpath", str(PYI / "dist"), "--workpath", str(PYI / "work"),
             "--specpath", str(PYI), str(entry)]
    run(args, cwd=BACKEND)


def assemble():
    if RESOURCES.exists():
        shutil.rmtree(RESOURCES)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    frozen = PYI / "dist" / "redforge-backend"
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
    # app.version.read_version() walks up from the module looking for VERSION.
    # Inside the frozen bundle that walk leaves the repo entirely, so without
    # this the shipped app reports 0.0.0 everywhere (API, About, UI footer).
    shutil.copy2(ROOT / "VERSION", RESOURCES / "VERSION")
    print(f"assembled desktop backend → {RESOURCES}")
    print("contains binary:", (RESOURCES / EXE).exists())


def verify() -> list[str]:
    """Everything an end user's machine needs must be inside resources/backend.

    A release build that silently omits the frozen binary would fall back to a
    system Python the user does not have, so this is a hard gate in CI.
    """
    problems: list[str] = []
    if not (RESOURCES / EXE).is_file():
        problems.append(f"missing frozen backend binary: {RESOURCES / EXE}")
    if not (RESOURCES / "app" / "static" / "index.html").is_file():
        problems.append(f"missing bundled UI: {RESOURCES / 'app' / 'static' / 'index.html'}")
    # Without this file on disk the managed training runtime cannot be launched.
    worker_candidates = [
        RESOURCES / "app" / "training_runtime" / "worker.py",
        RESOURCES / "_internal" / "app" / "training_runtime" / "worker.py",
    ]
    if not any(p.is_file() for p in worker_candidates):
        problems.append(
            "missing training worker: app/training_runtime/worker.py "
            "(real training would be impossible in the packaged app)"
        )
    version_file = RESOURCES / "VERSION"
    if not version_file.is_file():
        problems.append(f"missing VERSION: {version_file} (the app would report 0.0.0)")
    elif version_file.read_text(encoding="utf-8").strip() != (ROOT / "VERSION").read_text(encoding="utf-8").strip():
        problems.append("staged VERSION does not match the repo VERSION")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-frontend", action="store_true")
    ap.add_argument("--skip-freeze", action="store_true")
    ap.add_argument("--require-frozen", action="store_true",
                    help="fail if the frozen backend or bundled UI is missing (use in CI)")
    a = ap.parse_args()
    if not a.skip_frontend:
        build_frontend()
    if not a.skip_freeze:
        freeze_backend()
    assemble()
    problems = verify()
    if problems:
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        if a.require_frozen:
            print("✗ staging incomplete — refusing to package", file=sys.stderr)
            return 1
        print("WARNING: staging incomplete (dev build will fall back to system Python).",
              file=sys.stderr)
    else:
        print("✓ desktop backend staged and complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
