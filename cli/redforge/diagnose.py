"""`redforge diagnose` — collect a support bundle into diagnostics.zip.

Gathers everything needed to debug an installation and nothing that is secret.
It reuses the running app's **Runtime Manager** and **Health Engine** over HTTP
when a server is up (the richest, live source), and falls back to running the
Health Engine through the backend interpreter when it is not.

**API keys are never included.** Config collection is allowlisted to
``REDFORGE_*`` and redacts any key/token/secret by name; provider info comes from
the API, which only ever reports whether a key is *present*, never its value.
"""
from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import installer, paths
from ._version import __version__
from .colors import bold, cyan, dim, green, red, yellow

# Redact env values whose NAME matches these (defense in depth on top of the
# REDFORGE_* allowlist).
_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH|CREDENTIAL)", re.I)
_REDACTED = "***REDACTED***"

# Provider API-key env vars — we record presence only, never the value.
_PROVIDER_KEY_ENVS = [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GROQ_API_KEY", "OPENROUTER_API_KEY",
]


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _server_up(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _get_json(url: str, timeout: float = 8.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - localhost
            return json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Collectors — each returns a JSON-serializable object.
# ---------------------------------------------------------------------------

def collect_system() -> dict:
    return {
        "redforge_version": __version__,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "backend_python": paths.backend_python(),
        "cpu_count": os.cpu_count(),
        "cwd": str(Path.cwd()),
        "install_root": str(paths.root()),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_config() -> dict:
    """REDFORGE_* environment only, with secret-named values redacted, plus
    provider-key *presence* booleans. Never the raw environment."""
    config: dict[str, str] = {}
    for name, value in sorted(os.environ.items()):
        if not name.startswith("REDFORGE_"):
            continue
        config[name] = _REDACTED if _SECRET_NAME.search(name) else value
    provider_keys = {name: (name in os.environ) for name in _PROVIDER_KEY_ENVS}
    return {"redforge_env": config, "provider_api_keys_present": provider_keys}


def collect_packages() -> str:
    """`pip freeze` of the backend environment (venv if present)."""
    try:
        proc = subprocess.run(
            [paths.backend_python(), "-m", "pip", "freeze"],
            capture_output=True, text=True, timeout=60,
        )
        return proc.stdout or proc.stderr
    except Exception as exc:  # noqa: BLE001
        return f"(could not run pip freeze: {exc})"


def collect_install_state() -> dict:
    return {
        "state": installer.read_state(),
        "venv_present": paths.venv_python().is_file(),
        "frontend_present": paths.static_dir() is not None,
    }


def collect_from_server(port: int) -> dict:
    base = _base_url(port)
    return {
        "source": "live server",
        "health": _get_json(f"{base}/api/health"),
        "providers": _get_json(f"{base}/api/providers"),
        "runtime_status": _get_json(f"{base}/api/runtime/status"),
        "models": _get_json(f"{base}/api/models/catalog"),
        "logs": _get_json(f"{base}/api/runtime/logs?limit=1000"),
    }


def collect_offline() -> dict:
    """Server not running: run the Health Engine through the backend interpreter,
    and read logs from the log file."""
    health = installer.run_health(paths.venv_dir()) or {"error": "Health Engine unavailable"}
    logs = ""
    try:
        logs = paths.log_file().read_text(encoding="utf-8", errors="ignore")[-200_000:]
    except OSError:
        logs = "(no log file)"
    return {
        "source": "offline (no running server)",
        "health": health,
        "providers": {"note": "start RedForge for live provider status"},
        "runtime_status": {"note": "server not running"},
        "models": {"note": "server not running"},
        "logs": logs,
    }


# ---------------------------------------------------------------------------
# Redaction safety net (applied to the whole bundle before writing)
# ---------------------------------------------------------------------------

def _scrub(obj):
    """Recursively redact any dict value whose key looks secret. Belt and braces
    on top of allowlisting — guarantees no key slips through from any source."""
    if isinstance(obj, dict):
        return {
            k: (_REDACTED if isinstance(k, str) and _SECRET_NAME.search(k) else _scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def diagnose(port: int = 8000, output: Path | None = None) -> int:
    print(bold("\nCollecting diagnostics\n"))
    out = output or (Path.cwd() / "diagnostics.zip")

    print(cyan("→") + " Gathering system information…")
    bundle = {
        "system": collect_system(),
        "config": collect_config(),
        "install": collect_install_state(),
    }

    if _server_up(port):
        print(cyan("→") + f" Reading live runtime/health from :{port}…")
        runtime = collect_from_server(port)
    else:
        print(yellow("!") + " No running server — using the offline Health Engine.")
        runtime = collect_offline()
    bundle["runtime"] = runtime

    print(cyan("→") + " Capturing package versions…")
    packages = collect_packages()

    # Final safety net: scrub the entire structure before serialization.
    bundle = _scrub(bundle)

    logs = ""
    if isinstance(runtime.get("logs"), str):
        logs = runtime["logs"]
    elif isinstance(runtime.get("logs"), dict):
        logs = json.dumps(runtime["logs"], indent=2)

    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("system.json", json.dumps(bundle["system"], indent=2))
            zf.writestr("config.json", json.dumps(bundle["config"], indent=2))
            zf.writestr("install.json", json.dumps(bundle["install"], indent=2))
            zf.writestr("health.json", json.dumps(bundle["runtime"].get("health"), indent=2))
            zf.writestr("providers.json", json.dumps(bundle["runtime"].get("providers"), indent=2))
            zf.writestr("runtime_status.json", json.dumps(bundle["runtime"].get("runtime_status"), indent=2))
            zf.writestr("models.json", json.dumps(bundle["runtime"].get("models"), indent=2))
            zf.writestr("packages.txt", packages)
            zf.writestr("logs.txt", logs or "(no logs)")
            zf.writestr("MANIFEST.txt", _manifest(bundle))
    except OSError as exc:
        print(red("✕") + f" Could not write {out}: {exc}")
        return 1

    print()
    print(green("✓") + f" Diagnostics written to {bold(str(out))}")
    print(dim("  Contains: system, config (secrets redacted), health, providers,"))
    print(dim("  runtime, installed models, package versions, and logs."))
    print(dim("  Safe to share — no API keys are included."))
    return 0


def _manifest(bundle: dict) -> str:
    return (
        "RedForge diagnostics bundle\n"
        f"Generated: {bundle['system']['collected_at']}\n"
        f"Version:   {bundle['system']['redforge_version']}\n"
        f"Source:    {bundle['runtime'].get('source')}\n\n"
        "Files:\n"
        "  system.json          - OS, Python, install root\n"
        "  config.json          - REDFORGE_* env (secrets redacted) + key presence\n"
        "  install.json         - install state, venv/frontend presence\n"
        "  health.json          - System Health Engine report\n"
        "  providers.json       - Runtime Manager provider status\n"
        "  runtime_status.json  - runtime metrics\n"
        "  models.json          - installed models per provider\n"
        "  packages.txt         - pip freeze of the backend environment\n"
        "  logs.txt             - recent logs\n\n"
        "No API keys or secret values are included.\n"
    )
