"""Self-updater: `redforge update`.

Checks GitHub Releases, compares the published version against the local
``VERSION``, downloads the newest release archive, verifies its SHA-256 against
the published ``SHA256SUMS.txt``, and swaps it into place **atomically enough**
to roll back on any failure. User data is never touched:

  * ``.redforge/`` (venv, settings, logs, pid, install state) is outside the
    release payload and is left as-is.
  * The evaluation database (``backend/redforge.db``) is moved aside before the
    backend directory is replaced and restored into the new tree.

Standard library only (``urllib``, ``zipfile``, ``hashlib``, ``shutil``).

The network-free pieces — version comparison, checksum verification, asset
selection, and the file swap/rollback — are separated out so they are unit
testable without hitting GitHub.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from ._version import __version__
from .colors import bold, cyan, dim, green, red, yellow

DEFAULT_REPO = os.environ.get("REDFORGE_REPO", "BRGOVIND/REDFORGE")

# Release payload — the top-level entries a release archive installs. Anything
# not listed here (notably .redforge/ and *.db) is preserved untouched.
PAYLOAD = [
    "backend", "cli", "datasets", "docs", "VERSION",
    "README.md", "CHANGELOG.md", "RELEASE_NOTES.md", "LICENSE",
    "ROADMAP.md", "CONTRIBUTING.md", "SECURITY.md",
    "install.sh", "install.cmd", "start.sh", "start.cmd", "READ_ME_FIRST.txt",
]

# Files that hold user data and must survive a backend replacement.
PRESERVE_WITHIN_PAYLOAD = ["backend/redforge.db"]


# ---------------------------------------------------------------------------
# Version comparison (pure)
# ---------------------------------------------------------------------------

def parse_version(text: str) -> tuple:
    """('1.2.0-beta') -> (1, 2, 0, 0) where the 4th field ranks prereleases
    below the final release (a suffix ⇒ 0, no suffix ⇒ 1)."""
    text = text.strip().lstrip("vV")
    m = re.match(r"(\d+)\.(\d+)\.(\d+)(.*)$", text)
    if not m:
        return (0, 0, 0, 0)
    major, minor, patch, rest = m.groups()
    final_rank = 0 if rest.strip() else 1
    return (int(major), int(minor), int(patch), final_rank)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


# ---------------------------------------------------------------------------
# Checksums (pure)
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse ``<hex>  <name>`` lines into {basename: hex}."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[-1]] = parts[0].lower()
    return sums


def verify_sha256(path: Path, sums: dict[str, str]) -> bool:
    expected = sums.get(path.name)
    if not expected:
        return False
    return sha256_file(path) == expected


# ---------------------------------------------------------------------------
# Release metadata (pure selection over a GitHub API payload)
# ---------------------------------------------------------------------------

def select_assets(release: dict) -> tuple[str | None, str | None]:
    """(archive_url, sums_url) — prefer the .zip archive and SHA256SUMS.txt."""
    archive = sums = None
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("browser_download_url")
        if name.endswith(".zip") and name.lower().startswith("redforge"):
            archive = url
        elif name == "SHA256SUMS.txt":
            sums = url
    return archive, sums


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "redforge-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - github
        return resp.read()


def fetch_latest_release(repo: str = DEFAULT_REPO) -> dict:
    data = _get(f"https://api.github.com/repos/{repo}/releases/latest")
    return json.loads(data.decode())


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "redforge-updater"})
    with urllib.request.urlopen(req, timeout=120.0) as resp:  # noqa: S310
        with dest.open("wb") as fh:
            shutil.copyfileobj(resp, fh)


# ---------------------------------------------------------------------------
# Safe file swap with rollback (offline-testable)
# ---------------------------------------------------------------------------

def _release_root(staging: Path) -> Path:
    """A release archive extracts to a single ``redforge-<version>/`` dir."""
    entries = [p for p in staging.iterdir()]
    dirs = [p for p in entries if p.is_dir()]
    if len(entries) == 1 and dirs:
        return dirs[0]
    if len(dirs) == 1 and not any(p.is_file() for p in entries):
        return dirs[0]
    return staging


def apply_release(staging: Path, install_root: Path) -> Path:
    """Replace the install with the staged release, preserving user data.

    Returns the backup directory. Raises on failure **after** restoring the
    original tree, so the install is never left half-updated.
    """
    src = _release_root(staging)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = paths.runtime_home() / "backups" / ts
    backup.mkdir(parents=True, exist_ok=True)

    # Hold user-data files that live inside a replaced payload dir.
    held: dict[str, Path] = {}
    hold = backup / "_preserved"
    for rel in PRESERVE_WITHIN_PAYLOAD:
        current = install_root / rel
        if current.is_file():
            hold.mkdir(parents=True, exist_ok=True)
            dest = hold / rel.replace("/", "__")
            shutil.copy2(current, dest)
            held[rel] = dest

    # Every item whose original target we backed up (and removed). Recorded
    # BEFORE the move so an item failing mid-replacement is still restorable.
    backed_up: list[str] = []
    try:
        for name in PAYLOAD:
            new_item = src / name
            if not new_item.exists():
                continue
            target = install_root / name
            if target.exists():
                if target.is_dir():
                    shutil.copytree(target, backup / name, dirs_exist_ok=True)
                    backed_up.append(name)
                    shutil.rmtree(target)
                else:
                    shutil.copy2(target, backup / name)
                    backed_up.append(name)
                    target.unlink()
            shutil.move(str(new_item), str(target))

        # Restore preserved user-data files into the new tree (success path only).
        for rel, saved in held.items():
            dest = install_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, dest)

    except Exception:
        _rollback(backup, install_root, backed_up)
        raise

    return backup


def _rollback(backup: Path, install_root: Path, backed_up: list[str]) -> None:
    """Restore every backed-up item, removing whatever is now in its place. The
    backup of a payload dir includes any preserved user data (e.g. the DB), so
    restoring it also restores history."""
    for name in backed_up:
        target = install_root / name
        saved = backup / name
        try:
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink()
            if saved.is_dir():
                shutil.copytree(saved, target, dirs_exist_ok=True)
            elif saved.exists():
                shutil.copy2(saved, target)
        except Exception:  # noqa: BLE001 - best-effort restore
            pass


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _step(msg: str) -> None:
    print(cyan("→") + f" {msg}")


def _ok(msg: str) -> None:
    print(green("✓") + f" {msg}")


def update(*, check_only: bool = False, repo: str = DEFAULT_REPO) -> int:
    print(bold("\nRedForge update\n"))
    current = __version__

    # A git checkout updates via git, not release archives.
    if (paths.root() / ".git").exists() and not check_only:
        _step("Git checkout detected — updating via git…")
        import subprocess
        rc = subprocess.call(["git", "pull"], cwd=str(paths.root()))
        if rc == 0:
            _ok("Updated. Re-run `redforge repair` to refresh dependencies.")
            return 0
        print(red("✕") + " git pull failed.")
        return 1

    try:
        _step(f"Checking {repo} releases…")
        release = fetch_latest_release(repo)
    except Exception as exc:  # noqa: BLE001
        print(red("✕") + f" Could not reach GitHub Releases: {exc}")
        print(dim("   Check your connection or download manually from "
                  f"https://github.com/{repo}/releases"))
        return 1

    latest = (release.get("tag_name") or "").lstrip("vV")
    if not latest:
        print(red("✕") + " Latest release has no version tag.")
        return 1

    print(dim(f"   current {current} · latest {latest}"))
    if not is_newer(latest, current):
        _ok("RedForge is already up to date.")
        return 0
    if check_only:
        print(yellow("!") + f" Update available: {latest} (run `redforge update` to install).")
        return 0

    archive_url, sums_url = select_assets(release)
    if not archive_url or not sums_url:
        print(red("✕") + " Release is missing a .zip archive or SHA256SUMS.txt.")
        print(dim(f"   Download manually: https://github.com/{repo}/releases"))
        return 1

    with tempfile.TemporaryDirectory(prefix="redforge-update-") as tmp:
        tmpd = Path(tmp)
        archive = tmpd / archive_url.rsplit("/", 1)[-1]
        try:
            _step("Downloading release…")
            _download(archive_url, archive)
            _download(sums_url, tmpd / "SHA256SUMS.txt")
        except Exception as exc:  # noqa: BLE001
            print(red("✕") + f" Download failed: {exc}")
            return 1

        _step("Verifying SHA-256…")
        sums = parse_sha256sums((tmpd / "SHA256SUMS.txt").read_text(encoding="utf-8"))
        if not verify_sha256(archive, sums):
            print(red("✕") + " Checksum verification FAILED — aborting (nothing changed).")
            return 1
        _ok("Checksum verified")

        _step("Extracting…")
        staging = tmpd / "staging"
        staging.mkdir()
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staging)

        _step("Applying update (with rollback on failure)…")
        try:
            backup = apply_release(staging, paths.root())
        except Exception as exc:  # noqa: BLE001
            print(red("✕") + f" Update failed and was rolled back: {exc}")
            print(dim("   Your previous installation is intact."))
            return 1

    _ok(f"Updated {current} → {latest}")
    print(dim(f"  Backup of the previous version: {backup}"))
    print(dim("  Refresh dependencies with: ") + "redforge repair")
    return 0
