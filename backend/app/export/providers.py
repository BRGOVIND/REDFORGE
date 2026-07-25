"""Export providers (RedForge V3, Epic 3).

One provider per target runtime (Constitution §9, §10.8). Each converts an
inference-domain artifact into the next form and reports whether it used real native
tooling or the honest simulated/dev path (§2.14). Registered in a flat registry;
LM Studio / llama.cpp / vLLM are architecture-ready future providers.

Local-first: providers shell out to the target runtime's OWN tooling (``ollama``,
llama.cpp's converter) exactly as a human operator would — they never import the
Runtime Engine.
"""
from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional


def _write_manifest(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _real_export_enabled() -> bool:
    """Real export needs BOTH the native toolchain AND real merged weights (a GPU
    merge — not produced in Epic 3), so the real path is opt-in via an explicit
    env flag. Default off → the pipeline runs simulated (honest, fully local, testable).
    Flipping this on is for when real GPU merge + the toolchain are both present."""
    return os.environ.get("REDFORGE_ENABLE_REAL_EXPORT") == "1"


class ExportProvider(ABC):
    name: str = "export"
    target: str = ""

    @abstractmethod
    def is_available(self) -> tuple[bool, str]: ...

    @abstractmethod
    def run(self, *, source_path: str, workdir: str, config) -> dict:
        """Perform this provider's step. Returns
        ``{"output_path", "simulated": bool, "runtime_model_name"?: str, "note": str}``."""
        ...


class GGUFExportProvider(ExportProvider):
    """Merged model → GGUF. Uses llama.cpp's converter when present; otherwise writes
    an honest placeholder GGUF manifest (simulated) so the pipeline + artifact lineage
    are fully exercisable locally without the toolchain."""

    name = "gguf"
    target = "gguf"

    def is_available(self) -> tuple[bool, str]:
        # A real conversion needs llama.cpp's convert + quantize tools.
        if shutil.which("llama-quantize") or os.environ.get("REDFORGE_LLAMACPP_DIR"):
            return True, "llama.cpp tooling detected"
        return False, "llama.cpp converter not found — GGUF export runs in simulated mode"

    def run(self, *, source_path: str, workdir: str, config) -> dict:
        out = os.path.join(workdir, f"model.{config.quantization}.gguf")
        ok, _ = self.is_available()
        if ok and _real_export_enabled():  # pragma: no cover - requires the local llama.cpp toolchain
            from app.export._gguf_impl import convert_to_gguf
            convert_to_gguf(source_path, out, config.quantization)
            return {"output_path": out, "simulated": False, "note": "converted with llama.cpp"}
        _write_manifest(out, {"format": "gguf", "quantization": config.quantization,
                              "source": source_path, "simulated": True})
        return {"output_path": out, "simulated": True,
                "note": "simulated GGUF (llama.cpp toolchain not installed)"}


class OllamaExportProvider(ExportProvider):
    """GGUF → Ollama runtime model via ``ollama create`` + a generated Modelfile.
    Simulated when the ``ollama`` CLI is absent."""

    name = "ollama"
    target = "ollama"

    def is_available(self) -> tuple[bool, str]:
        if shutil.which("ollama"):
            return True, "ollama CLI detected"
        return False, "ollama CLI not found — Ollama import runs in simulated mode"

    def run(self, *, source_path: str, workdir: str, config) -> dict:
        model_name = config.model_name or f"redforge-{os.path.basename(workdir)[:8]}"
        modelfile = os.path.join(workdir, "Modelfile")
        _write_manifest(modelfile, {"FROM": source_path, "model_name": model_name})
        ok, _ = self.is_available()
        if ok and _real_export_enabled():  # pragma: no cover - requires the local ollama CLI
            from app.export._ollama_impl import ollama_create
            ollama_create(model_name, modelfile)
            return {"output_path": source_path, "runtime_model_name": model_name,
                    "simulated": False, "note": f"created Ollama model '{model_name}'"}
        return {"output_path": source_path, "runtime_model_name": model_name, "simulated": True,
                "note": f"simulated Ollama import as '{model_name}' (ollama CLI not installed)"}


_PROVIDERS: dict[str, ExportProvider] = {p.target: p for p in (GGUFExportProvider(), OllamaExportProvider())}


def register_export_provider(provider: ExportProvider) -> None:
    _PROVIDERS[provider.target] = provider


def get_export_provider(target: str) -> Optional[ExportProvider]:
    return _PROVIDERS.get(target)


def list_export_providers() -> list[dict]:
    known = list(_PROVIDERS.values())
    out = [{"target": p.target, "name": p.name, **dict(zip(("available", "reason"), p.is_available()))}
           for p in known]
    # Architecture-ready future targets, honestly flagged as not-yet-implemented.
    for t in ("lmstudio", "llamacpp", "vllm"):
        if t not in _PROVIDERS:
            out.append({"target": t, "name": t, "available": False,
                        "reason": "provider not yet implemented (architecture-ready)"})
    return out
