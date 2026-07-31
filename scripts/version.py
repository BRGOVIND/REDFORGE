#!/usr/bin/env python3
"""Single source of truth for the RedForge version.

The repo-root ``VERSION`` file is the *only* place a version literal may live.
Every other component derives from it:

    VERSION ──┬─ redforge._version.read_version()   (CLI, stdlib)
              ├─ app.version.read_version()         (backend / FastAPI `version=`)
              ├─ pyproject.toml  [tool.setuptools.dynamic] version = {file = "VERSION"}
              ├─ cli/pyproject.toml                  version = {attr = "redforge.__version__"}
              ├─ vite.config.ts  → define __APP_VERSION__
              ├─ installers/windows/redforge.iss     (ISPP FileRead, /DAppVersion override)
              ├─ installers/linux/build-appimage.sh  (cat VERSION)
              └─ desktop/package.json  "version"     (electron-builder REQUIRES a literal;
                                                      kept in lockstep via --sync/--check)

Usage:
    python scripts/version.py            # print the version
    python scripts/version.py --check    # verify nothing re-introduced a literal
    python scripts/version.py --sync     # rewrite the derived literals from VERSION
    python scripts/version.py --set X.Y.Z  # bump VERSION, then sync
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_ANY_VERSION = r"\d+\.\d+\.\d+"


def read_version() -> str:
    """The one authoritative read. Raises if the file is missing or malformed."""
    if not VERSION_FILE.is_file():
        raise SystemExit(f"missing {VERSION_FILE}")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not _SEMVER.match(version):
        raise SystemExit(f"VERSION is not semver: {version!r}")
    return version


# ---------------------------------------------------------------------------
# Drift guard
# ---------------------------------------------------------------------------

# (path, regex that must NOT match, why)
_FORBIDDEN: list[tuple[str, str, str]] = [
    ("pyproject.toml", rf'^version\s*=\s*"{_ANY_VERSION}"', "use [tool.setuptools.dynamic]"),
    ("cli/pyproject.toml", rf'^version\s*=\s*"{_ANY_VERSION}"', "use [tool.setuptools.dynamic]"),
    ("backend/app/main.py", rf'version\s*=\s*"{_ANY_VERSION}"', "import app.version.__version__"),
    ("cli/redforge/cli.py", rf'__version__\s*=\s*"{_ANY_VERSION}"', "import from redforge._version"),
    ("cli/redforge/__init__.py", rf'__version__\s*=\s*"{_ANY_VERSION}"', "import from redforge._version"),
    ("installers/windows/redforge.iss", rf'#define\s+AppVersion\s+"{_ANY_VERSION}"', "read VERSION via ISPP"),
]


def _literal_problems() -> list[str]:
    problems: list[str] = []
    for rel, pattern, hint in _FORBIDDEN:
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"{rel}: missing")
            continue
        rx = re.compile(pattern, re.MULTILINE)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(line):
                problems.append(f"{rel}:{lineno}: hardcoded version — {hint}")
    return problems


def _package_json_problems() -> list[str]:
    path = ROOT / "frontend" / "package.json"
    if not path.is_file():
        return [f"{path.relative_to(ROOT)}: missing"]
    data = json.loads(path.read_text(encoding="utf-8"))
    if "version" in data:
        return [
            "frontend/package.json: remove the `version` field "
            "(private package; vite.config.ts injects __APP_VERSION__ from VERSION)"
        ]
    return []


# --- desktop/package.json ---------------------------------------------------
# electron-builder resolves the app version from package.json and bakes it into
# installer filenames, the NSIS uninstall entry, the .deb control file and the
# auto-update feed (latest.yml). It cannot read an external file, so this is the
# one place a literal is *required* — we keep it honest with --sync/--check.

DESKTOP_PACKAGE_JSON = ROOT / "desktop" / "package.json"


def _desktop_version() -> tuple[str | None, str | None]:
    """(version, error) for desktop/package.json."""
    if not DESKTOP_PACKAGE_JSON.is_file():
        return None, "desktop/package.json: missing"
    try:
        # utf-8-sig: tolerate a BOM (some Windows editors add one) without
        # failing the release gate.
        data = json.loads(DESKTOP_PACKAGE_JSON.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"desktop/package.json: invalid JSON ({exc})"
    version = data.get("version")
    if not isinstance(version, str):
        return None, "desktop/package.json: missing a string `version` field"
    return version, None


def _desktop_problems(expected: str) -> list[str]:
    version, err = _desktop_version()
    if err:
        return [err]
    if version != expected:
        return [
            f"desktop/package.json: version {version!r} != VERSION {expected!r} "
            f"— run `python scripts/version.py --sync`"
        ]
    return []


def sync() -> int:
    """Rewrite every derived literal from VERSION. Idempotent."""
    expected = read_version()
    changed: list[str] = []

    version, err = _desktop_version()
    if err:
        print(f"✗ {err}", file=sys.stderr)
        return 1
    if version != expected:
        # Targeted line rewrite so formatting/key order survive untouched.
        text = DESKTOP_PACKAGE_JSON.read_text(encoding="utf-8-sig")
        new_text, count = re.subn(
            r'("version"\s*:\s*)"[^"]*"', rf'\1"{expected}"', text, count=1
        )
        if count != 1:
            print("✗ desktop/package.json: could not locate the version field", file=sys.stderr)
            return 1
        DESKTOP_PACKAGE_JSON.write_text(new_text, encoding="utf-8")
        changed.append(f"desktop/package.json: {version} → {expected}")

    if changed:
        for c in changed:
            print(f"↻ {c}")
    else:
        print(f"✓ already in sync at {expected}")
    return 0


def set_version(new: str) -> int:
    if not _SEMVER.match(new):
        print(f"✗ not semver: {new!r}", file=sys.stderr)
        return 1
    VERSION_FILE.write_text(f"{new}\n", encoding="utf-8")
    print(f"↻ VERSION → {new}")
    return sync()


def _runtime_problems(expected: str) -> list[str]:
    """Import the CLI and backend resolvers in subprocesses and compare."""
    problems: list[str] = []
    probes = {
        "redforge._version": (
            ROOT / "cli",
            "from redforge._version import read_version; print(read_version())",
        ),
        "app.version": (
            ROOT / "backend",
            "from app.version import read_version; print(read_version())",
        ),
    }
    for label, (path, code) in probes.items():
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env={**_env(), "PYTHONPATH": str(path)},
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            problems.append(f"{label}: failed to resolve ({proc.stderr.strip().splitlines()[-1:]})")
            continue
        actual = proc.stdout.strip()
        if actual != expected:
            problems.append(f"{label}: resolved {actual!r}, expected {expected!r}")
    return problems


def _env() -> dict:
    import os

    env = dict(os.environ)
    env.pop("REDFORGE_HOME", None)  # never let a local install shadow the repo
    return env


def check() -> int:
    expected = read_version()
    problems = (
        _literal_problems()
        + _package_json_problems()
        + _desktop_problems(expected)
        + _runtime_problems(expected)
    )
    if problems:
        print(f"✗ version drift (VERSION = {expected})\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"✓ version {expected} is single-sourced from VERSION")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="verify no duplicated version literals")
    ap.add_argument("--sync", action="store_true", help="rewrite derived literals from VERSION")
    ap.add_argument("--set", metavar="X.Y.Z", help="bump VERSION to X.Y.Z, then --sync")
    args = ap.parse_args()
    if args.set:
        return set_version(args.set)
    if args.sync:
        return sync()
    if args.check:
        return check()
    print(read_version())
    return 0


if __name__ == "__main__":
    sys.exit(main())
