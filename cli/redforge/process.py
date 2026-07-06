"""Process lifecycle: start (one process), stop, status.

`redforge start` launches a single backend process that serves the API *and* the
built frontend, waits until it is healthy, then opens the browser once. If a
build is missing and Node is available it is built first; otherwise the API still
starts (the packaged release always ships a build).
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
            subprocess.run(["npm", "run", "build"], cwd=str(fe), check=True, shell=(os.name == "nt"))
        except Exception as exc:
            print(yellow(f"Frontend build failed ({exc}); starting API only."))
        return paths.static_dir()
    print(yellow("No frontend build and Node.js not available — starting API only."))
    print(dim("  (Packaged releases include the build; developers can `npm run build`.)"))
    return None


def start(host: str = "127.0.0.1", port: int = 8000, *, dev: bool = False, open_browser: bool = True) -> int:
    url = f"http://{host}:{port}"
    if is_up(port):
        print(green(f"RedForge is already running at {url}"))
        if open_browser:
            webbrowser.open(url)
        return 0

    static = _ensure_frontend_built()
    env = dict(os.environ)
    if static is not None:
        env["REDFORGE_STATIC_DIR"] = str(static)

    log = paths.log_file()
    logf = open(log, "w", encoding="utf-8")

    if dev:
        return _start_dev(host, port, env, logf)

    print(cyan(f"Starting RedForge (single process) on {url} …"))
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=str(paths.backend_dir()), env=env, stdout=logf, stderr=subprocess.STDOUT)
    _write_pid(proc.pid)

    if not _wait_healthy(port, proc):
        print(red("RedForge failed to start. See logs:"), dim(str(log)))
        return 1

    print(green(f"✓ RedForge is running at {bold(url)}"))
    print(dim(f"  logs: {log}   ·   stop with: redforge stop"))
    if open_browser:
        webbrowser.open(url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print(dim("\nStopping…"))
        _terminate(proc.pid)
    finally:
        logf.close()
        _clear_pid()
    return 0


def _start_dev(host: str, port: int, env: dict, logf) -> int:
    """Developer mode: backend with reload + Vite dev server (two processes)."""
    print(cyan("Starting RedForge in DEV mode (backend + Vite, hot reload)…"))
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port), "--reload"],
        cwd=str(paths.backend_dir()), env=env,
    )
    _write_pid(backend.pid)
    vite = subprocess.Popen(["npm", "run", "dev"], cwd=str(paths.frontend_dir()), shell=(os.name == "nt"))
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
