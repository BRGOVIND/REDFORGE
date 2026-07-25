"""Real Ollama model creation (opt-in, CLI-only).

The concrete counterpart to :class:`OllamaExportProvider`, isolated so the ``ollama``
CLI is invoked only when real export is explicitly enabled
(``REDFORGE_ENABLE_REAL_EXPORT=1``) AND the CLI is present. Never imported on the
default (simulated) path and never imported in CI — hence ``# pragma: no cover``.

Local-first (Constitution §9/§10.8): shells out to the ``ollama`` CLI exactly as a
human operator would; never imports the Runtime Engine.
"""
from __future__ import annotations

import shutil
import subprocess


def ollama_create(model_name: str, modelfile_path: str) -> str:  # pragma: no cover - requires the local ollama CLI
    """Register a runtime model with Ollama from a generated Modelfile via
    ``ollama create <name> -f <Modelfile>``. Raises on failure so the export Job
    surfaces the real error verbatim (never a silent success)."""
    ollama = shutil.which("ollama")
    if not ollama:
        raise FileNotFoundError("ollama CLI not found on PATH")
    subprocess.run([ollama, "create", model_name, "-f", modelfile_path], check=True)
    return model_name
