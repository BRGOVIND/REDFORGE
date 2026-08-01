#!/usr/bin/env python3
"""The single source of truth for release artifact filenames.

Every consumer (the release gate, the config validator, the release-notes
generator) derives names from here instead of hand-maintaining its own list.
Three copies had already drifted: the AppImage was written as `-x64.AppImage` in
the validator, the notes table and the website, while electron-builder actually
emits `-x86_64.AppImage`.

The arch token is NOT a single string. electron-builder resolves it per *target
extension*, following each packaging ecosystem's own convention — AppImage and
rpm use `x86_64`, dpkg uses `amd64`, everything else uses the plain arch. This is
a faithful port of `builder-util/out/arch.js: getArtifactArchName(arch, ext)`.
Normalising these to one string would fight `dpkg`/`appimagetool`, so the correct
long-term fix is to model the rule, not to override it.
"""
from __future__ import annotations

# ext (lowercased) -> arch name, for a 64-bit Intel build.
_X64_BY_EXT = {
    "appimage": "x86_64",
    "rpm": "x86_64",
    "flatpak": "x86_64",
    "deb": "amd64",
    "snap": "amd64",
}

# ext (lowercased) -> arch name, for 32-bit.
_IA32_BY_EXT = {
    "deb": "i386",
    "appimage": "i386",
    "snap": "i386",
    "flatpak": "i386",
    "pacman": "i686",
    "rpm": "i686",
}

# ext (lowercased) -> arch name, for arm64.
_ARM64_BY_EXT = {
    "pacman": "aarch64",
    "rpm": "aarch64",
    "flatpak": "aarch64",
}


def artifact_arch_name(arch: str, ext: str) -> str:
    """What electron-builder substitutes for ``${arch}`` in an artifactName.

    Port of builder-util ``getArtifactArchName``. ``ext`` is the target
    extension without a dot (``AppImage``, ``deb``, ``exe``, ``dmg``, ``zip``).
    """
    ext = ext.lower().lstrip(".")
    if arch == "x64":
        return _X64_BY_EXT.get(ext, "x64")
    if arch == "ia32":
        return _IA32_BY_EXT.get(ext, "ia32")
    if arch == "arm64":
        return _ARM64_BY_EXT.get(ext, "arm64")
    return arch


def render(pattern: str, version: str, arch: str, ext: str) -> str:
    """Expand an electron-builder artifactName pattern the way it does."""
    return (pattern.replace("${version}", version)
                   .replace("${arch}", artifact_arch_name(arch, ext))
                   .replace("${ext}", ext))


# --- the canonical release asset set ----------------------------------------
# (arch, ext, human label, which package.json section owns the artifactName)
INSTALLER_TARGETS: list[tuple[str, str, str, str]] = [
    ("x64",   "exe",      "Windows installer",                      "nsis"),
    ("x64",   "zip",      "Windows portable",                       "win"),
    ("x64",   "dmg",      "macOS (Intel)",                          "dmg"),
    ("arm64", "dmg",      "macOS (Apple Silicon)",                  "dmg"),
    # electron-updater cannot update from a .dmg — the zip IS the macOS update
    # payload referenced by latest-mac.yml. A release without it silently breaks
    # auto-update for every Mac user.
    ("x64",   "zip",      "macOS update payload (Intel)",           "mac"),
    ("arm64", "zip",      "macOS update payload (Apple Silicon)",   "mac"),
    ("x64",   "AppImage", "Linux AppImage",                         "appImage"),
    ("x64",   "deb",      "Linux .deb",                             "deb"),
]

# electron-updater reads these; without them installed apps never see updates.
UPDATE_FEEDS: list[tuple[str, str]] = [
    ("latest.yml",       "Windows update feed"),
    ("latest-mac.yml",   "macOS update feed"),
    ("latest-linux.yml", "Linux update feed"),
]


def installer_names(build: dict, version: str) -> list[tuple[str, str]]:
    """[(filename, label)] for every installer, using package.json's own patterns."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for arch, ext, label, section in INSTALLER_TARGETS:
        pattern = build[section]["artifactName"]
        name = render(pattern, version, arch, ext)
        if name in seen:          # win zip and mac zip must not collide
            continue
        seen.add(name)
        out.append((name, label))
    return out


def payload_names(version: str) -> list[tuple[str, str]]:
    """The source archives for CLI / headless users."""
    return [
        (f"redforge-{version}.zip", "source payload (zip)"),
        (f"redforge-{version}.tar.gz", "source payload (tar.gz)"),
    ]
