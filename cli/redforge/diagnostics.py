"""System diagnostics for `redforge doctor` — green / yellow / red checks.

Dependency-light: standard library only, with an optional best-effort import of
the backend's cross-platform resource monitor for RAM/GPU/disk.
"""
from __future__ import annotations

import json
import platform
import shutil
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass

from . import paths

OLLAMA_URL = "http://localhost:11434"
RECOMMENDED_MODELS = ["qwen3:8b", "llama3", "gemma", "mistral"]
MIN_PYTHON = (3, 11)


@dataclass
class Check:
    label: str
    level: str  # "ok" | "warn" | "fail"
    detail: str = ""


def _http_json(url: str, timeout: float = 2.5):
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - localhost
        return json.loads(resp.read().decode())


def _cmd_version(exe: str) -> str | None:
    if shutil.which(exe) is None:
        return None
    try:
        out = subprocess.check_output([exe, "--version"], stderr=subprocess.STDOUT, timeout=5)
        return out.decode(errors="ignore").strip().splitlines()[0]
    except Exception:
        return None


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _resources() -> dict:
    """Best-effort RAM/GPU/disk via the backend monitor; empty dict on failure."""
    try:
        sys.path.insert(0, str(paths.backend_dir()))
        from app.resources.resource_monitor import detect_resources  # type: ignore

        return detect_resources().to_dict()
    except Exception:
        return {}


def collect() -> list[Check]:
    checks: list[Check] = []

    # Python
    v = sys.version_info
    py_ok = (v.major, v.minor) >= MIN_PYTHON
    checks.append(Check("Python", "ok" if py_ok else "fail",
                        f"{v.major}.{v.minor}.{v.micro}" + ("" if py_ok else f" (need ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")))

    # OS
    checks.append(Check("Operating System", "ok", f"{platform.system()} {platform.release()}"))

    # Node (developer-only)
    node = _cmd_version("node")
    checks.append(Check("Node.js (dev only)", "ok" if node else "warn",
                        node or "not found — only needed to build from source"))

    # Git (optional)
    git = _cmd_version("git")
    checks.append(Check("Git (optional)", "ok" if git else "warn", git or "not found"))

    res = _resources()
    # RAM
    ram = res.get("ram_available_mb")
    if ram is not None:
        checks.append(Check("RAM", "ok" if ram >= 2000 else "warn",
                            f"{ram} MB available of {res.get('ram_total_mb', '?')} MB"))
    # GPU
    gpu = res.get("gpu") or {}
    checks.append(Check("GPU", "ok" if gpu.get("available") else "warn",
                        gpu.get("name") or "none — evaluations run on CPU"))
    # Disk
    disk = res.get("disk_free_mb")
    if disk is None:
        try:
            disk = shutil.disk_usage(str(paths.root())).free // (1024 * 1024)
        except Exception:
            disk = None
    if disk is not None:
        checks.append(Check("Disk", "ok" if disk >= 1000 else "warn", f"{disk} MB free"))

    # Ollama installed / running / models
    ollama_installed = shutil.which("ollama") is not None
    checks.append(Check("Ollama installed", "ok" if ollama_installed else "fail",
                        "found" if ollama_installed else "not installed — https://ollama.com/download"))
    models: list[str] = []
    running = False
    try:
        data = _http_json(f"{OLLAMA_URL}/api/tags")
        running = True
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        running = False
    checks.append(Check("Ollama running", "ok" if running else "fail",
                        "reachable on :11434" if running else "not running — run: ollama serve"))
    checks.append(Check("Models installed", "ok" if models else ("warn" if running else "fail"),
                        ", ".join(models) if models else f"none — try: ollama pull {RECOMMENDED_MODELS[0]}"))

    # Database
    checks.append(Check("Database", "ok" if paths.db_path().exists() else "warn",
                        "initialized" if paths.db_path().exists() else "will be created on first start"))

    # Datasets
    bench = paths.datasets_dir() / "redforge-bench-v1"
    files = list(bench.glob("*.json")) if bench.is_dir() else []
    checks.append(Check("Benchmark dataset", "ok" if len(files) >= 5 else "fail",
                        f"{len(files)} category files" if files else "missing"))

    # Ports
    checks.append(Check("Port 8000 (app)", "ok" if not _port_in_use(8000) else "warn",
                        "free" if not _port_in_use(8000) else "in use — RedForge may already be running"))

    return checks


def is_ready(checks: list[Check]) -> bool:
    blocking = {"Python", "Ollama installed", "Ollama running", "Models installed", "Benchmark dataset"}
    return all(c.level != "fail" for c in checks if c.label in blocking)


def as_plaintext(checks: list[Check]) -> str:
    lines = [f"RedForge Diagnostics ({platform.system()})", "=" * 40]
    for c in checks:
        mark = {"ok": "[OK]", "warn": "[!!]", "fail": "[XX]"}[c.level]
        lines.append(f"{mark} {c.label}: {c.detail}")
    return "\n".join(lines)
