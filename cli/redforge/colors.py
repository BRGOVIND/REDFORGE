"""Tiny cross-platform ANSI color helpers (no dependencies)."""
from __future__ import annotations

import os
import sys

# Make output UTF-8 safe so status glyphs (✓ ⚠ ✕ ●) never crash a cp1252 console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if os.name == "nt":  # enable ANSI on modern Windows terminals
    os.system("")


def _wrap(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ENABLED else text


def green(t: str) -> str:
    return _wrap("32", t)


def yellow(t: str) -> str:
    return _wrap("33", t)


def red(t: str) -> str:
    return _wrap("31", t)


def cyan(t: str) -> str:
    return _wrap("36", t)


def dim(t: str) -> str:
    return _wrap("2", t)


def bold(t: str) -> str:
    return _wrap("1", t)


# Status glyph + color by level.
def status_mark(level: str) -> str:
    return {"ok": green("✓"), "warn": yellow("⚠"), "fail": red("✕")}.get(level, "•")
