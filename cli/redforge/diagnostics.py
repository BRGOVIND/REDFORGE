"""System diagnostics for `redforge doctor`.

The checks themselves are NOT implemented here — this module is a thin consumer of
the backend's centralized **System Health Engine** (``app.health``), the single
source of truth. It runs the engine in-process and maps its structured report to
the CLI's green / yellow / red rows.

If the backend dependencies aren't importable yet (a fresh clone, before
``redforge install``), it falls back to a minimal stdlib bootstrap so
``redforge doctor`` still runs and can tell you what to install.
"""
from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass

from . import paths

RECOMMENDED_MODELS = ["qwen3:8b", "llama3", "gemma", "mistral"]
MIN_PYTHON = (3, 11)

# Engine status -> CLI level.
_LEVEL = {"healthy": "ok", "warning": "warn", "error": "fail"}
_BLOCKING = {"critical", "high"}


@dataclass
class Check:
    label: str
    level: str  # "ok" | "warn" | "fail"
    detail: str = ""
    severity: str = "medium"
    id: str = ""


# ---------------------------------------------------------------------------
# Engine consumption
# ---------------------------------------------------------------------------

def _run_engine() -> list[Check] | None:
    """Run the centralized health engine in-process; None if unavailable."""
    import asyncio
    import os

    prev_cwd = os.getcwd()
    try:
        backend = str(paths.backend_dir())
        if backend not in sys.path:
            sys.path.insert(0, backend)
        # Run from the backend dir so cwd-relative checks (DB/permissions) reflect
        # where the backend actually runs — not the user's shell directory.
        os.chdir(backend)
        from app.health import health_service  # type: ignore

        report = asyncio.run(health_service.run())
    except Exception:
        return None
    finally:
        try:
            os.chdir(prev_cwd)
        except OSError:
            pass

    checks: list[Check] = []
    for c in report.checks:
        detail = c.message
        if c.suggested_fix and c.status != "healthy":
            detail = f"{detail} — {c.suggested_fix}"
        checks.append(
            Check(
                label=c.name,
                level=_LEVEL.get(c.status, "warn"),
                detail=detail,
                severity=c.severity,
                id=c.id,
            )
        )
    return checks


# ---------------------------------------------------------------------------
# Bootstrap fallback (stdlib only — used only before deps are installed)
# ---------------------------------------------------------------------------

def _bootstrap() -> list[Check]:
    checks: list[Check] = []
    v = sys.version_info
    py_ok = (v.major, v.minor) >= MIN_PYTHON
    checks.append(Check(
        "Python", "ok" if py_ok else "fail",
        f"{v.major}.{v.minor}.{v.micro}" + ("" if py_ok else f" (need ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]})"),
        severity="critical", id="python_version",
    ))
    checks.append(Check(
        "Operating System", "ok", f"{platform.system()} {platform.release()}",
        severity="info", id="os",
    ))
    # Pre-install bootstrap: the Runtime Manager isn't importable yet, so we can
    # only do a best-effort presence check for a local runtime on PATH. The full,
    # provider-agnostic health check runs via the Health Engine once deps exist.
    runtime = next((r for r in ("ollama", "lms", "llama-server", "vllm") if shutil.which(r)), None)
    checks.append(Check(
        "Runtime", "ok" if runtime else "warn",
        f"{runtime} found on PATH" if runtime
        else "no local runtime found — install one (Ollama recommended: https://ollama.com/download)",
        severity="high", id="provider_health",
    ))
    checks.append(Check(
        "Backend dependencies", "warn",
        "not installed yet — run: redforge install",
        severity="high", id="deps",
    ))
    return checks


# ---------------------------------------------------------------------------
# Public surface (unchanged for cli.py)
# ---------------------------------------------------------------------------

def collect() -> list[Check]:
    return _run_engine() or _bootstrap()


def is_ready(checks: list[Check]) -> bool:
    """Ready when no blocking (critical/high) check has failed."""
    return not any(c.level == "fail" and c.severity in _BLOCKING for c in checks)


def as_plaintext(checks: list[Check]) -> str:
    lines = [f"RedForge Diagnostics ({platform.system()})", "=" * 40]
    for c in checks:
        mark = {"ok": "[OK]", "warn": "[!!]", "fail": "[XX]"}[c.level]
        lines.append(f"{mark} {c.label}: {c.detail}")
    return "\n".join(lines)
