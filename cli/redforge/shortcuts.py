"""Desktop / Start-Menu shortcut creation — best-effort, never fatal.

Each function returns a list of created paths (empty if the platform is
unsupported or creation failed). Shortcut creation must NEVER raise into the
installer: a missing shortcut is a warning, not a failed install.

Stdlib only. Windows shortcuts are created with a short PowerShell one-liner
(WScript.Shell) so we need no pywin32.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import paths


def _launch_command() -> tuple[str, list[str]]:
    """(python, args) that launches RedForge, using this interpreter + the CLI."""
    return sys.executable, ["-m", "redforge", "start"]


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _windows_shortcut(link: Path, target: str, args: str, workdir: str, icon: str | None) -> bool:
    icon_line = f'$s.IconLocation = "{icon}";' if icon else ""
    ps = (
        "$w = New-Object -ComObject WScript.Shell;"
        f'$s = $w.CreateShortcut("{link}");'
        f'$s.TargetPath = "{target}";'
        f'$s.Arguments = "{args}";'
        f'$s.WorkingDirectory = "{workdir}";'
        f"{icon_line}"
        "$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        return link.is_file()
    except Exception:
        return False


def _create_windows() -> list[Path]:
    created: list[Path] = []
    python, args = _launch_command()
    workdir = str(paths.root())
    icon = str(paths.backend_dir() / "app" / "static" / "favicon.ico")
    icon = icon if Path(icon).is_file() else None
    arg_str = " ".join(args)

    targets = []
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    if desktop.is_dir():
        targets.append(desktop / "RedForge.lnk")
    appdata = os.environ.get("APPDATA")
    if appdata:
        start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RedForge"
        try:
            start_menu.mkdir(parents=True, exist_ok=True)
            targets.append(start_menu / "RedForge.lnk")
        except OSError:
            pass

    for link in targets:
        if _windows_shortcut(link, python, arg_str, workdir, icon):
            created.append(link)
    return created


# ---------------------------------------------------------------------------
# Linux (freedesktop .desktop)
# ---------------------------------------------------------------------------

def _desktop_entry() -> str:
    python, args = _launch_command()
    exec_cmd = " ".join([python, *args])
    icon = paths.backend_dir() / "app" / "static" / "favicon.ico"
    icon_line = f"Icon={icon}\n" if icon.is_file() else ""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=RedForge\n"
        "Comment=Local AI security evaluation\n"
        f"Exec={exec_cmd}\n"
        f"Path={paths.root()}\n"
        f"{icon_line}"
        "Terminal=true\n"
        "Categories=Development;Security;\n"
    )


def _create_linux() -> list[Path]:
    created: list[Path] = []
    entry = _desktop_entry()
    locations = [
        Path.home() / ".local" / "share" / "applications" / "redforge.desktop",  # menu
        Path.home() / "Desktop" / "RedForge.desktop",                              # desktop
    ]
    for path in locations:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry, encoding="utf-8")
            os.chmod(path, 0o755)
            created.append(path)
        except OSError:
            pass
    return created


# ---------------------------------------------------------------------------
# macOS (.command double-clickable launcher on the Desktop)
# ---------------------------------------------------------------------------

def _create_macos() -> list[Path]:
    created: list[Path] = []
    python, args = _launch_command()
    script = (
        "#!/bin/bash\n"
        f'cd "{paths.root()}"\n'
        f'exec "{python}" {" ".join(args)}\n'
    )
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        launcher = desktop / "RedForge.command"
        try:
            launcher.write_text(script, encoding="utf-8")
            os.chmod(launcher, 0o755)
            created.append(launcher)
        except OSError:
            pass
    return created


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def create() -> list[Path]:
    """Create shortcuts for the current OS. Returns created paths (never raises)."""
    try:
        if os.name == "nt":
            return _create_windows()
        if sys.platform == "darwin":
            return _create_macos()
        return _create_linux()
    except Exception:
        return []


def remove() -> list[Path]:
    """Remove any shortcuts we may have created. Returns removed paths."""
    candidates = [
        Path(os.path.expanduser("~")) / "Desktop" / "RedForge.lnk",
        Path.home() / "Desktop" / "RedForge.desktop",
        Path.home() / "Desktop" / "RedForge.command",
        Path.home() / ".local" / "share" / "applications" / "redforge.desktop",
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(
            Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "RedForge" / "RedForge.lnk"
        )
    removed: list[Path] = []
    for path in candidates:
        try:
            if path.is_file():
                path.unlink()
                removed.append(path)
        except OSError:
            pass
    return removed
