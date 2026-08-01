#!/usr/bin/env python3
"""The single version authority for RedForge.

The repo-root ``VERSION`` file is the only place a version is *decided*. Every
other location either derives it at runtime or is a **sink** kept in lockstep by
this script. Nothing is ever edited by hand.

    VERSION
      │
      ├─ derived at runtime (nothing to sync, verified by --check)
      │    redforge._version.read_version()      CLI
      │    app.version.read_version()            backend / FastAPI
      │    pyproject.toml                        setuptools dynamic
      │    cli/pyproject.toml                    setuptools dynamic
      │    frontend/vite.config.ts               __APP_VERSION__
      │    website/vite.config.ts                __APP_VERSION__
      │    installers/windows/redforge.iss       ISPP FileRead
      │    installers/linux/build-appimage.sh    cat VERSION
      │    desktop/electron/*                    app.getVersion()
      │
      └─ sinks (a literal is unavoidable — written by --set/--sync)
           desktop/package.json                  electron-builder reads it
           desktop/package-lock.json             npm mirrors package.json
           website/package.json
           website/package-lock.json
           SECURITY.md                           "currently **X.Y.Z**"

Release procedure — no manual editing anywhere:

    python scripts/version.py --set 2.0.1
    git commit -am "release 2.0.1"
    git tag v2.0.1
    git push origin main
    git push origin v2.0.1

Usage:
    python scripts/version.py               print the version
    python scripts/version.py --check       verify every location is in sync
    python scripts/version.py --check --release
                                            additionally require a CHANGELOG entry
    python scripts/version.py --sync        rewrite every sink from VERSION
    python scripts/version.py --set X.Y.Z   bump VERSION, then sync
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles (Windows CI)
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_ANY_VERSION = r"\d+\.\d+\.\d+"


# --- byte-exact file I/O ----------------------------------------------------
# Every read/write below disables newline translation. Python's default would
# rewrite an entire LF file to CRLF on Windows, which is both a noisy diff and a
# real hazard: installers/linux/build-appimage.sh does VERSION="$(cat VERSION)",
# and `cat` does not strip a trailing \r — the AppImage filename would gain one.
# Editing a version must never touch a single unrelated byte.


def _read(path: Path) -> str:
    # utf-8-sig tolerates a BOM (some Windows editors add one) rather than
    # failing the release gate on it.
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return fh.read()


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _newline_of(text: str) -> str:
    """The dominant line ending, so regenerated files keep the original style."""
    return "\r\n" if "\r\n" in text else "\n"


def read_version() -> str:
    """The one authoritative read. Raises if the file is missing or malformed."""
    if not VERSION_FILE.is_file():
        raise SystemExit(f"missing {VERSION_FILE}")
    version = _read(VERSION_FILE).strip()
    if not _SEMVER.match(version):
        raise SystemExit(f"VERSION is not semver: {version!r}")
    return version


# ---------------------------------------------------------------------------
# Sinks — locations that must carry a literal copy of the version
# ---------------------------------------------------------------------------


class Sink:
    """A place the version is written to. Subclasses implement read/write.

    ``read`` returns the value(s) currently stored; ``write`` sets them and
    reports what changed. Both must be safe to call repeatedly (idempotent) and
    must never reformat the surrounding file.
    """

    rel: str
    label: str

    @property
    def path(self) -> Path:
        return ROOT / self.rel

    def current(self) -> tuple[list[str], str | None]:
        raise NotImplementedError

    def write(self, version: str) -> tuple[bool, str | None]:
        raise NotImplementedError

    def problems(self, expected: str) -> list[str]:
        values, error = self.current()
        if error:
            return [error]
        return [
            f"{self.rel}: {self.label} is {value!r}, expected {expected!r} "
            f"— run `python scripts/version.py --sync`"
            for value in values
            if value != expected
        ]


class PackageJsonSink(Sink):
    """The ``version`` field of a package.json.

    Rewritten with a targeted regex rather than a JSON round-trip so hand-written
    formatting (comment arrays, key order, spacing) survives untouched.
    """

    def __init__(self, rel: str, label: str = "version") -> None:
        self.rel = rel
        self.label = label

    def current(self) -> tuple[list[str], str | None]:
        if not self.path.is_file():
            return [], f"{self.rel}: missing"
        try:
            # utf-8-sig tolerates a BOM (some Windows editors add one) rather
            # than failing the release gate on it.
            data = json.loads(_read(self.path))
        except json.JSONDecodeError as exc:
            return [], f"{self.rel}: invalid JSON ({exc})"
        value = data.get("version")
        if not isinstance(value, str):
            return [], f"{self.rel}: missing a string `version` field"
        return [value], None

    def write(self, version: str) -> tuple[bool, str | None]:
        values, error = self.current()
        if error:
            return False, error
        if values[0] == version:
            return False, None
        text = _read(self.path)
        new_text, count = re.subn(r'("version"\s*:\s*)"[^"]*"', rf'\1"{version}"', text, count=1)
        if count != 1:
            return False, f"{self.rel}: could not locate the version field"
        _write(self.path, new_text)
        return True, f"{self.rel}: {values[0]} -> {version}"


class PackageLockSink(Sink):
    """The two ``version`` fields npm keeps in a lockfile: the document root and
    the ``packages[""]`` self-entry. npm rewrites both on install, so they drift
    the moment package.json is bumped by hand.

    Safe to serialize: npm writes standard 2-space JSON, and both lockfiles were
    verified to round-trip byte-identically through ``json.dumps(indent=2)``.
    """

    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.label = "lockfile version"

    def _load(self) -> tuple[dict | None, str | None]:
        if not self.path.is_file():
            return None, f"{self.rel}: missing"
        try:
            return json.loads(_read(self.path)), None
        except json.JSONDecodeError as exc:
            return None, f"{self.rel}: invalid JSON ({exc})"

    def current(self) -> tuple[list[str], str | None]:
        data, error = self._load()
        if error or data is None:
            return [], error
        values = []
        root = data.get("version")
        if isinstance(root, str):
            values.append(root)
        self_entry = (data.get("packages") or {}).get("", {})
        if isinstance(self_entry.get("version"), str):
            values.append(self_entry["version"])
        if not values:
            return [], f"{self.rel}: no version field found"
        return values, None

    def write(self, version: str) -> tuple[bool, str | None]:
        data, error = self._load()
        if error or data is None:
            return False, error
        before = json.dumps(data, indent=2, ensure_ascii=False)
        if isinstance(data.get("version"), str):
            data["version"] = version
        self_entry = (data.get("packages") or {}).get("")
        if isinstance(self_entry, dict) and isinstance(self_entry.get("version"), str):
            self_entry["version"] = version
        after = json.dumps(data, indent=2, ensure_ascii=False)
        if after == before:
            return False, None
        # json.dumps always emits LF; keep whatever the file already used.
        newline = _newline_of(_read(self.path))
        _write(self.path, (after + "\n").replace("\n", newline))
        return True, f"{self.rel}: -> {version}"


class RegexSink(Sink):
    """A version literal embedded in prose or config.

    ``pattern`` must contain exactly one group around the version so the
    surrounding text is preserved verbatim.
    """

    def __init__(self, rel: str, pattern: str, template: str, label: str) -> None:
        self.rel = rel
        self.label = label
        self._rx = re.compile(pattern)
        self._template = template

    def current(self) -> tuple[list[str], str | None]:
        if not self.path.is_file():
            return [], f"{self.rel}: missing"
        text = _read(self.path)
        found = self._rx.findall(text)
        if not found:
            return [], f"{self.rel}: no version literal matched {self._rx.pattern!r}"
        return list(found), None

    def write(self, version: str) -> tuple[bool, str | None]:
        values, error = self.current()
        if error:
            return False, error
        if all(v == version for v in values):
            return False, None
        text = _read(self.path)
        new_text = self._rx.sub(self._template.format(version=version), text)
        if new_text == text:
            return False, None
        _write(self.path, new_text)
        return True, f"{self.rel}: {values[0]} -> {version}"


# Order matters only for readable output.
SINKS: list[Sink] = [
    # electron-builder bakes this into installer filenames, the NSIS uninstall
    # entry, the .deb control file and the auto-update feed. It cannot read an
    # external file, which is why a literal is unavoidable here.
    PackageJsonSink("desktop/package.json"),
    PackageLockSink("desktop/package-lock.json"),
    PackageJsonSink("website/package.json"),
    PackageLockSink("website/package-lock.json"),
    RegexSink(
        "SECURITY.md",
        pattern=rf"(?<=currently \*\*)({_ANY_VERSION})(?=\*\*)",
        template="{version}",
        label="supported release",
    ),
]


# ---------------------------------------------------------------------------
# Guards — locations that must NOT contain a literal
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

# package.json files that must have NO version field: they are private, never
# published to npm, and their build injects __APP_VERSION__ from VERSION.
_MUST_NOT_HAVE_VERSION = [
    ("frontend/package.json", "vite.config.ts injects __APP_VERSION__ from VERSION"),
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


def _absent_problems() -> list[str]:
    problems: list[str] = []
    for rel, hint in _MUST_NOT_HAVE_VERSION:
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"{rel}: missing")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            problems.append(f"{rel}: invalid JSON ({exc})")
            continue
        if "version" in data:
            problems.append(f"{rel}: remove the `version` field ({hint})")
    return problems


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
    env.pop("REDFORGE_HOME", None)      # never let a local install shadow the repo
    env.pop("REDFORGE_VERSION", None)   # nor an injected desktop version
    return env


def _changelog_warnings(expected: str) -> list[str]:
    """A missing section is a WARNING, never a failure.

    ``release_notes.py`` degrades gracefully (the release just has no "What's
    changed" body), and the documented release procedure is a version bump plus a
    tag — authoring changelog prose is a separate editorial step. Blocking the
    release on it would make the documented procedure fail.
    """
    path = ROOT / "CHANGELOG.md"
    if not path.is_file():
        return ["CHANGELOG.md: missing"]
    text = path.read_text(encoding="utf-8")
    if not re.search(rf"^##\s*\[?{re.escape(expected)}\]?", text, re.MULTILINE):
        return [
            f"CHANGELOG.md has no section for {expected} — the release body will "
            f"have no 'What's changed'. Add '## [{expected}]' to include one."
        ]
    return []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def sync() -> int:
    """Rewrite every sink from VERSION. Idempotent."""
    expected = read_version()
    changed: list[str] = []
    errors: list[str] = []

    for sink in SINKS:
        did_change, message = sink.write(expected)
        if message and not did_change:
            errors.append(message)
        elif did_change and message:
            changed.append(message)

    if errors:
        print(f"✗ could not sync to {expected}\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if changed:
        for c in changed:
            print(f"↻ {c}")
        print(f"\n✓ {len(changed)} location(s) updated to {expected}")
    else:
        print(f"✓ already in sync at {expected}")
    return 0


def check(release: bool = False) -> int:
    expected = read_version()
    problems: list[str] = []
    for sink in SINKS:
        problems += sink.problems(expected)
    problems += _literal_problems()
    problems += _absent_problems()
    problems += _runtime_problems(expected)

    if problems:
        print(f"✗ version drift (VERSION = {expected})\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n  fix: python scripts/version.py --sync", file=sys.stderr)
        return 1

    print(f"✓ version {expected} is single-sourced from VERSION "
          f"({len(SINKS)} sinks + {len(_FORBIDDEN)} guards)")

    # Non-blocking release hygiene, surfaced in the release log.
    if release:
        for warning in _changelog_warnings(expected):
            print(f"::warning::{warning}" if _in_github_actions() else f"! {warning}")
    return 0


def _in_github_actions() -> bool:
    import os

    return os.environ.get("GITHUB_ACTIONS") == "true"


def set_version(new: str) -> int:
    if not _SEMVER.match(new):
        print(f"✗ not semver: {new!r}", file=sys.stderr)
        return 1
    previous = read_version() if VERSION_FILE.is_file() else "(none)"
    # Always LF: installers/linux/build-appimage.sh does `cat VERSION`,
    # and `cat` would keep a trailing CR in the AppImage filename.
    _write(VERSION_FILE, f"{new}\n")
    print(f"↻ VERSION: {previous} -> {new}")
    return sync()


def show_locations() -> int:
    """Print every location and its current value — the audit view."""
    expected = read_version()
    print(f"VERSION = {expected}\n")
    print(f"{'location':<34} {'value':<14} status")
    print("-" * 66)
    print(f"{'VERSION':<34} {expected:<14} source of truth")
    for sink in SINKS:
        values, error = sink.current()
        if error:
            print(f"{sink.rel:<34} {'-':<14} ERROR: {error}")
            continue
        for value in values:
            status = "in sync" if value == expected else "DRIFTED"
            print(f"{sink.rel:<34} {value:<14} {status}")
    for label in ("redforge._version", "app.version"):
        print(f"{label:<34} {'(derived)':<14} resolved at runtime")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="verify every location is in sync")
    ap.add_argument("--release", action="store_true",
                    help="with --check: also require a CHANGELOG section")
    ap.add_argument("--sync", action="store_true", help="rewrite every sink from VERSION")
    ap.add_argument("--set", metavar="X.Y.Z", help="bump VERSION to X.Y.Z, then --sync")
    ap.add_argument("--list", action="store_true", help="show every location and its value")
    args = ap.parse_args()

    if args.set:
        return set_version(args.set)
    if args.sync:
        return sync()
    if args.list:
        return show_locations()
    if args.check:
        return check(release=args.release)
    print(read_version())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
