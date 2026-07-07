#!/usr/bin/env python3
"""Build a self-contained RedForge release.

Pipeline (Part 2.5 — the released app must NOT require Node.js):

    npm run build (frontend)  →  copy dist into backend/app/static  →
    stage backend + cli + datasets + docs  →  archive (.zip and .tar.gz)

The resulting release runs with **Python + Ollama only**: the backend serves the
API and the bundled frontend as a single process.

Usage:
    python scripts/build_release.py [--skip-frontend] [--version X.Y.Z]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
RELEASES = ROOT / "releases"

_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.db",
    ".vite", "node_modules", "dist", ".mypy_cache",
)


def _version() -> str:
    vf = ROOT / "VERSION"
    return vf.read_text().strip() if vf.is_file() else "0.0.0"


def build_frontend() -> Path:
    fe = ROOT / "frontend"
    print("• Building frontend (npm run build)…")
    subprocess.run(["npm", "run", "build"], cwd=str(fe), check=True, shell=(os.name == "nt"))
    dist = fe / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("frontend build did not produce dist/index.html")
    return dist


def stage(version: str, dist: Path) -> Path:
    staging = RELEASES / f"redforge-{version}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    print("• Staging backend, cli, datasets, docs…")
    shutil.copytree(ROOT / "backend", staging / "backend", ignore=_IGNORE)
    shutil.copytree(ROOT / "cli", staging / "cli", ignore=_IGNORE)
    shutil.copytree(ROOT / "datasets", staging / "datasets", ignore=_IGNORE)
    shutil.copytree(ROOT / "docs", staging / "docs", ignore=_IGNORE)
    for f in ("VERSION", "README.md", "CHANGELOG.md", "RELEASE_NOTES.md",
              "LICENSE", "ROADMAP.md", "CONTRIBUTING.md", "SECURITY.md"):
        src = ROOT / f
        if src.is_file():
            shutil.copy2(src, staging / f)

    # Bundle the built frontend so the backend serves it — no Node.js at runtime.
    static = staging / "backend" / "app" / "static"
    print(f"• Bundling frontend build → {static.relative_to(staging)}")
    shutil.copytree(dist, static)

    _write_launchers(staging)
    return staging


def _write_launchers(staging: Path) -> None:
    (staging / "install.cmd").write_text(
        "@echo off\r\n"
        "python -m pip install -r backend\\requirements.txt\r\n"
        "echo.\r\n"
        "echo RedForge installed. Run start.cmd to launch.\r\n",
        encoding="utf-8",
    )
    (staging / "start.cmd").write_text(
        "@echo off\r\n"
        "set \"PYTHONPATH=%~dp0cli;%PYTHONPATH%\"\r\n"
        "python -m redforge start %*\r\n",
        encoding="utf-8",
    )
    (staging / "install.sh").write_text(
        "#!/usr/bin/env bash\nset -e\npython3 -m pip install -r backend/requirements.txt\n"
        'echo "RedForge installed. Run ./start.sh to launch."\n',
        encoding="utf-8",
    )
    (staging / "start.sh").write_text(
        "#!/usr/bin/env bash\nset -e\ncd \"$(dirname \"$0\")\"\n"
        'export PYTHONPATH="$PWD/cli:${PYTHONPATH:-}"\nexec python3 -m redforge start "$@"\n',
        encoding="utf-8",
    )
    for sh in ("install.sh", "start.sh"):
        try:
            os.chmod(staging / sh, 0o755)
        except OSError:
            pass
    (staging / "READ_ME_FIRST.txt").write_text(
        "RedForge — quick start\n"
        "======================\n\n"
        "Requirements: Python 3.11+ and Ollama (https://ollama.com/download).\n"
        "Node.js is NOT required.\n\n"
        "1. Install:   install.cmd   (Windows)   |   ./install.sh   (Linux/macOS)\n"
        "2. Start:     start.cmd                 |   ./start.sh\n"
        "3. Your browser opens automatically. Follow the on-screen setup.\n",
        encoding="utf-8",
    )


def archive(staging: Path, version: str) -> list[Path]:
    print("• Creating archives…")
    base = RELEASES / f"redforge-{version}"
    artifacts = []
    zip_path = Path(shutil.make_archive(str(base), "zip", root_dir=RELEASES, base_dir=staging.name))
    artifacts.append(zip_path)
    tar_path = Path(shutil.make_archive(str(base), "gztar", root_dir=RELEASES, base_dir=staging.name))
    artifacts.append(tar_path)
    return artifacts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-frontend", action="store_true", help="reuse existing frontend/dist")
    ap.add_argument("--version", default=None)
    args = ap.parse_args()

    version = args.version or _version()
    RELEASES.mkdir(exist_ok=True)
    print(f"Building RedForge release {version}\n")

    dist = ROOT / "frontend" / "dist"
    if not args.skip_frontend or not (dist / "index.html").is_file():
        dist = build_frontend()

    staging = stage(version, dist)
    artifacts = archive(staging, version)

    print("\n✓ Release built (no Node.js required to run):")
    print(f"  staging: {staging}")
    for a in artifacts:
        size = a.stat().st_size // 1024
        print(f"  {a.name}  ({size} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
