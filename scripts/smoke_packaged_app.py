#!/usr/bin/env python3
"""Start the packaged backend and prove the UI it serves is actually loadable.

Static checks confirm the right files were built and copied. They cannot confirm
that the running app can FETCH them: that depends on the mount path, the port,
the MIME type and the cache policy. RedForge 2.0.3 shipped a complete, correct
asset set that users still could not navigate, because the shell was served with
no `Cache-Control` and browsers reused the previous version's copy across the
upgrade. This test exercises the served surface end to end.

Checks, against a real HTTP server:

  1. the backend boots and answers /healthz
  2. GET / returns the SPA, and it is revalidated (never blindly cached)
  3. the entry bundle named by index.html loads as JavaScript
  4. EVERY lazily imported route chunk loads as JavaScript — the failure mode
     reported in 2.0.3, where one uncached route 404'd after an upgrade
  5. hashed assets are immutable, so caching stays fast where it is safe
  6. a missing chunk is an honest 404, not index.html wearing a .js name
  7. a client-side route still returns the SPA

Usage:
    python scripts/smoke_packaged_app.py desktop/resources/backend
    python scripts/smoke_packaged_app.py --static backend/app/static   # no freeze
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from verify_frontend_assets import references  # noqa: E402

BOOT_TIMEOUT_S = 90.0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str, timeout: float = 30.0, retries: int = 2) -> tuple[int, dict[str, str], bytes]:
    """Fetch a URL. A transport failure is reported as status 0, never raised.

    A single hung request must be a FAILED CHECK, not a crashed smoke test —
    otherwise the run tells us nothing about the other 50 chunks.
    """
    last = ""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()
        except OSError as exc:
            last = str(exc) or exc.__class__.__name__
            if attempt < retries:
                time.sleep(0.5)
    return 0, {"x-transport-error": last}, b""


def wait_healthy(base: str, proc: subprocess.Popen) -> bool:
    started = time.monotonic()
    deadline = started + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        # One short attempt per iteration: a slow boot should keep polling, not
        # sit inside a 30s request with retries.
        if get(f"{base}/healthz", timeout=2.0, retries=0)[0] == 200:
            # Printed so a CI runner that creeps toward BOOT_TIMEOUT_S is visible
            # long before it starts failing releases.
            print(f"  backend healthy after {time.monotonic() - started:.1f}s "
                  f"(timeout {BOOT_TIMEOUT_S:.0f}s)")
            return True
        time.sleep(0.4)
    return False


def launch(bundle: Path | None, static: Path, port: int, home: Path,
           log: Path, sinks: list) -> subprocess.Popen:
    """Start the backend with its output going to a FILE, never to a pipe.

    Uvicorn logs a line per request. An undrained subprocess pipe fills its OS
    buffer after a few dozen of them and the server blocks mid-write — which
    looks exactly like the app hanging, and is purely an artefact of how the test
    captured output. A file has no such limit.
    """
    env = {
        **os.environ,
        "REDFORGE_PORT": str(port),
        "REDFORGE_HOST": "127.0.0.1",
        "REDFORGE_HOME": str(home),
        "REDFORGE_STATIC_DIR": str(static),
        "PYTHONUNBUFFERED": "1",
    }
    # Windows will not delete a directory while a handle into it is open, so the
    # caller closes this once the child is gone.
    sink = log.open("wb")
    sinks.append(sink)
    if bundle is not None:
        exe = bundle / ("redforge-backend.exe" if os.name == "nt" else "redforge-backend")
        print(f"launching frozen backend: {exe}")
        return subprocess.Popen([str(exe)], cwd=str(bundle), env=env,
                                stdout=sink, stderr=subprocess.STDOUT)
    print("launching backend from source (no frozen binary given)")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT / "backend"), env=env,
        stdout=sink, stderr=subprocess.STDOUT,
    )


def run_checks(base: str, static: Path) -> list[str]:
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            failures.append(f"{name}: {detail}")

    status, headers, body = get(f"{base}/")
    check("GET / returns the SPA", status == 200 and b"<" in body[:64], f"status {status}")
    cache = headers.get("cache-control", "")
    check("index.html is revalidated, never blindly cached", "no-cache" in cache,
          f"cache-control: {cache or '(absent)'}")

    # Everything index.html and the chunks reference, walked transitively.
    assets_dir = static / "assets"
    wanted: set[str] = references(static / "index.html")
    for f in sorted(assets_dir.glob("*.js")):
        wanted |= references(f)
    scripts = sorted(a for a in wanted if a.endswith(".js"))
    styles = sorted(a for a in wanted if a.endswith(".css"))
    check("index.html names an entry bundle", bool(scripts), f"{len(scripts)} js references")

    bad_status: list[str] = []
    bad_type: list[str] = []
    bad_cache: list[str] = []
    for name in scripts + styles:
        st, hd, _ = get(f"{base}/assets/{name}")
        if st != 200:
            bad_status.append(f"{name} -> {st}")
            continue
        ctype = hd.get("content-type", "")
        expected = "javascript" if name.endswith(".js") else "css"
        if expected not in ctype:
            bad_type.append(f"{name} -> {ctype}")
        if "immutable" not in hd.get("cache-control", ""):
            bad_cache.append(f"{name} -> {hd.get('cache-control', '(absent)')}")

    check(f"all {len(scripts)} JS chunks + {len(styles)} CSS load with HTTP 200",
          not bad_status, "; ".join(bad_status[:4]))
    check("every chunk has the correct Content-Type", not bad_type, "; ".join(bad_type[:4]))
    check("hashed assets are cacheable as immutable", not bad_cache, "; ".join(bad_cache[:4]))

    st, hd, _ = get(f"{base}/assets/NewEvaluationPage-DoesNotExist.js")
    check("a missing chunk is a 404, not index.html",
          st == 404 and "text/html" not in hd.get("content-type", ""),
          f"status {st}, type {hd.get('content-type', '')}")

    st, hd, _ = get(f"{base}/nonexistent-asset.js")
    check("a missing asset outside /assets is a 404 too",
          st == 404 and "text/html" not in hd.get("content-type", ""),
          f"status {st}, type {hd.get('content-type', '')}")

    bad_routes: list[str] = []
    for route in ("/training", "/new", "/settings", "/models", "/benchmarks", "/model-hub"):
        st, hd, _ = get(f"{base}{route}")
        if st != 200 or "text/html" not in hd.get("content-type", ""):
            bad_routes.append(f"{route} -> {st}")
    check("client-side routes still return the SPA", not bad_routes, "; ".join(bad_routes))

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", nargs="?", type=Path, default=None,
                    help="a staged/packaged backend dir (holds redforge-backend and app/static)")
    ap.add_argument("--static", type=Path, default=None,
                    help="serve this frontend build instead of the bundle's own")
    args = ap.parse_args()

    bundle: Path | None = args.bundle
    if bundle is not None and not bundle.is_dir():
        print(f"not a directory: {bundle}", file=sys.stderr)
        return 1

    static = args.static or (bundle / "app" / "static" if bundle else ROOT / "backend" / "app" / "static")
    if not (static / "index.html").is_file():
        print(f"no frontend build at {static}", file=sys.stderr)
        return 1

    exe_name = "redforge-backend.exe" if os.name == "nt" else "redforge-backend"
    if bundle is not None and not (bundle / exe_name).is_file():
        print(f"note: no frozen binary in {bundle}; running the backend from source")
        bundle = None

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    print(f"smoke test: serving {static} on {base}\n")

    # ignore_cleanup_errors: on Windows the backend's SQLite files can still be
    # held for a moment after terminate(). Failing to remove a temp directory must
    # never turn an all-green smoke test into a red release.
    with tempfile.TemporaryDirectory(prefix="redforge-smoke-", ignore_cleanup_errors=True) as tmp:
        log = Path(tmp) / "backend.log"
        sinks: list = []
        proc = launch(bundle, static, port, Path(tmp), log, sinks)
        try:
            if not wait_healthy(base, proc):
                print("backend did not become healthy", file=sys.stderr)
                for s in sinks:
                    s.flush()
                if log.is_file():
                    print(log.read_text(encoding="utf-8", errors="replace")[-4000:], file=sys.stderr)
                return 1
            failures = run_checks(base, static)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            for s in sinks:
                s.close()

    if failures:
        print(f"\n{len(failures)} check(s) failed:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nOK: the packaged app serves every lazy-loaded chunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
