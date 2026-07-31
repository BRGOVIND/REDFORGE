#!/usr/bin/env python3
"""Generate GitHub Release notes for the current VERSION.

Notes are *derived*, never hand-maintained per release:

    CHANGELOG.md  "## [X.Y.Z]" section   → what changed
    VERSION + the installer naming scheme → the download table
    SHA256SUMS.txt (if present)           → verification block

Usage:
    python scripts/release_notes.py                  # print to stdout
    python scripts/release_notes.py -o NOTES.md      # write to a file
    python scripts/release_notes.py --checksums dist/SHA256SUMS.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from version import read_version  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/BRGOVIND/REDFORGE"

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def changelog_section(version: str) -> str:
    """The body under `## [version]`, up to the next `## ` heading."""
    if not CHANGELOG.is_file():
        return ""
    text = CHANGELOG.read_text(encoding="utf-8")
    # Accept "## [2.0.0]", "## [2.0.0] - 2026-01-01", or "## 2.0.0".
    pattern = rf"^##\s*\[?{re.escape(version)}\]?.*?$"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end():]
    nxt = re.search(r"^##\s", rest, re.MULTILINE)
    return (rest[: nxt.start()] if nxt else rest).strip()


def downloads_table(version: str) -> str:
    """Mirrors desktop/package.json artifactName patterns exactly."""
    rows = [
        ("Windows", "Installer", f"RedForge-v{version}-Setup.exe"),
        ("Windows", "Portable (no install)", f"RedForge-v{version}-Portable.zip"),
        ("macOS", "Apple Silicon", f"RedForge-v{version}-arm64.dmg"),
        ("macOS", "Intel", f"RedForge-v{version}-x64.dmg"),
        ("Linux", "AppImage", f"RedForge-v{version}-x64.AppImage"),
        ("Linux", "Debian / Ubuntu", f"RedForge-v{version}-amd64.deb"),
    ]
    base = f"{REPO}/releases/download/v{version}"
    out = ["| Platform | Build | Download |", "| --- | --- | --- |"]
    for os_name, kind, filename in rows:
        out.append(f"| {os_name} | {kind} | [`{filename}`]({base}/{filename}) |")
    return "\n".join(out)


def verification(checksums: Path | None) -> str:
    if not checksums or not checksums.is_file():
        return (
            "Every asset is listed in `SHA256SUMS.txt`, attached to this release.\n\n"
            "```bash\n"
            "# macOS / Linux\n"
            "shasum -a 256 -c SHA256SUMS.txt --ignore-missing\n"
            "```\n"
        )
    lines = [ln for ln in checksums.read_text(encoding="utf-8").splitlines() if ln.strip()]
    body = "\n".join(lines)
    return (
        "```\n" + body + "\n```\n\n"
        "```bash\n"
        "shasum -a 256 -c SHA256SUMS.txt --ignore-missing\n"
        "```\n"
    )


def build(version: str, checksums: Path | None) -> str:
    changes = changelog_section(version)
    parts = [
        f"# RedForge v{version}",
        "",
        "The local AI engineering platform — build, evaluate and manage AI models "
        "entirely on your own hardware. No account, no cloud, no telemetry.",
        "",
        "## Download",
        "",
        downloads_table(version),
        "",
        "Not sure which to pick? The [download page](https://redforge.site#download) "
        "detects your platform automatically.",
        "",
        "## Install",
        "",
        "- **Windows** — run the `Setup.exe` and launch RedForge from the Start menu. "
        "Portable users: unzip and run `RedForge.exe`; all data stays in the folder.",
        "- **macOS** — open the `.dmg` and drag RedForge to Applications.",
        "- **Linux** — `chmod +x` the AppImage and run it, or "
        "`sudo apt install ./RedForge-v" + version + "-amd64.deb`.",
        "",
        "Nothing else is required: the backend is bundled and starts automatically. "
        "Python is **not** needed.",
        "",
    ]
    if changes:
        parts += ["## What's changed", "", changes, ""]
    parts += [
        "## Verify your download",
        "",
        verification(checksums),
        "## Notes",
        "",
        "- Real GPU fine-tuning is **Experimental** and needs a CUDA GPU plus the "
        "Unsloth stack; without it, Training runs a clearly-labelled simulation.",
        "- RedForge is local-first and unauthenticated by design — do not expose it "
        "to an untrusted network.",
        "",
        f"**Full changelog:** {REPO}/blob/v{version}/CHANGELOG.md",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", type=Path, help="write notes here instead of stdout")
    ap.add_argument("--checksums", type=Path, help="SHA256SUMS.txt to inline")
    ap.add_argument("--version", help="override the version (defaults to the VERSION file)")
    args = ap.parse_args()

    version = args.version or read_version()
    notes = build(version, args.checksums)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(notes, encoding="utf-8")
        print(f"wrote {args.output} ({len(notes)} bytes)")
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
