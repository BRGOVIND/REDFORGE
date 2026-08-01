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


def _render(pattern: str, version: str, arch: str, ext: str) -> str:
    return (pattern.replace("${version}", version)
                   .replace("${arch}", arch)
                   .replace("${ext}", ext))


def check_artifact_names(build: dict, problems: list[str]) -> None:
    """The names package.json produces must be the names the gate expects."""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    produced = {
        _render(build["nsis"]["artifactName"], version, "x64", "exe"),
        _render(build["win"]["artifactName"], version, "x64", "zip"),
        _render(build["dmg"]["artifactName"], version, "x64", "dmg"),
        _render(build["dmg"]["artifactName"], version, "arm64", "dmg"),
        _render(build["mac"]["artifactName"], version, "x64", "zip"),
        _render(build["mac"]["artifactName"], version, "arm64", "zip"),
        _render(build["appImage"]["artifactName"], version, "x64", "AppImage"),
        _render(build["deb"]["artifactName"], version, "amd64", "deb"),
    }

    sys.path.insert(0, str(ROOT / "scripts"))
    from verify_release_assets import INSTALLERS  # noqa: E402

    expected = {tmpl.format(v=version) for tmpl, _, _ in INSTALLERS}
    missing = expected - produced
    extra = produced - expected
    for name in sorted(missing):
        problems.append(
            f"verify_release_assets.py expects '{name}', but no artifactName in "
            "package.json produces it"
        )
    for name in sorted(extra):
        problems.append(
            f"package.json produces '{name}', but verify_release_assets.py does not "
            "require it (it would not be gated)"
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
