"""Smoke/regression tests for the redforge CLI (runs inside the backend suite)."""
from __future__ import annotations

import sys
from pathlib import Path

# The CLI package lives under ../cli — make it importable for these tests.
_CLI = Path(__file__).resolve().parent.parent.parent / "cli"
if str(_CLI) not in sys.path:
    sys.path.insert(0, str(_CLI))

import pytest

from redforge import diagnostics, paths  # noqa: E402
from redforge.cli import _version, build_parser, main  # noqa: E402

EXPECTED_COMMANDS = {
    "version", "doctor", "start", "stop", "status", "logs",
    "models", "evaluate", "benchmark", "install", "update",
}


def _version_file() -> str:
    return (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()


def test_version_matches_version_file():
    """VERSION is the single source of truth — no literal may drift from it."""
    assert _version() == _version_file()


def test_cli_package_version_matches_version_file():
    from redforge import __version__

    assert __version__ == _version_file()


def test_parser_exposes_all_commands():
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    assert EXPECTED_COMMANDS.issubset(set(sub.choices))


def test_main_version_runs(capsys):
    rc = main(["version"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RedForge" in out and _version_file() in out


def test_paths_root_resolves_to_repo():
    root = paths.root()
    assert (root / "backend").is_dir()
    assert (root / "cli").is_dir()
    assert (root / "VERSION").is_file()


def test_diagnostics_collect_returns_valid_checks():
    # doctor now consumes the centralized System Health Engine (provider-agnostic).
    checks = diagnostics.collect()
    assert checks, "doctor produced no checks"
    labels = {c.label for c in checks}
    assert "Python" in labels
    assert all(c.level in ("ok", "warn", "fail") for c in checks)
    assert all(c.severity in ("critical", "high", "medium", "low", "info") for c in checks)
