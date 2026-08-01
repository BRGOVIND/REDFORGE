#!/usr/bin/env python3
"""Fail the release unless every expected asset is present and genuinely intact.

A partially-successful build matrix must never produce a published release that
silently omits macOS, or that ships installers with no auto-update feed. This is
the last gate before `softprops/action-gh-release` runs.

**No arbitrary size thresholds.** An earlier version required every asset to
exceed a hand-picked floor, which rejected a perfectly valid 992 KB source
archive purely because the repository compresses well. Archive size is a
property of the content, not of correctness, so it proves nothing. Each asset is
instead validated by what it actually is:

  | asset          | check                                                     |
  |----------------|-----------------------------------------------------------|
  | any            | exists, is a regular file, is readable, is not empty      |
  | .zip           | opens, central directory parses, contains >= 1 entry      |
  | .tar.gz        | gzip stream decodes, contains >= 1 member                 |
  | .exe           | starts with the `MZ` PE signature                         |
  | .AppImage      | starts with the ELF signature                             |
  | .deb           | starts with the `!<arch>` ar signature                    |
  | .dmg           | non-empty (format is opaque without macOS tooling)        |
  | latest*.yml    | parses, declares the release version, and every file it   |
  |                | references is actually present in the directory           |

These are *stronger* than a size floor, not weaker. A truncated ZIP fails
because its central directory lives at the end of the file; a truncated tar.gz
fails its gzip CRC; a stub `.exe` fails its magic bytes. The update-feed check
additionally catches a feed that points at an asset the release does not carry —
which a size check could never detect.

Usage:
    python scripts/verify_release_assets.py dist --version 2.0.2
    python scripts/verify_release_assets.py dist --version 2.0.2 --skip-payload
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_names import UPDATE_FEEDS, installer_names, payload_names  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
KB = 1024
MB = 1024 * 1024

# Magic bytes that prove a file is the kind of binary it claims to be. Cheap,
# exact, and independent of how large the artifact happens to be.
MAGIC: dict[str, tuple[bytes, str]] = {
    ".exe": (b"MZ", "PE executable"),
    ".appimage": (b"\x7fELF", "ELF binary"),
    ".deb": (b"!<arch>", "ar archive"),
}


def _human(size: int) -> str:
    return f"{size / MB:.1f} MB" if size >= MB else f"{size / KB:.0f} KB"


# --- per-type integrity ------------------------------------------------------


def _check_zip(path: Path) -> str | None:
    """A truncated ZIP cannot be opened: the central directory is at the end."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except (zipfile.BadZipFile, OSError) as exc:
        return f"not a readable ZIP ({exc})"
    if not names:
        return "ZIP contains no entries"
    return None


def _check_targz(path: Path) -> str | None:
    """Decodes the gzip stream (catching truncation) and requires >= 1 member."""
    try:
        with tarfile.open(path, "r:gz") as tf:
            first = tf.next()
            if first is None:
                return "tar.gz contains no members"
            # Walk the rest so a truncated stream raises here rather than later.
            count = 1
            while tf.next() is not None:
                count += 1
    except (tarfile.TarError, gzip.BadGzipFile, EOFError, OSError) as exc:
        return f"not a readable tar.gz ({exc})"
    return None


def _check_magic(path: Path, suffix: str) -> str | None:
    expected, label = MAGIC[suffix]
    try:
        with path.open("rb") as fh:
            head = fh.read(len(expected))
    except OSError as exc:
        return f"unreadable ({exc})"
    if head != expected:
        return f"does not start with the {label} signature (got {head!r})"
    return None


def _check_feed(path: Path, version: str, directory: Path) -> list[str]:
    """An update feed must name this release AND reference assets that exist.

    A feed pointing at a missing file is the failure mode that silently breaks
    auto-update for everyone — no size check can see it.
    """
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{path.name}: unreadable ({exc})"]

    match = re.search(r"^version:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        problems.append(f"{path.name}: no `version:` key — not a valid update feed")
    elif match.group(1).strip().strip("'\"") != version:
        problems.append(
            f"{path.name}: declares version {match.group(1)!r}, expected {version!r} "
            "— a stale feed would offer the wrong build"
        )

    referenced = set(re.findall(r"^\s*-?\s*url:\s*(\S+)\s*$", text, re.MULTILINE))
    for url in sorted(referenced):
        name = url.strip().strip("'\"")
        # Feeds reference plain filenames, not URLs, in electron-builder output.
        if "/" in name:
            continue
        if not (directory / name).is_file():
            problems.append(
                f"{path.name}: references '{name}', which is not in the release "
                "— auto-update would 404"
            )
    if not referenced:
        problems.append(f"{path.name}: references no files — auto-update would find nothing")
    return problems


def check_asset(directory: Path, name: str, label: str) -> list[str]:
    """Existence + readability + non-empty + format integrity."""
    path = directory / name
    if not path.exists():
        return [f"MISSING   {name}  ({label})"]
    if not path.is_file():
        return [f"NOT A FILE {name}  ({label})"]
    try:
        size = path.stat().st_size
    except OSError as exc:
        return [f"UNREADABLE {name}  ({label}): {exc}"]
    if size == 0:
        return [f"EMPTY     {name}  ({label}) — 0 bytes"]

    suffix = "".join(path.suffixes[-2:]).lower()
    single = path.suffix.lower()
    detail = ""

    if suffix.endswith(".tar.gz"):
        error = _check_targz(path)
        detail = "tar.gz ok"
    elif single == ".zip":
        error = _check_zip(path)
        detail = "zip ok"
    elif single in MAGIC:
        error = _check_magic(path, single)
        detail = f"{MAGIC[single][1]} ok"
    else:
        # .dmg and anything else: readability + non-empty is all we can assert
        # without platform tooling. Prove it is actually readable end-to-end.
        try:
            with path.open("rb") as fh:
                fh.seek(-1, 2)
                fh.read(1)
            error = None
        except OSError as exc:
            error = f"unreadable ({exc})"
        detail = "readable"

    if error:
        return [f"CORRUPT   {name}  ({label}): {error}"]
    print(f"  ok  {name:<44} {_human(size):>9}  {detail}")
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("directory", type=Path, help="directory holding the collected assets")
    ap.add_argument("--version", required=True)
    ap.add_argument("--skip-payload", action="store_true",
                    help="don't require the source .zip/.tar.gz")
    args = ap.parse_args()

    directory: Path = args.directory
    if not directory.is_dir():
        print(f"✗ not a directory: {directory}", file=sys.stderr)
        return 1

    build = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8-sig"))["build"]
    version: str = args.version

    print(f"verifying release assets in {directory} for v{version}\n")
    problems: list[str] = []

    for name, label in installer_names(build, version):
        problems += check_asset(directory, name, label)

    for name, label in UPDATE_FEEDS:
        found = check_asset(directory, name, label)
        problems += found
        if not found:
            problems += _check_feed(directory / name, version, directory)

    if not args.skip_payload:
        for name, label in payload_names(version):
            problems += check_asset(directory, name, label)

    if problems:
        print(f"\n✗ {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nPresent in the directory:", file=sys.stderr)
        for f in sorted(directory.iterdir()):
            if f.is_file():
                print(f"    {f.name} ({f.stat().st_size:,} bytes)", file=sys.stderr)
        return 1

    print("\n✓ release asset set is complete and intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
