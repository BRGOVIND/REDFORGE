"""`redforge` — the unified command-line interface.

Commands: install · doctor · start · stop · status · update · models ·
benchmark · evaluate · logs · version.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import paths, process
from .colors import bold, cyan, dim, green, red, status_mark, yellow
from .diagnostics import RECOMMENDED_MODELS, as_plaintext, collect, is_ready

__version__ = "1.0.0"


def _version() -> str:
    vf = paths.root() / "VERSION"
    if vf.is_file():
        return vf.read_text().strip()
    return __version__


def _post_json(url: str, payload: dict, timeout: float = 10.0):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - localhost
        return json.loads(resp.read().decode())


def _get_json(url: str, timeout: float = 3.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - localhost
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_version(_args) -> int:
    print(f"RedForge {_version()}")
    return 0


def cmd_doctor(args) -> int:
    checks = collect()
    print(bold("\nRedForge Doctor\n"))
    for c in checks:
        print(f"  {status_mark(c.level)} {c.label:<22} {dim(c.detail)}")
    ready = is_ready(checks)
    print()
    print(green("✓ System ready — run: redforge start") if ready
          else yellow("⚠ Some checks need attention before you can run an evaluation."))
    if args.copy:
        print(dim("\n----- copy below -----"))
        print(as_plaintext(checks))
    else:
        print(dim("\n(run `redforge doctor --copy` to print copyable diagnostics)"))
    return 0 if ready else 1


def cmd_start(args) -> int:
    return process.start(args.host, args.port, dev=args.dev, open_browser=not args.no_browser)


def cmd_stop(args) -> int:
    return process.stop(args.port)


def cmd_status(args) -> int:
    return process.status(args.port)


def cmd_logs(args) -> int:
    log = paths.log_file()
    if not log.exists():
        print(yellow("No log file yet — start RedForge first."))
        return 1
    lines = log.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines[-args.lines:]:
        print(line)
    return 0


def cmd_models(_args) -> int:
    try:
        data = _get_json("http://localhost:11434/api/tags")
        installed = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        print(red("Ollama is not reachable. Start it with: ollama serve"))
        installed = []
    print(bold("\nInstalled models"))
    if installed:
        for m in installed:
            print(f"  {green('✓')} {m}")
    else:
        print(dim("  (none)"))
    print(bold("\nRecommended"))
    for m in RECOMMENDED_MODELS:
        mark = green("✓") if m in installed else dim("○")
        print(f"  {mark} {m:<12} {dim('ollama pull ' + m)}")
    return 0


def _run_evaluation(model: str, profile: str, port: int) -> int:
    if not process.is_up(port):
        print(red("RedForge is not running. Start it with: redforge start"))
        return 1
    try:
        res = _post_json(f"http://127.0.0.1:{port}/api/evaluate", {"model": model, "profile": profile})
    except Exception as exc:
        print(red(f"Failed to start evaluation: {exc}"))
        return 1
    sid = res.get("session_id", "")
    print(green(f"✓ Evaluation started · profile={profile} · model={model}"))
    print(f"  Session: {sid}")
    print(f"  Watch:   http://127.0.0.1:{port}/live/{sid}")
    return 0


def cmd_evaluate(args) -> int:
    return _run_evaluation(args.model, args.profile, args.port)


def cmd_benchmark(args) -> int:
    return _run_evaluation(args.model, "thorough", args.port)


def cmd_install(args) -> int:
    print(bold("\nInstalling RedForge\n"))
    v = sys.version_info
    if (v.major, v.minor) < (3, 11):
        print(red(f"✕ Python {v.major}.{v.minor} found — RedForge needs Python ≥ 3.11."))
        return 1
    print(green(f"✓ Python {v.major}.{v.minor}.{v.micro}"))

    req = paths.backend_dir() / "requirements.txt"
    if req.is_file() and not args.skip_deps:
        print(cyan("Installing backend dependencies…"))
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)])
        print(green("✓ Backend dependencies") if rc == 0 else yellow("⚠ pip reported an issue"))

    # Frontend build (developers / from-source only; releases ship a build).
    static = paths.static_dir()
    fe = paths.frontend_dir()
    if static is None and (fe / "package.json").is_file() and __import__("shutil").which("node"):
        print(cyan("Building frontend assets…"))
        subprocess.call(process.npm_cmd(["install"]), cwd=str(fe))
        subprocess.call(process.npm_cmd(["run", "build"]), cwd=str(fe))
    print(green("✓ Frontend assets") if paths.static_dir() else dim("• Frontend build skipped (no Node)"))

    # Initialize the database (idempotent; the backend also does this on start).
    print(cyan("Initializing database…"))
    init = "import asyncio; from app.db.database import init_db; asyncio.run(init_db())"
    subprocess.call([sys.executable, "-c", init], cwd=str(paths.backend_dir()))
    print(green("✓ Database initialized"))

    # Datasets are shipped statically; verify.
    bench = paths.datasets_dir() / "redforge-bench-v1"
    n = len(list(bench.glob("*.json"))) if bench.is_dir() else 0
    print(green(f"✓ Benchmark dataset ({n} categories)") if n >= 5 else red("✕ Benchmark dataset missing"))

    print(bold("\nVerifying…"))
    return cmd_doctor(argparse.Namespace(copy=False))


def cmd_update(_args) -> int:
    if (paths.root() / ".git").exists():
        print(cyan("Updating from git…"))
        subprocess.call(["git", "pull"], cwd=str(paths.root()))
        return cmd_install(argparse.Namespace(skip_deps=False))
    print(yellow("Not a git checkout. Download the latest release from:"))
    print("  https://github.com/BRGOVIND/REDFORGE/releases")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="redforge", description="RedForge — local AI security evaluation")
    p.add_argument("-v", "--version", action="store_true", help="print version and exit")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("version", help="print version")
    d = sub.add_parser("doctor", help="run system diagnostics")
    d.add_argument("--copy", action="store_true", help="also print copyable diagnostics")

    s = sub.add_parser("start", help="start RedForge and open the browser")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--dev", action="store_true", help="developer mode (backend + Vite hot reload)")
    s.add_argument("--no-browser", action="store_true", help="do not open the browser")

    for name, help_ in [("stop", "stop RedForge"), ("status", "show run status")]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--port", type=int, default=8000)

    lg = sub.add_parser("logs", help="show recent logs")
    lg.add_argument("-n", "--lines", type=int, default=60)

    sub.add_parser("models", help="list installed and recommended models")

    ev = sub.add_parser("evaluate", help="start an evaluation")
    ev.add_argument("model")
    ev.add_argument("profile", nargs="?", default="quick_scan")
    ev.add_argument("--port", type=int, default=8000)

    bm = sub.add_parser("benchmark", help="run a benchmark evaluation")
    bm.add_argument("model")
    bm.add_argument("--port", type=int, default=8000)

    inst = sub.add_parser("install", help="install/verify RedForge")
    inst.add_argument("--skip-deps", action="store_true")

    sub.add_parser("update", help="update RedForge")
    return p


_DISPATCH = {
    "version": cmd_version, "doctor": cmd_doctor, "start": cmd_start, "stop": cmd_stop,
    "status": cmd_status, "logs": cmd_logs, "models": cmd_models, "evaluate": cmd_evaluate,
    "benchmark": cmd_benchmark, "install": cmd_install, "update": cmd_update,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version or args.command == "version":
        return cmd_version(args)
    if not args.command:
        parser.print_help()
        return 0
    return _DISPATCH[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
