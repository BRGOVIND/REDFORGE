"""Centralized, structured logging.

One place configures the root logger; everywhere else calls ``get_logger`` and
the ``log_op`` helper, which attaches consistent context — operation, session,
model, and duration — to every line. Timestamp and severity come from the
formatter. Example line::

    2026-07-06 10:12:04 INFO     redforge.pipeline  op=run session=b674b793 model=llama3:8b duration=12.44s | evaluation completed
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

_configured = False

# Bounded in-memory ring buffer of recent log records, so the Runtime Manager can
# expose read-only logs over the API without touching disk or the CLI log file.
_LOG_BUFFER: "deque[dict]" = deque(maxlen=1000)


class _RingBufferHandler(logging.Handler):
    """Capture each ``redforge`` log record as a small dict in ``_LOG_BUFFER``."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _LOG_BUFFER.append(
                {
                    "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
            )
        except Exception:  # noqa: BLE001 - logging must never raise
            pass


def get_recent_logs(limit: int = 200) -> list[dict]:
    """Return up to ``limit`` most-recent captured log lines (oldest → newest)."""
    limit = max(1, min(limit, _LOG_BUFFER.maxlen or 1000))
    items = list(_LOG_BUFFER)
    return items[-limit:]


def configure_logging() -> None:
    """Idempotently configure the ``redforge`` logger hierarchy."""
    global _configured
    if _configured:
        return
    logger = logging.getLogger("redforge")
    logger.setLevel(settings.LOG_LEVEL.upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.addHandler(_RingBufferHandler())
    logger.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced child logger, e.g. ``get_logger("pipeline")``."""
    return logging.getLogger(f"redforge.{name}")


def log_op(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    op: Optional[str] = None,
    session: Optional[str] = None,
    model: Optional[str] = None,
    duration: Optional[float] = None,
) -> None:
    """Emit a log line with standardized context fields prepended."""
    parts: list[str] = []
    if op:
        parts.append(f"op={op}")
    if session:
        parts.append(f"session={session[:8]}")
    if model:
        parts.append(f"model={model}")
    if duration is not None:
        parts.append(f"duration={duration:.2f}s")
    context = " ".join(parts)
    logger.log(level, f"{context} | {message}" if context else message)
