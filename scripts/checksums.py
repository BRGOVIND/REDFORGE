#!/usr/bin/env python3
"""SHA-256 checksums for release artifacts.

Emits the standard ``sha256sum`` format (``<hex>  <name>``) so users can verify a
download with:

    sha256sum -c SHA256SUMS.txt          # Linux
    shasum -a 256 -c SHA256SUMS.txt      # macOS
    certutil -hashfile <file> SHA256     # Windows

Only basenames are recorded, so the file verifies from the directory holding the
artifacts. Used by ``build_release.py`` and by the release workflow (which reruns
it across the installer artifacts built on other runners).

Usage:
    python scripts/checksums.py <dir-or-file> [...] [-o SHA256SUMS.txt]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

_CHUNK = 1 << 20
# Never checksum a checksum file, and skip the unpacked staging tree.
_SKIP_SUFFIXES = {".txt", ".sha256"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(p for p in target.iterdir() if p.is_file())
        elif target.is_file():
            files.append(target)
    return sorted(
        (f for f in files if f.suffix.lower() not in _SKIP_SUFFIXES),
        key=lambda p: p.name,
    )


def write_sums(artifacts: list[Path], out: Path) -> Path:
    lines = [f"{sha256(a)}  {a.name}" for a in collect(artifacts)]
    out.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("SHA256SUMS.txt"))
    args = ap.parse_args()

    artifacts = collect(args.targets)
    if not artifacts:
        print("no artifacts to checksum", file=sys.stderr)
        return 1
    write_sums(artifacts, args.out)
    for line in args.out.read_text(encoding="utf-8").splitlines():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
