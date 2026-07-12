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
from ._version import __version__
from .colors import bold, cyan, dim, green, red, status_mark, yellow
from .diagnostics import RECOMMENDED_MODELS, as_plaintext, collect, is_ready


def _version() -> str:
    """Prefer the VERSION of the installation we are driving (REDFORGE_HOME-aware)."""
    vf = paths.root() / "VERSION"
    if vf.is_file():
        text = vf.read_text(encoding="utf-8").strip()
        if text:
            return text
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

def _banner() -> None:
    """A tiny forged mark (chevron · ember · chevron) — only for version/doctor."""
    print()
    print("   " + red("▲"))
    print("   " + red("◆") + "   " + bold("RedForge"))
    print("   " + red("▼") + "   " + dim("local AI red teaming"))
    print()


def cmd_version(_args) -> int:
    _banner()
    print(f"RedForge {_version()}")
    return 0


def cmd_doctor(args) -> int:
    _banner()
    checks = collect()
    print(bold("System check\n"))
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


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", ""}


def _is_loopback(host: str) -> bool:
    return host.strip().lower() in _LOOPBACK_HOSTS


def _confirm_network_exposure(host: str, assume_yes: bool) -> bool:
    """Warn before binding to a non-loopback address. Returns True to continue."""
    print()
    print(red("⚠  Network exposure warning"))
    print(f"   You are binding RedForge to {bold(host)}, not localhost.")
    print()
    print("   " + yellow("RedForge has no authentication."))
    print("   Anyone who can reach this machine on the network will be able to")
    print("   use the API — start evaluations, delete models, change settings.")
    print("   This is not recommended unless you understand and accept the risk.")
    print()
    print(dim("   To keep RedForge private, start it without --host (defaults to 127.0.0.1)."))
    print()
    if assume_yes:
        print(dim("   --yes supplied; continuing."))
        return True
    if not sys.stdin.isatty():
        print(red("   Refusing to bind to a public interface non-interactively."))
        print(dim("   Re-run with --yes if you are sure."))
        return False
    try:
        answer = input("   Continue anyway? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def cmd_start(args) -> int:
    if not _is_loopback(args.host) and not _confirm_network_exposure(args.host, args.yes):
        print(dim("Cancelled. RedForge was not started."))
        return 1
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


_MODELS_SNAPSHOT_CODE = (
    "import json, asyncio\n"
    "from app.runtime.manager import get_runtime\n"
    "rt = get_runtime(); p = rt.provider\n"
    "async def go():\n"
    "    online = False; models = []\n"
    "    try: online = await p.health()\n"
    "    except Exception: online = False\n"
    "    if online:\n"
    "        try: models = await rt.list_models(use_cache=False)\n"
    "        except Exception: models = []\n"
    "    return online, models\n"
    "online, models = asyncio.run(go())\n"
    "print(json.dumps({'provider': getattr(p,'name','runtime'), 'label': getattr(p,'label','Runtime'),\n"
    "  'supports_pull': bool(p.capabilities().get('supports_pull', False)),\n"
    "  'setup_hint': getattr(p,'setup_hint','') or None, 'online': online, 'models': models}))\n"
)


def _models_snapshot(port: int) -> dict | None:
    """Active-provider model list via the Runtime Manager.

    Prefers the running backend (its shared RuntimeClient); falls back to running
    the Runtime Manager in-process through the backend interpreter. Never queries
    a provider API directly and never assumes Ollama.
    """
    if process.is_up(port):
        try:
            info = _get_json(f"http://127.0.0.1:{port}/api/providers")
            active = next((p for p in info.get("providers", []) if p.get("is_default")), {})
            data = _get_json(f"http://127.0.0.1:{port}/api/models")
            models = [m["name"] for m in data.get("models", []) if m.get("name")]
            return {
                "label": active.get("label", "Runtime"),
                "supports_pull": bool(active.get("supports_pull")),
                "setup_hint": active.get("setup_hint"),
                "online": not data.get("error"),
                "models": models,
            }
        except Exception:  # noqa: BLE001 - fall through to in-process
            pass
    # Backend not running — use the Runtime Manager in-process.
    import json as _json
    import os as _os

    env = dict(_os.environ)
    env["PYTHONPATH"] = str(paths.backend_dir()) + _os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [paths.backend_python(), "-c", _MODELS_SNAPSHOT_CODE],
            cwd=str(paths.backend_dir()), env=env, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return _json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        pass
    return None


def cmd_models(_args) -> int:
    snap = _models_snapshot(getattr(_args, "port", 8000))
    if snap is None:
        print(red("Could not reach the runtime. Start RedForge (redforge start) or check: redforge doctor"))
        return 1

    label = snap.get("label", "Runtime")
    installed = snap.get("models", [])
    print(bold(f"\nModels · {label}"))
    if not snap.get("online"):
        print(red(f"  {label} is not reachable."))
        if snap.get("setup_hint"):
            print(dim("  ") + snap["setup_hint"])
        return 1
    if installed:
        for m in installed:
            print(f"  {green('✓')} {m}")
    else:
        print(dim("  (no models available)"))

    # Only providers that can download models get pull suggestions.
    if snap.get("supports_pull"):
        print(bold("\nRecommended (download with your runtime)"))
        for m in RECOMMENDED_MODELS:
            mark = green("✓") if m in installed else dim("○")
            print(f"  {mark} {m:<14} {dim('ollama pull ' + m)}")
    elif not installed:
        print(dim("\n  Load a model into your runtime, then re-run: redforge models"))
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


def cmd_install(_args) -> int:
    from . import installer

    return installer.install()


def cmd_uninstall(args) -> int:
    from . import installer

    return installer.uninstall(purge=args.purge)


def cmd_repair(_args) -> int:
    from . import installer

    return installer.repair()


def cmd_update(args) -> int:
    from . import updater

    return updater.update(check_only=args.check)


def cmd_diagnose(args) -> int:
    from . import diagnose

    out = Path(args.output) if args.output else None
    return diagnose.diagnose(port=args.port, output=out)


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
    s.add_argument("--host", default="127.0.0.1",
                   help="bind address (default: 127.0.0.1; non-local values prompt a warning)")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--dev", action="store_true", help="developer mode (backend + Vite hot reload)")
    s.add_argument("--no-browser", action="store_true", help="do not open the browser")
    s.add_argument("--yes", action="store_true",
                   help="skip the network-exposure confirmation when binding a non-local host")

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

    sub.add_parser("install", help="install RedForge (venv, deps, shortcuts, health)")

    un = sub.add_parser("uninstall", help="remove the venv and shortcuts")
    un.add_argument("--purge", action="store_true",
                    help="also delete data (database, logs, settings)")

    sub.add_parser("repair", help="repair an existing installation (idempotent)")

    up = sub.add_parser("update", help="update to the latest GitHub release")
    up.add_argument("--check", action="store_true", help="only check; do not install")

    dg = sub.add_parser("diagnose", help="write a diagnostics.zip support bundle")
    dg.add_argument("--port", type=int, default=8000)
    dg.add_argument("-o", "--output", default=None, help="output path (default: ./diagnostics.zip)")
    return p


_DISPATCH = {
    "version": cmd_version, "doctor": cmd_doctor, "start": cmd_start, "stop": cmd_stop,
    "status": cmd_status, "logs": cmd_logs, "models": cmd_models, "evaluate": cmd_evaluate,
    "benchmark": cmd_benchmark, "install": cmd_install, "uninstall": cmd_uninstall,
    "repair": cmd_repair, "update": cmd_update, "diagnose": cmd_diagnose,
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
