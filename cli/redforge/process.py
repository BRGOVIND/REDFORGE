"""Process lifecycle: start (one process), stop, status.

`redforge start` is the primary launcher. It detects an existing instance,
validates the environment through the centralized **System Health Engine**
(reused, never duplicated), starts a single backend process that serves the API
*and* the built frontend, waits until it is healthy, verifies backend health, and
opens the browser once (the SPA routes to onboarding on first run, else the
dashboard).
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import paths
from .colors import bold, cyan, dim, green, red, yellow


def npm_cmd(args: list[str]) -> list[str]:
    """Build an npm command as an explicit arg list (never shell=True).

    On Windows ``npm`` is ``npm.cmd`` (a batch file), which can't be launched
    without a shell, so we invoke it via ``cmd /c`` with a fixed argument list —
    no string is ever passed to a shell for interpretation.
    """
    return ["cmd", "/c", "npm", *args] if os.name == "nt" else ["npm", *args]


def _http_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - localhost
        return json.loads(resp.read().decode())


def is_up(port: int) -> bool:
    try:
        _http_json(f"http://127.0.0.1:{port}/healthz", timeout=1.0)
        return True
    except Exception:
        return False


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _write_pid(pid: int) -> None:
    paths.pid_file().write_text(str(pid))


def _read_pid() -> int | None:
    f = paths.pid_file()
    if not f.exists():
        return None
    try:
        return int(f.read_text().strip())
    except ValueError:
        return None


def _ensure_frontend_built() -> Path | None:
    static = paths.static_dir()
    if static is not None:
        return static
    fe = paths.frontend_dir()
    node = __import__("shutil").which("node") is not None
    if node and (fe / "package.json").is_file():
        print(dim("No frontend build found — building it once (npm run build)…"))
        try:
            subprocess.run(npm_cmd(["run", "build"]), cwd=str(fe), check=True)
        except Exception as exc:
            print(yellow(f"Frontend build failed ({exc}); starting API only."))
        return paths.static_dir()
    return None


# ---------------------------------------------------------------------------
# Startup progress + health (reuses the Health Engine via diagnostics.collect)
# ---------------------------------------------------------------------------

def _step(msg: str) -> None:
    print(cyan("→") + f" {msg}")


def _ok(msg: str) -> None:
    print(green("✓") + f" {msg}")


def _warn(msg: str) -> None:
    print(yellow("!") + f" {msg}")


def _fail(msg: str) -> None:
    print(red("✕") + f" {msg}")


def _hint(check, label: str) -> None:
    """Surface a non-blocking, actionable hint for a non-ok check."""
    if check is not None and check.level != "ok":
        _warn(f"{label}: {check.detail}")


def _preflight() -> bool:
    """Validate the environment through the System Health Engine (single source
    of truth). Returns False only for genuinely blocking problems; missing
    runtime/models are surfaced as hints but never block launch — the onboarding
    flow guides the user through those.
    """
    from . import diagnostics

    checks = diagnostics.collect()
    by_id = {getattr(c, "id", ""): c for c in checks}

    # Backend dependencies not installed → the engine ran in bootstrap mode.
    if "deps" in by_id:
        _fail("Backend dependencies are not installed.")
        print(dim("   Fix: ") + "redforge install")
        return False

    # Blocking: any critical-severity failure (e.g. Python too old).
    critical = [c for c in checks if c.level == "fail" and c.severity == "critical"]
    if critical:
        for c in critical:
            _fail(f"{c.label}: {c.detail}")
        print(dim("   Fix: ") + "resolve the above, then run: redforge start")
        return False

    _ok("System checks passed")
    # Non-blocking, actionable hints (onboarding will also guide these).
    _hint(by_id.get("provider_health"), "Runtime")
    _hint(by_id.get("installed_models"), "Models")
    _hint(by_id.get("database"), "Database")
    return True


def _diagnose_startup_failure(log: Path) -> tuple[str, str, bool]:
    """(message, fix, retryable) inferred from the backend log tail."""
    tail = ""
    try:
        tail = log.read_text(encoding="utf-8", errors="ignore")[-4000:].lower()
    except Exception:
        pass
    if any(s in tail for s in ("address already in use", "10048", "only one usage of each socket")):
        return ("The port is already in use by another process.",
                "Stop it, or start on another port: redforge start --port 8100", False)
    if "modulenotfounderror" in tail or "no module named" in tail:
        return ("A backend dependency is missing.", "Install dependencies: redforge install", False)
    if "unable to open database" in tail or "database is locked" in tail:
        return ("The database could not be opened.",
                "Check write permissions for the RedForge data directory, then retry.", False)
    if "permission denied" in tail or "winerror 5" in tail:
        return ("Permission was denied while starting.",
                "Run from a writable location or adjust permissions.", False)
    return ("The backend failed to start.", f"See the log for details: {log}", True)


def _verify_backend_health(port: int) -> None:
    """Backend is up — confirm via the Health Engine over HTTP (reuse, never a
    second implementation). Non-blocking: warnings are shown, never fatal."""
    try:
        report = _http_json(f"http://127.0.0.1:{port}/api/health", timeout=10.0)
    except Exception:
        return
    status = report.get("status", "unknown")
    s = report.get("summary", {})
    mark = {"healthy": green("✓"), "warning": yellow("!"), "error": red("✕")}.get(status, dim("•"))
    print(f"{mark} Backend health: {status} "
          + dim(f"({s.get('healthy', 0)} ok · {s.get('warning', 0)} warning · {s.get('error', 0)} error)"))
    for c in report.get("checks", []):
        if c.get("status") == "error" and c.get("severity") in ("critical", "high"):
            fix = c.get("suggested_fix")
            _warn(f"{c.get('name')}: {c.get('message')}" + (f" — {fix}" if fix else ""))


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def start(host: str = "127.0.0.1", port: int = 8000, *, dev: bool = False, open_browser: bool = True) -> int:
    url = f"http://{host}:{port}"

    # 1. Detect an existing instance / port conflict (prevent duplicate launches).
    if is_up(port):
        _ok(f"RedForge is already running at {bold(url)}")
        if open_browser:
            webbrowser.open(url)
        return 0
    if _port_open(port):
        _fail(f"Port {port} is already in use by another process.")
        print(dim("   Fix: ") + "stop it, or choose another port: redforge start --port 8100")
        return 1

    print(bold("\nStarting RedForge\n"))

    # 2. Environment validation via the Health Engine (single source of truth).
    _step("Running system checks…")
    if not _preflight():
        return 1

    # 3. Interface (built frontend).
    _step("Preparing interface…")
    static = _ensure_frontend_built()
    env = dict(os.environ)
    if static is not None:
        env["REDFORGE_STATIC_DIR"] = str(static)
        _ok("Interface ready")
    else:
        _warn("No prebuilt interface found — serving the API only (dev builds on demand)")

    if dev:
        return _start_dev(host, port, env)

    # 4. Start the backend, retrying once on a transient failure.
    log = paths.log_file()
    proc: subprocess.Popen | None = None
    logf = None
    for attempt in (1, 2):
        _step("Starting backend…" if attempt == 1 else "Retrying backend start…")
        logf = open(log, "w", encoding="utf-8")
        # Use the dedicated venv from `redforge install` if present (falls back to
        # this interpreter for source checkouts). Single resolution point.
        cmd = [paths.backend_python(), "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)]
        proc = subprocess.Popen(cmd, cwd=str(paths.backend_dir()), env=env, stdout=logf, stderr=subprocess.STDOUT)
        _write_pid(proc.pid)
        _step("Waiting for the backend to become ready…")
        if _wait_healthy(port, proc):
            break

        message, fix, retryable = _diagnose_startup_failure(log)
        _terminate(proc.pid)
        _clear_pid()
        try:
            logf.close()
        except Exception:
            pass
        proc, logf = None, None
        if attempt == 1 and retryable:
            time.sleep(1.0)
            continue
        _fail(message)
        print(dim("   Fix: ") + fix)
        print(dim("   Log: ") + str(log))
        return 1

    assert proc is not None
    _ok("Backend is ready")

    # 5. Verify backend health (Health Engine over HTTP).
    _verify_backend_health(port)

    # 6. Ready → open the browser (SPA routes to onboarding on first run).
    print()
    _ok(f"RedForge is ready at {bold(url)}")
    print(dim(f"  logs: {log}   ·   stop with: redforge stop"))
    if open_browser:
        _step("Opening your browser…")
        webbrowser.open(url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print(dim("\nStopping…"))
        _terminate(proc.pid)
    finally:
        if logf is not None:
            logf.close()
        _clear_pid()
    return 0


def _start_dev(host: str, port: int, env: dict) -> int:
    """Developer mode: backend with reload + Vite dev server (two processes)."""
    print(cyan("Starting RedForge in DEV mode (backend + Vite, hot reload)…"))
    backend = subprocess.Popen(
        [paths.backend_python(), "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port), "--reload"],
        cwd=str(paths.backend_dir()), env=env,
    )
    _write_pid(backend.pid)
    vite = subprocess.Popen(npm_cmd(["run", "dev"]), cwd=str(paths.frontend_dir()))
    print(green("Backend :%d  ·  Vite :5173" % port))
    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in (vite, backend):
            try:
                p.terminate()
            except Exception:
                pass
        _clear_pid()
    return 0


def _wait_healthy(port: int, proc: subprocess.Popen, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:  # process died
            return False
        if is_up(port):
            return True
        time.sleep(0.5)
    return False


def _terminate(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def _clear_pid() -> None:
    try:
        paths.pid_file().unlink()
    except OSError:
        pass


def stop(port: int = 8000) -> int:
    pid = _read_pid()
    if pid is None and not _port_open(port):
        print(yellow("RedForge does not appear to be running."))
        return 0
    if pid is not None:
        print(cyan(f"Stopping RedForge (pid {pid})…"))
        _terminate(pid)
        _clear_pid()
    # Give the OS a moment to release the port.
    for _ in range(10):
        if not _port_open(port):
            break
        time.sleep(0.3)
    if _port_open(port):
        print(yellow(f"Port {port} still in use; a process may need to be closed manually."))
        return 1
    print(green("✓ RedForge stopped."))
    return 0


def status(port: int = 8000) -> int:
    if not is_up(port):
        print(red("● RedForge is not running."))
        print(dim("  Start it with: redforge start"))
        return 1

    base = f"http://127.0.0.1:{port}"
    print(green(f"● RedForge is running")); print(f"  URL:        {base}")
    pid = _read_pid()
    if pid:
        print(f"  PID:        {pid}")
    print(f"  Port:       {port}")

    try:
        sessions = _http_json(f"{base}/api/sessions", timeout=2.0)
        active = [s for s in sessions if s.get("status") in ("running", "pending", "paused")]
        print(f"  Sessions:   {len(sessions)} total, {len(active)} active")
    except Exception:
        pass
    try:
        models = _http_json(f"{base}/api/models", timeout=3.0)
        n = len(models.get("models", [])) if isinstance(models, dict) else 0
        print(f"  Models:     {n} installed")
    except Exception:
        pass
    try:
        rt = _http_json(f"{base}/api/runtime/status", timeout=2.0)
        m = rt.get("metrics", {})
        print(f"  Runtime:    {rt.get('provider')} · {m.get('active_requests', 0)} active, "
              f"queue {m.get('queue_length', 0)}, avg {m.get('avg_latency_ms', 0)} ms")
    except Exception:
        pass

    _print_process_resources(pid)
    return 0


def _print_process_resources(pid: int | None) -> None:
    if not pid:
        return
    try:
        import psutil  # optional

        p = psutil.Process(pid)
        mem = p.memory_info().rss // (1024 * 1024)
        print(f"  Memory:     {mem} MB")
        print(f"  CPU:        {p.cpu_percent(interval=0.2):.0f}%")
    except Exception:
        pass
