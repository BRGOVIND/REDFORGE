#!/usr/bin/env python3
"""Fail the release unless every expected asset is present and non-trivial.

A partially-successful build matrix must never produce a published release that
silently omits macOS, or that ships installers with no auto-update feed. This is
the last gate before `softprops/action-gh-release` runs.

Checks, per asset:
  • it exists,
  • it is larger than a floor size (catches truncated / stub / 0-byte uploads).

Usage:
    python scripts/verify_release_assets.py dist --version 2.0.0
    python scripts/verify_release_assets.py dist --version 2.0.0 --skip-payload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

MB = 1024 * 1024

# (filename template, minimum plausible size, human label)
INSTALLERS: list[tuple[str, int, str]] = [
    ("RedForge-v{v}-Setup.exe",      20 * MB, "Windows installer"),
    ("RedForge-v{v}-Portable.zip",   20 * MB, "Windows portable"),
    ("RedForge-v{v}-x64.dmg",        20 * MB, "macOS (Intel)"),
    ("RedForge-v{v}-arm64.dmg",      20 * MB, "macOS (Apple Silicon)"),
    ("RedForge-v{v}-x64.AppImage",   20 * MB, "Linux AppImage"),
    ("RedForge-v{v}-amd64.deb",      20 * MB, "Linux .deb"),
]

# electron-updater reads these; without them installed apps never see updates.
UPDATE_FEEDS: list[tuple[str, int, str]] = [
    ("latest.yml",       64, "Windows update feed"),
    ("latest-mac.yml",   64, "macOS update feed"),
    ("latest-linux.yml", 64, "Linux update feed"),
]

PAYLOAD: list[tuple[str, int, str]] = [
    ("redforge-{v}.zip",    1 * MB, "source payload (zip)"),
    ("redforge-{v}.tar.gz", 1 * MB, "source payload (tar.gz)"),
]


def check(directory: Path, items: list[tuple[str, int, str]], version: str) -> list[str]:
    problems: list[str] = []
    for template, floor, label in items:
        name = template.format(v=version)
        path = directory / name
        if not path.is_file():
            problems.append(f"MISSING  {name}  ({label})")
            continue
        size = path.stat().st_size
        if size < floor:
            problems.append(
                f"TOO SMALL {name} — {size:,} bytes < {floor:,} ({label}); "
                "likely a truncated or stub upload"
            )
        else:
            print(f"  ok  {name:<44} {size / MB:>8.1f} MB  {label}")
    return problems


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

    print(f"verifying release assets in {directory} for v{args.version}\n")
    problems = check(directory, INSTALLERS, args.version)
    problems += check(directory, UPDATE_FEEDS, args.version)
    if not args.skip_payload:
        problems += check(directory, PAYLOAD, args.version)

    if problems:
        print(f"\n✗ {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nPresent in the directory:", file=sys.stderr)
        for f in sorted(directory.iterdir()):
            if f.is_file():
                print(f"    {f.name} ({f.stat().st_size:,} bytes)", file=sys.stderr)
        return 1

    print("\n✓ release asset set is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
