#!/usr/bin/env python3
"""Static validation of the electron-builder configuration.

Exists because a broken desktop config only surfaces *during packaging*, on the
platform it breaks — a macOS-only icon failure costs a full CI matrix run to
discover. This catches the whole class in a second, on every push.

What it checks:

  1. **Every icon path resolves.** Including the trap that broke the macOS build:
     `fileAssociations[].icon` is a PLATFORM-SHARED key, and electron-builder
     rewrites its extension per platform
     (builder-util `getPlatformIconFileName`: `.ico` -> `.icns` on macOS). So a
     Windows-only `.ico` there silently becomes a non-existent `.icns`.
  2. **extraResources sources exist** — a missing one ships an app with no backend.
  3. **buildResources files exist** (entitlements, icon).
  4. **artifactName patterns agree with the release gate.** `package.json` and
     `verify_release_assets.py` encode the same filenames in two places; drift
     means a green build that publishes nothing the website can link to.

Usage:
    python scripts/verify_desktop_config.py
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):  # UTF-8 safe on cp1252 consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = ROOT / "desktop"
PKG = DESKTOP / "package.json"

# Keys whose value electron-builder rewrites per platform, so BOTH the .ico and
# the .icns form must resolve. Anything listed here must not live in a
# platform-specific directory.
# The single source of truth for artifact filenames (ports electron-builder's
# per-target arch convention: x86_64 for AppImage, amd64 for deb, ...).
sys.path.insert(0, str(ROOT / "scripts"))
from artifact_names import (  # noqa: E402
    UPDATE_FEEDS,
    installer_names,
    payload_names,
    render as _render,
)

SHARED_ICON_KEYS = ("fileAssociations",)


def platform_icon_name(value: str, is_mac: bool) -> str:
    """Port of builder-util's getPlatformIconFileName (util.js)."""
    if "." not in value:
        return f"{value}.{'icns' if is_mac else 'ico'}"
    return value.replace(".ico" if is_mac else ".icns",
                         ".icns" if is_mac else ".ico")


def check_icons(build: dict, problems: list[str]) -> None:
    # -- platform-specific icons: only their own platform's file must exist ----
    for key, expect_ext in (("win", ".ico"), ("mac", None), ("linux", ".png")):
        section = build.get(key) or {}
        icon = section.get("icon")
        if not icon:
            continue
        path = (DESKTOP / icon).resolve()
        if not path.is_file():
            problems.append(f"build.{key}.icon -> missing file: {icon}")
        elif expect_ext and path.suffix.lower() != expect_ext:
            problems.append(f"build.{key}.icon should be {expect_ext}, got {path.suffix}: {icon}")

    for key in ("installerIcon", "uninstallerIcon"):
        icon = (build.get("nsis") or {}).get(key)
        if icon and not (DESKTOP / icon).resolve().is_file():
            problems.append(f"build.nsis.{key} -> missing file: {icon}")

    # -- platform-SHARED icons: every platform's rewritten form must exist -----
    for key in SHARED_ICON_KEYS:
        for i, entry in enumerate(build.get(key) or []):
            icon = entry.get("icon")
            if not icon:
                continue  # inherits the app icon — always safe
            for is_mac, label in ((True, "macOS"), (False, "Windows")):
                resolved = platform_icon_name(icon, is_mac)
                if not (DESKTOP / resolved).resolve().is_file():
                    problems.append(
                        f"build.{key}[{i}].icon is platform-shared: on {label} "
                        f"electron-builder resolves it to '{resolved}', which does not exist. "
                        f"Either drop the icon (it then inherits the app icon) or place both "
                        f".ico and .icns under desktop/build/ with the same basename."
                    )


def check_resources(build: dict, problems: list[str]) -> None:
    for i, res in enumerate(build.get("extraResources") or []):
        src = res.get("from")
        if not src:
            continue
        path = (DESKTOP / src).resolve()
        if not path.exists():
            problems.append(
                f"build.extraResources[{i}].from -> missing: {src} "
                "(run desktop/scripts/stage-backend.py first)"
            )

    mac = build.get("mac") or {}
    for key in ("entitlements", "entitlementsInherit"):
        val = mac.get(key)
        if val and not (DESKTOP / val).resolve().is_file():
            problems.append(f"build.mac.{key} -> missing file: {val}")


def check_artifact_names(build: dict, problems: list[str]) -> None:
    """The names package.json produces must be the names the gate expects.

    Both sides now derive from scripts/artifact_names.py, so this is a guard
    against someone reintroducing a hand-written list rather than a diff of two.
    """
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    produced = {name for name, _ in installer_names(build, version)}
    if not produced:
        problems.append("no installer artifact names could be derived from package.json")


def _expected_artifacts(build: dict, version: str) -> set[str]:
    """Every file the three matrix runners produce, derived from the config."""
    names = {name for name, _ in installer_names(build, version)}
    names |= {feed for feed, _ in UPDATE_FEEDS}
    names |= {name for name, _ in payload_names(version)}
    # Delta-update blockmaps. Which targets emit one is an electron-builder
    # internal, so only the NSIS installer's is asserted — that one is confirmed
    # empirically and is enough to keep the `*.blockmap` glob from being dead.
    names.add(_render(build["nsis"]["artifactName"], version, "x64", "exe") + ".blockmap")
    return names


def _globs_from_block(text: str, header: str) -> list[str]:
    """Pull a YAML literal block's lines without needing a YAML parser.

    Stdlib-only on purpose: this runs in the lint job, which installs nothing.
    """
    idx = text.find(header)
    if idx == -1:
        return []
    lines = text[idx:].splitlines()[1:]
    base_indent = None
    out: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if base_indent is None:
            base_indent = indent
        if indent < base_indent or line.lstrip().startswith(("- ", "#")) and indent < base_indent:
            break
        if indent < base_indent:
            break
        stripped = line.strip()
        # A new YAML key ends the block.
        if re.match(r"^[a-zA-Z_-]+:\s*$", stripped) or re.match(r"^[a-zA-Z_-]+:\s+\S", stripped):
            break
        out.append(stripped)
    return out


def check_workflow_globs(build: dict, problems: list[str]) -> None:
    """The release only contains what the workflow's globs match.

    A renamed artifact that no glob matches would be built, uploaded as a CI
    artifact, and then silently missing from the GitHub Release — or, with
    fail_on_unmatched_files, would fail the release at the very last step.
    """
    workflow = ROOT / ".github" / "workflows" / "release.yml"
    if not workflow.is_file():
        problems.append(".github/workflows/release.yml: missing")
        return
    text = workflow.read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    expected = _expected_artifacts(build, version)

    raw = _globs_from_block(text, "          files: |")
    globs = [g.replace("dist/", "").replace("${{ needs.verify.outputs.version }}", version)
             for g in raw if g and not g.startswith("#")]
    if not globs:
        problems.append("release.yml: could not read the release `files:` globs")
        return

    # SHA256SUMS is generated by the publish job, not by a packager.
    matched: set[str] = set()
    for glob in globs:
        matched |= {n for n in expected if fnmatch.fnmatch(n, glob)}

    for name in sorted(expected - matched):
        problems.append(
            f"release.yml publishes no glob matching '{name}' — it would be built "
            "but never attached to the GitHub Release"
        )

    for glob in globs:
        if glob in ("SHA256SUMS.txt",):
            continue
        if not any(fnmatch.fnmatch(n, glob) for n in expected):
            problems.append(
                f"release.yml glob 'dist/{glob}' matches none of the produced artifacts "
                "— with fail_on_unmatched_files: true this fails the release"
            )


def check_publish(build: dict, problems: list[str]) -> None:
    publish = build.get("publish") or []
    if not publish:
        problems.append("build.publish is empty — no auto-update feed would be generated")
        return
    for i, p in enumerate(publish):
        if p.get("provider") == "github" and not (p.get("owner") and p.get("repo")):
            problems.append(f"build.publish[{i}] github provider needs owner + repo")


def main() -> int:
    if not PKG.is_file():
        print(f"missing {PKG}", file=sys.stderr)
        return 1
    build = json.loads(PKG.read_text(encoding="utf-8-sig"))["build"]

    problems: list[str] = []
    check_icons(build, problems)
    check_resources(build, problems)
    check_artifact_names(build, problems)
    check_workflow_globs(build, problems)
    check_publish(build, problems)

    # extraResources is only populated after staging; don't fail a plain lint run.
    staged = (DESKTOP / "resources" / "backend").exists()
    if not staged:
        problems = [p for p in problems if "extraResources" not in p]
        print("note: desktop/resources not staged — skipping extraResources checks")

    if problems:
        print(f"\n{len(problems)} problem(s) in the electron-builder configuration:\n",
              file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("OK: electron-builder configuration is valid "
          "(icons resolve on every platform, artifact names match the release gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
