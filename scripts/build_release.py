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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checksums import write_sums  # noqa: E402
from version import read_version  # noqa: E402

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
RELEASES = ROOT / "releases"

# Only end-user documentation ships in a release. Internal engineering docs
# (docs/architecture/, architecture-audit*, *-architecture.md) are excluded so
# the public download contains nothing developer-only. Files absent from the
# repo are skipped silently.
END_USER_DOCS = [
    "quickstart.md",
    "installation.md",
    "cli-reference.md",
    "architecture-overview.md",
    "first-run-experience.md",
    "model-installation.md",
    "providers.md",
    "runtime.md",
    "network-profile.md",
    "gpu-support.md",
    "evaluation-engine.md",
    "intelligent-evaluation.md",
    "troubleshooting.md",
    "common-errors.md",
    "faq.md",
]

_IGNORE = shutil.ignore_patterns(
    # caches / build leftovers / local data
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", "*.db",
    "*.sqlite", "*.sqlite3", ".env", "*.key", "*.pem", "*.p12", "*.pfx", "*.log",
    ".vite", "node_modules", "dist", ".mypy_cache",
    ".venv", "venv", ".idea", ".vscode", ".DS_Store",
    # developer-only files — never shipped to end users
    "tests", "pytest.ini", "requirements-dev.txt", "conftest.py",
)


def _backend_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set(_IGNORE(directory, names))
    if Path(directory).resolve() == (ROOT / "backend").resolve():
        # These are generated on the developer's machine, not release assets.
        # In particular, outputs/ can contain private training checkpoints.
        ignored.update({".redforge", "artifacts", "checkpoints", "logs", "outputs",
                        "runs", "unsloth_compiled_cache"} & set(names))
    # A checkout may contain an old compiled UI. Ship only the just-built dist,
    # not stale chunks that survived from an earlier version.
    if Path(directory).resolve() == (ROOT / "backend" / "app").resolve():
        ignored.add("static")
    return ignored


def _cli_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set(_IGNORE(directory, names))
    if Path(directory).resolve() == (ROOT / "cli").resolve():
        ignored.update({"build", "redforge_cli.egg-info", "redforge.egg-info"} & set(names))
    return ignored


def _version() -> str:
    """Delegates to the single source of truth (scripts/version.py → VERSION)."""
    return read_version()


def build_frontend() -> Path:
    fe = ROOT / "frontend"
    print("• Building frontend (npm run build)…")
    npm = ["cmd", "/c", "npm", "run", "build"] if os.name == "nt" else ["npm", "run", "build"]
    subprocess.run(npm, cwd=str(fe), check=True)  # explicit arg list, never shell=True
    dist = fe / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("frontend build did not produce dist/index.html")
    return dist


def stage(version: str, dist: Path) -> Path:
    staging = RELEASES / f"redforge-{version}"
    if staging.exists():
        raise SystemExit(f"Refusing to overwrite existing staging directory: {staging}")
    staging.mkdir(parents=True)

    print("• Staging backend, cli, datasets, docs…")
    shutil.copytree(ROOT / "backend", staging / "backend", ignore=_backend_ignore)
    shutil.copytree(ROOT / "cli", staging / "cli", ignore=_cli_ignore)
    shutil.copytree(ROOT / "datasets", staging / "datasets", ignore=_IGNORE)
    _stage_docs(staging / "docs")
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


def _stage_docs(dest: Path) -> None:
    """Copy only end-user docs — never internal engineering documents."""
    dest.mkdir(parents=True, exist_ok=True)
    shipped = 0
    for name in END_USER_DOCS:
        src = ROOT / "docs" / name
        if src.is_file():
            shutil.copy2(src, dest / name)
            shipped += 1
    print(f"  docs: {shipped} end-user file(s) (internal engineering docs excluded)")


def _write_launchers(staging: Path) -> None:
    (staging / "install.cmd").write_text(
        "@echo off\r\n"
        "if /I \"%REDFORGE_NETWORK_PROFILE%\"==\"connected\" (\r\n"
        "  python -m pip install -r backend\\requirements.lock\r\n"
        ") else (\r\n"
        "  if defined REDFORGE_WHEELHOUSE (\r\n"
        "    python -m pip install --no-index --find-links \"%REDFORGE_WHEELHOUSE%\" -r backend\\requirements.lock\r\n"
        "  ) else (\r\n"
        "    python -m pip install --no-index -r backend\\requirements.lock\r\n"
        "  )\r\n"
        ")\r\n"
        "if errorlevel 1 (\r\n"
        "  echo Strict mode needs preinstalled dependencies or REDFORGE_WHEELHOUSE.\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
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
        "#!/usr/bin/env bash\nset -e\n"
        'if [ "$(printf %s "${REDFORGE_NETWORK_PROFILE:-strict}" | tr "[:upper:]" "[:lower:]")" = "connected" ]; then\n'
        '  python3 -m pip install -r backend/requirements.lock\n'
        'elif [ -n "${REDFORGE_WHEELHOUSE:-}" ]; then\n'
        '  python3 -m pip install --no-index --find-links "$REDFORGE_WHEELHOUSE" -r backend/requirements.lock\n'
        'else\n'
        '  python3 -m pip install --no-index -r backend/requirements.lock\n'
        'fi\n'
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
        "Requirements: Python 3.11+ and an installed local runtime/model.\n"
        "Node.js is NOT required.\n\n"
        "Strict mode has no package-index access. Provide REDFORGE_WHEELHOUSE\n"
        "or preinstall dependencies. See docs/network-profile.md.\n\n"
        "1. Install:   install.cmd   (Windows)   |   ./install.sh   (Linux/macOS)\n"
        "2. Start:     start.cmd                 |   ./start.sh\n"
        "3. Your browser opens automatically. Follow the on-screen setup.\n",
        encoding="utf-8",
    )


def archive(staging: Path, version: str) -> list[Path]:
    print("• Creating archives…")
    base = RELEASES / f"redforge-{version}"
    for suffix in (".zip", ".tar.gz"):
        if Path(str(base) + suffix).exists():
            raise SystemExit(f"Refusing to overwrite existing archive: {base}{suffix}")
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
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="write staging and archives to a new or empty output directory")
    args = ap.parse_args()

    global RELEASES
    if args.output_dir is not None:
        RELEASES = args.output_dir.resolve()
    if RELEASES.resolve() in {ROOT.resolve(), ROOT.parent.resolve(), Path.home().resolve()}:
        raise SystemExit("Choose a dedicated release output directory")
    version = args.version or _version()
    RELEASES.mkdir(exist_ok=True)
    if (RELEASES / "SHA256SUMS.txt").exists():
        raise SystemExit(f"Refusing to overwrite existing checksums: {RELEASES / 'SHA256SUMS.txt'}")
    for suffix in ("", ".zip", ".tar.gz"):
        target = RELEASES / f"redforge-{version}{suffix}"
        if target.exists():
            raise SystemExit(f"Refusing to overwrite existing release output: {target}")
    print(f"Building RedForge release {version}\n")

    dist = ROOT / "frontend" / "dist"
    if not args.skip_frontend or not (dist / "index.html").is_file():
        dist = build_frontend()

    staging = stage(version, dist)
    artifacts = archive(staging, version)

    print("• Writing SHA256SUMS.txt…")
    sums = write_sums(artifacts, RELEASES / "SHA256SUMS.txt")

    print("\n✓ Release built (no Node.js required to run):")
    print(f"  staging: {staging}")
    for a in artifacts:
        size = a.stat().st_size // 1024
        print(f"  {a.name}  ({size} KB)")
    print(f"  {sums.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
