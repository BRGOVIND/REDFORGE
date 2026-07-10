"""Centralized configuration — the single source of truth for tunables.

Every value has a sensible default and can be overridden with an environment
variable (prefix ``REDFORGE_``). Modules import ``settings`` from here instead of
hardcoding URLs, timeouts, and thresholds. Defaults are identical to the values
that were previously scattered across the codebase, so importing this changes no
behavior.
"""
from __future__ import annotations

import os


def _str(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    # --- Ollama -----------------------------------------------------------
    OLLAMA_BASE_URL: str = _str("REDFORGE_OLLAMA_URL", "http://localhost:11434")
    # Long timeout for generation/inference calls.
    OLLAMA_TIMEOUT: float = _float("REDFORGE_OLLAMA_TIMEOUT", 60.0)
    # Short timeout for quick metadata calls (/api/tags used by health checks).
    OLLAMA_TAGS_TIMEOUT: float = _float("REDFORGE_OLLAMA_TAGS_TIMEOUT", 5.0)
    # Timeout for /api/show (model capability detection).
    OLLAMA_SHOW_TIMEOUT: float = _float("REDFORGE_OLLAMA_SHOW_TIMEOUT", 15.0)
    # Very short timeout for the first-run system check (keep the wizard snappy).
    OLLAMA_HEALTH_TIMEOUT: float = _float("REDFORGE_OLLAMA_HEALTH_TIMEOUT", 2.5)

    # --- Runtime (unified LLM layer) -------------------------------------
    # Which provider backs the runtime. Built-ins: ollama (default), lmstudio,
    # llamacpp, vllm, openai, anthropic, gemini, groq, openrouter.
    RUNTIME_PROVIDER: str = _str("REDFORGE_RUNTIME_PROVIDER", "ollama")
    # Provider-agnostic HTTP timeouts used by the non-Ollama providers. Each
    # provider owns its own base URL / API key via convention env vars (see
    # app/runtime/providers), so adding a provider needs no new setting here.
    RUNTIME_READ_TIMEOUT: float = _float("REDFORGE_RUNTIME_READ_TIMEOUT", 120.0)
    RUNTIME_METADATA_TIMEOUT: float = _float("REDFORGE_RUNTIME_METADATA_TIMEOUT", 10.0)
    # Max concurrent generations PER MODEL (1 = serialize, don't hammer Ollama).
    RUNTIME_CONCURRENCY: int = _int("REDFORGE_RUNTIME_CONCURRENCY", 1)
    # Timeouts (seconds).
    RUNTIME_CONNECT_TIMEOUT: float = _float("REDFORGE_RUNTIME_CONNECT_TIMEOUT", 10.0)
    RUNTIME_IDLE_TIMEOUT: float = _float("REDFORGE_RUNTIME_IDLE_TIMEOUT", 300.0)
    # Retries on transient connection failures (not on timeouts/cancels).
    RUNTIME_RETRY_COUNT: int = _int("REDFORGE_RUNTIME_RETRY_COUNT", 1)
    RUNTIME_RETRY_BACKOFF: float = _float("REDFORGE_RUNTIME_RETRY_BACKOFF", 0.5)
    # How long /api/tags and /api/show results stay cached (seconds).
    MODEL_CACHE_TTL: float = _float("REDFORGE_MODEL_CACHE_TTL", 30.0)

    # --- Adaptive execution ----------------------------------------------
    # How often to emit a heartbeat while awaiting a slow model response.
    HEARTBEAT_INTERVAL: float = _float("REDFORGE_HEARTBEAT_INTERVAL", 4.0)

    # --- Runtime estimation ----------------------------------------------
    # Fallback per-call latency when a model has no history yet.
    DEFAULT_LATENCY_MS: float = _float("REDFORGE_DEFAULT_LATENCY_MS", 4000.0)

    # --- Planner ----------------------------------------------------------
    # A model at/above this historical security score is treated as "robust".
    ROBUST_SCORE_THRESHOLD: float = _float("REDFORGE_ROBUST_SCORE_THRESHOLD", 80.0)

    # --- Resource detection ----------------------------------------------
    GPU_PROBE_TIMEOUT: float = _float("REDFORGE_GPU_PROBE_TIMEOUT", 2.0)

    # --- HTTP server ------------------------------------------------------
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in _str(
            "REDFORGE_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]

    # --- Database ---------------------------------------------------------
    # SQLAlchemy async URL. Default preserves the historical CWD-relative
    # SQLite path exactly; override with REDFORGE_DATABASE_URL (e.g. to pin an
    # absolute path independent of the launch directory).
    DATABASE_URL: str = _str("REDFORGE_DATABASE_URL", "sqlite+aiosqlite:///./redforge.db")

    # --- Logging ----------------------------------------------------------
    LOG_LEVEL: str = _str("REDFORGE_LOG_LEVEL", "INFO")


settings = Settings()
