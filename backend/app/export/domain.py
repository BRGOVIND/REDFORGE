"""Export Engine — pure domain model (RedForge V3, Epic 3).

Turns training-domain artifacts (checkpoints/adapters) into inference-domain runtime
artifacts (merged model → GGUF → runtime model), via pluggable export providers,
executed as Jobs (Constitution §3.9, §10.8). Pure: no SQLAlchemy, no FastAPI.

Export uses target runtimes' *native tooling* (e.g. ``ollama create``) — it never
imports the Runtime Engine (§11.2). It produces artifacts; it does not serve models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ExportTarget(str, Enum):
    GGUF = "gguf"
    OLLAMA = "ollama"
    # Architecture-ready future targets (providers not yet implemented):
    LMSTUDIO = "lmstudio"
    LLAMACPP = "llamacpp"
    VLLM = "vllm"


@dataclass
class ExportConfiguration:
    """What to export and how. ``source_artifact_id`` is a checkpoint or adapter;
    ``target`` selects the export provider; ``quantization`` applies to GGUF."""
    source_artifact_id: str
    target: str = "gguf"
    base_model: str = ""
    quantization: str = "q4_k_m"
    model_name: Optional[str] = None            # runtime model name (e.g. Ollama tag)

    def to_dict(self) -> dict:
        return {"source_artifact_id": self.source_artifact_id, "target": self.target,
                "base_model": self.base_model, "quantization": self.quantization,
                "model_name": self.model_name}


@dataclass
class ExportResult:
    success: bool = True
    target: str = ""
    merged_model_artifact_id: Optional[str] = None
    gguf_artifact_id: Optional[str] = None
    runtime_model_artifact_id: Optional[str] = None
    runtime_model_name: Optional[str] = None
    message: str = ""
    simulated: bool = False                      # True when produced by the mock/dev path

    def artifact_ids(self) -> list[str]:
        return [a for a in (self.merged_model_artifact_id, self.gguf_artifact_id,
                            self.runtime_model_artifact_id) if a]

    def to_dict(self) -> dict:
        return {"success": self.success, "target": self.target,
                "merged_model_artifact_id": self.merged_model_artifact_id,
                "gguf_artifact_id": self.gguf_artifact_id,
                "runtime_model_artifact_id": self.runtime_model_artifact_id,
                "runtime_model_name": self.runtime_model_name,
                "message": self.message, "simulated": self.simulated,
                "artifact_ids": self.artifact_ids()}
