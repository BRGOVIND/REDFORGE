"""Centralized, structured logging.

One place configures the root logger; everywhere else calls ``get_logger`` and
the ``log_op`` helper, which attaches consistent context — operation, session,
model, and duration — to every line. Timestamp and severity come from the
formatter. Example line::

    2026-07-06 10:12:04 INFO     redforge.pipeline  op=run session=b674b793 model=llama3:8b duration=12.44s | evaluation completed
"""
from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

_configured = False


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
