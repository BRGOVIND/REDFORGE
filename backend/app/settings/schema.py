"""Settings schema — the single, data-driven definition of every user setting.

Adding a setting is one entry here (key, category, type, default, …). The service
persists overrides, the API groups by category, and the UI renders controls from the
``type``. This keeps "every important path and behavior configurable" without bespoke
code per setting. Defaults mirror the env-driven ``app.config`` so nothing changes
until a user opts in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _home() -> str:
    return os.environ.get("REDFORGE_HOME") or str(Path.home() / ".redforge")


@dataclass(frozen=True)
class Setting:
    key: str                       # dotted, unique
    category: str
    label: str
    type: str                      # bool | int | float | string | enum | path | secret
    default: Any
    description: str = ""
    options: Optional[list] = None   # for enum
    min: Optional[float] = None
    max: Optional[float] = None
    unit: str = ""
    advanced: bool = False           # hidden unless "show advanced"
    restart: bool = False            # requires a restart to take effect

    def to_dict(self) -> dict:
        return {
            "key": self.key, "category": self.category, "label": self.label,
            "type": self.type, "default": self.default, "description": self.description,
            "options": self.options, "min": self.min, "max": self.max, "unit": self.unit,
            "advanced": self.advanced, "restart": self.restart,
        }


# Categories in display order (label + short blurb).
CATEGORIES = [
    ("general", "General", "Startup, confirmations, and language."),
    ("appearance", "Appearance", "Theme, density, and motion."),
    ("workspace", "Workspace", "Where projects and data live."),
    ("downloads", "Downloads", "Model download behavior and location."),
    ("models", "Models", "Model storage and defaults."),
    ("datasets", "Datasets", "Dataset storage and import."),
    ("training", "Training", "Fine-tuning defaults (Experimental)."),
    ("runtimes", "Runtimes", "Runtime providers and endpoints."),
    ("hardware", "Hardware", "GPU detection and memory."),
    ("performance", "Performance", "Concurrency, polling, and caching."),
    ("networking", "Networking", "Proxy, tokens, and offline mode."),
    ("updates", "Updates", "Auto-update behavior."),
    ("experimental", "Experimental Features", "Opt-in, unfinished features."),
    ("developer", "Developer Options", "Debugging and internals."),
    ("diagnostics", "Diagnostics", "Logging and support bundles."),
]

_S = Setting
SCHEMA: list[Setting] = [
    # General
    _S("general.open_last_page", "general", "Reopen last page on launch", "bool", True),
    _S("general.confirm_destructive", "general", "Confirm destructive actions", "bool", True,
       "Ask before deleting runs, datasets, or models."),
    _S("general.language", "general", "Language", "enum", "en", options=["en"]),

    # Appearance
    _S("appearance.theme", "appearance", "Theme", "enum", "dark", options=["dark", "light", "system"]),
    _S("appearance.density", "appearance", "Density", "enum", "comfortable", options=["comfortable", "compact"]),
    _S("appearance.reduce_motion", "appearance", "Reduce motion", "bool", False,
       "Minimize animations and transitions."),

    # Workspace
    _S("workspace.dir", "workspace", "Workspace directory", "path", _home(),
       "Root folder for projects, runs, and local state.", restart=True),
    _S("workspace.default_project", "workspace", "Default project", "string", "",
       "Project selected on launch (blank = none)."),

    # Downloads
    _S("downloads.dir", "downloads", "Download directory", "path", str(Path(_home()) / "downloads")),
    _S("downloads.prefer_source", "downloads", "Preferred source", "enum", "huggingface",
       "Where one-click downloads pull from by default.", options=["huggingface", "ollama"]),
    _S("downloads.concurrent", "downloads", "Concurrent downloads", "int", 2, min=1, max=6),
    _S("downloads.verify_checksums", "downloads", "Verify files after download", "bool", True),

    # Models
    _S("models.dir", "models", "Model directory", "path", str(Path(_home()) / "models")),
    _S("models.default_runtime_model", "models", "Default runtime model", "string", ""),

    # Datasets
    _S("datasets.dir", "datasets", "Dataset directory", "path", str(Path(_home()) / "datasets")),
    _S("datasets.max_import_mb", "datasets", "Max import size", "int", 512, unit="MB", min=1, max=100000),

    # Training (Experimental)
    _S("training.enabled", "training", "Enable training", "bool", True,
       "Training is Experimental; disable to hide it."),
    # "auto" picks the best backend that is actually usable on this machine.
    # Never default this to a concrete backend: settings are authoritative, so a
    # hardcoded "simulation" here would force simulated runs on a capable GPU.
    _S("training.default_backend", "training", "Default backend", "enum", "auto",
       "auto uses the real training runtime when it is installed, and simulation otherwise.",
       options=["auto", "simulation", "managed", "unsloth", "transformers"]),
    _S("training.default_strategy", "training", "Default strategy", "enum", "qlora",
       options=["lora", "qlora", "sft"]),
    _S("training.default_max_seq_length", "training", "Default max sequence length", "int", 2048, min=128, max=131072),
    _S("training.default_batch_size", "training", "Default batch size", "int", 2, min=1, max=256),

    # Runtimes
    _S("runtimes.default_provider", "runtimes", "Default provider", "enum", "ollama",
       options=["ollama", "lmstudio", "llamacpp", "openai", "anthropic", "gemini"]),
    _S("runtimes.ollama_base_url", "runtimes", "Ollama base URL", "string", "http://localhost:11434"),
    _S("runtimes.request_timeout", "runtimes", "Request timeout", "int", 60, unit="s", min=5, max=600),

    # Hardware
    _S("hardware.gpu_enabled", "hardware", "Use GPU when available", "bool", True),
    _S("hardware.vram_override_mb", "hardware", "VRAM override", "int", 0,
       description="0 = auto-detect. Set to cap the memory the estimator assumes.",
       unit="MB", min=0, max=200000, advanced=True),
    _S("hardware.auto_safe_defaults", "hardware", "Auto-apply safe training defaults", "bool", True,
       "When a model is tight, reduce sequence/batch automatically."),

    # Performance
    _S("performance.max_concurrent_jobs", "performance", "Max concurrent tasks", "int", 8, min=1, max=32),
    _S("performance.task_poll_ms", "performance", "Task panel refresh", "int", 1500, unit="ms", min=500, max=10000),
    _S("performance.cache_limit_mb", "performance", "Cache size limit", "int", 2048, unit="MB", min=64, max=100000),

    # Networking
    _S("networking.offline", "networking", "Offline mode", "bool", False,
       "Never reach the network (downloads/updates disabled)."),
    _S("networking.proxy_url", "networking", "HTTP proxy", "string", "", advanced=True),
    _S("networking.hf_token", "networking", "Hugging Face token", "secret", "",
       "Used for gated/private model downloads. Stored locally."),

    # Updates
    _S("updates.auto_check", "updates", "Automatically check for updates", "bool", True),
    _S("updates.channel", "updates", "Update channel", "enum", "stable", options=["stable", "beta"]),

    # Experimental
    _S("experimental.real_training", "experimental", "Real GPU training", "bool", False,
       "Use the real Unsloth/Transformers backend instead of simulation."),
    _S("experimental.plugins", "experimental", "Plugin loading", "bool", False,
       "Load third-party plugins (Plugin Architecture)."),

    # Developer
    _S("developer.debug_logging", "developer", "Debug logging", "bool", False, restart=True),
    _S("developer.show_advanced", "developer", "Show advanced settings", "bool", False),
    _S("developer.api_base", "developer", "API base URL", "string", "", advanced=True),

    # Diagnostics
    _S("diagnostics.log_level", "diagnostics", "Log level", "enum", "info",
       options=["error", "warning", "info", "debug"], restart=True),
    _S("diagnostics.telemetry", "diagnostics", "Anonymous telemetry", "bool", False,
       "Off by default. RedForge never sends usage data unless you enable this."),
]

_BY_KEY = {s.key: s for s in SCHEMA}
_SECRET_KEYS = {s.key for s in SCHEMA if s.type == "secret"}


def get_def(key: str) -> Optional[Setting]:
    return _BY_KEY.get(key)


def is_secret(key: str) -> bool:
    return key in _SECRET_KEYS


def defaults() -> dict:
    return {s.key: s.default for s in SCHEMA}
