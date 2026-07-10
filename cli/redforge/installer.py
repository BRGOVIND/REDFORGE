"""Self-installer: `redforge install` / `uninstall` / `repair`.

Cross-platform (Windows / Linux / macOS), standard-library only. The installer
creates a dedicated virtual environment for the backend, installs the pinned
requirements into it, verifies the runtime environment, and wires desktop /
Start-Menu shortcuts. It is **idempotent**: running it again repairs an existing
install rather than duplicating it, and a failed run never leaves a
half-installed system (a venv we created this run is rolled back on failure).

Runtime logic is not duplicated: system validation reuses the backend **Health
Engine** (run through the venv interpreter, the single source of truth), and
`redforge start` / diagnostics resolve the backend interpreter through
:func:`paths.backend_python`.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import paths, shortcuts
from ._version import __version__
from .colors import bold, cyan, dim, green, red, yellow

MIN_PYTHON = (3, 11)

# Provider presence detection (install-time, dependency-free). Full health comes
# from the Runtime Manager / Health Engine once deps are installed.
_PROVIDER_PROBES = [
    ("Ollama", 11434, ("ollama",)),
    ("LM Studio", 1234, ("lms",)),
    ("llama.cpp", 8080, ("llama-server", "llama-cli", "server")),
    ("vLLM", 8000, ("vllm",)),
]


class InstallError(Exception):
    """Raised for a fatal, user-actionable installation problem."""

    def __init__(self, message: str, fix: str = "") -> None:
        super().__init__(message)
        self.fix = fix


# ---------------------------------------------------------------------------
# Progress printing
# ---------------------------------------------------------------------------

def _step(msg: str) -> None:
    print(cyan("→") + f" {msg}")


def _ok(msg: str) -> None:
    print(green("✓") + f" {msg}")


def _warn(msg: str) -> None:
    print(yellow("!") + f" {msg}")


def _fail(msg: str, fix: str = "") -> None:
    print(red("✕") + f" {msg}")
    if fix:
        print(dim("   Fix: ") + fix)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_os() -> str:
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def check_python() -> tuple[int, int, int]:
    v = sys.version_info
    if (v.major, v.minor) < MIN_PYTHON:
        raise InstallError(
            f"Python {v.major}.{v.minor} found — RedForge needs Python "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}+.",
            fix=f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ and re-run: redforge install",
        )
    return (v.major, v.minor, v.micro)


def check_pip() -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        raise InstallError(
            "pip is not available for this interpreter.",
            fix="Install pip (https://pip.pypa.io/en/stable/installation/) and re-run.",
        ) from exc


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def detect_providers() -> list[dict]:
    """Detect local runtime providers via executable-on-PATH and default ports.

    Dependency-free so it runs before the backend deps exist. This is presence
    detection only; the Runtime Manager reports live health after install.
    """
    results = []
    for label, port, exes in _PROVIDER_PROBES:
        on_path = next((e for e in exes if shutil.which(e)), None)
        running = _port_open(port)
        present = bool(on_path) or running
        if running:
            detail = f"running on :{port}"
        elif on_path:
            detail = f"installed ({on_path}) — not running"
        else:
            detail = "not detected"
        results.append({"label": label, "present": present, "running": running, "detail": detail})
    return results


# ---------------------------------------------------------------------------
# Virtual environment + dependencies
# ---------------------------------------------------------------------------

def _venv_ok(venv: Path) -> bool:
    return paths.venv_python(venv).is_file()


def create_venv(venv: Path) -> bool:
    """Create the venv if missing. Returns True if it created one this run."""
    if _venv_ok(venv):
        return False
    venv.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    except Exception as exc:  # noqa: BLE001
        raise InstallError(
            f"Could not create the virtual environment at {venv}.",
            fix="Ensure the 'venv' module is available (python -m venv --help).",
        ) from exc
    if not _venv_ok(venv):
        raise InstallError(f"Virtual environment at {venv} is missing an interpreter.")
    return True


def install_requirements(venv: Path) -> None:
    req = paths.requirements_file()
    if not req.is_file():
        raise InstallError(
            f"Backend requirements not found at {req}.",
            fix="Run install from a RedForge release or checkout (needs backend/). "
            "If you installed via pip, download a release with: redforge update",
        )
    vpy = str(paths.venv_python(venv))
    try:
        subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        subprocess.run([vpy, "-m", "pip", "install", "-r", str(req)], check=True)
    except subprocess.CalledProcessError as exc:
        raise InstallError(
            "Failed to install backend dependencies.",
            fix=f"Check network access and re-run: redforge repair  (pip exit {exc.returncode})",
        ) from exc


def verify_frontend() -> bool:
    """True if a built frontend is present (packaged release or dev build)."""
    return paths.static_dir() is not None


# ---------------------------------------------------------------------------
# Health Engine (reused, run through the venv interpreter)
# ---------------------------------------------------------------------------

def _backend_run(venv: Path, code: str, timeout: float = 60.0) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(paths.backend_dir()) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [str(paths.venv_python(venv)), "-c", code],
            cwd=str(paths.backend_dir()), env=env,
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


_HEALTH_SNIPPET = (
    "import json, asyncio\n"
    "from app.health import health_service\n"
    "r = asyncio.run(health_service.run())\n"
    "print(json.dumps(r.model_dump()))\n"
)


def run_health(venv: Path) -> dict | None:
    """Run the backend Health Engine via the venv. None if it could not run."""
    rc, out, _err = _backend_run(venv, _HEALTH_SNIPPET)
    if rc != 0 or not out.strip():
        return None
    try:
        return json.loads(out.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return None


def _render_health(report: dict) -> None:
    marks = {"healthy": green("✓"), "warning": yellow("!"), "error": red("✕")}
    for c in report.get("checks", []):
        mark = marks.get(c.get("status"), dim("•"))
        line = f"  {mark} {c.get('name', ''):<20} {dim(c.get('message', ''))}"
        print(line)
    s = report.get("summary", {})
    print(dim(f"  {s.get('healthy', 0)} ok · {s.get('warning', 0)} warning · {s.get('error', 0)} error"))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def _write_state(venv: Path) -> None:
    paths.state_file().write_text(
        json.dumps(
            {
                "version": __version__,
                "venv": str(venv),
                "python": platform.python_version(),
                "installed_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def read_state() -> dict | None:
    try:
        return json.loads(paths.state_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def install(*, repair: bool = False) -> int:
    """Install (or, if already present, repair) RedForge. Idempotent."""
    title = "Repairing RedForge" if repair else "Installing RedForge"
    print(bold(f"\n{title}\n"))
    venv = paths.venv_dir()
    created_venv = False
    try:
        # 1. Environment.
        _step("Detecting environment…")
        _ok(f"OS: {detect_os()}")
        major, minor, micro = check_python()
        _ok(f"Python {major}.{minor}.{micro}")
        check_pip()
        _ok("pip available")

        # 2. Virtual environment.
        _step(f"Preparing virtual environment ({venv})…")
        created_venv = create_venv(venv)
        _ok("Virtual environment created" if created_venv else "Virtual environment present")

        # 3. Backend dependencies.
        _step("Installing backend dependencies…")
        install_requirements(venv)
        _ok("Backend dependencies installed")

        # 4. Frontend assets.
        _step("Verifying interface assets…")
        if verify_frontend():
            _ok("Frontend assets present")
        else:
            _warn("No built frontend found — the API will build/serve on demand "
                  "(packaged releases ship a build).")

        # 5. Providers.
        _step("Detecting runtime providers…")
        any_running = False
        for p in detect_providers():
            any_running = any_running or p["running"]
            (_ok if p["present"] else _warn)(f"{p['label']:<10} {dim(p['detail'])}")
        if not any_running:
            _warn("No provider is currently running. Start one (e.g. `ollama serve`) "
                  "before running an evaluation.")

        # 6. Shortcuts (best-effort).
        _step("Creating shortcuts…")
        made = shortcuts.create()
        if made:
            for path in made:
                _ok(f"Shortcut: {path}")
        else:
            _warn("No shortcuts created on this platform (non-fatal).")

        # 7. Health Engine (reused).
        _step("Running the System Health Engine…")
        report = run_health(venv)
        if report is None:
            _warn("Health Engine could not run yet (see: redforge doctor).")
        else:
            _render_health(report)

        # 8. Record success.
        _write_state(venv)

    except InstallError as exc:
        print()
        _fail(str(exc), exc.fix)
        if created_venv:
            _step("Rolling back the partial virtual environment…")
            shutil.rmtree(venv, ignore_errors=True)
            _ok("Rolled back — no half-installed environment left behind.")
        else:
            _warn("Existing installation left untouched. Re-run: redforge repair")
        return 1

    print()
    _ok(bold("RedForge is installed and ready."))
    print(dim("  Start it with: ") + "redforge start")
    return 0


def uninstall(*, purge: bool = False) -> int:
    """Remove the venv and shortcuts. With --purge, also delete data (DB/logs)."""
    print(bold("\nUninstalling RedForge\n"))
    venv = paths.venv_dir()

    _step("Removing shortcuts…")
    removed = shortcuts.remove()
    _ok(f"Removed {len(removed)} shortcut(s)" if removed else "No shortcuts to remove")

    _step("Removing virtual environment…")
    if venv.exists():
        shutil.rmtree(venv, ignore_errors=True)
        _ok("Virtual environment removed")
    else:
        _ok("No virtual environment present")

    try:
        paths.state_file().unlink()
    except OSError:
        pass

    if purge:
        _step("Purging data (database, logs, settings)…")
        home = paths.runtime_home()
        for name in ("redforge.log", "redforge.pid"):
            try:
                (home / name).unlink()
            except OSError:
                pass
        db = paths.db_path()
        try:
            if db.is_file():
                db.unlink()
                _ok("Database removed")
        except OSError:
            _warn("Could not remove the database (in use?).")
    else:
        print(dim("  Your evaluation history and settings were preserved."))
        print(dim("  Use `redforge uninstall --purge` to remove them too."))

    print()
    _ok("RedForge uninstalled. The `redforge` command itself remains "
        "(remove it with: pip uninstall redforge).")
    return 0


def repair() -> int:
    """Idempotent repair — re-runs install against the existing environment."""
    return install(repair=True)
