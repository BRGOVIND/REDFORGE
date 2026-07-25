"""Artifact type registry (RedForge V3, Epic 2).

Artifact types are **extensible without architecture change** (the Epic's explicit
requirement). Known types are registered descriptors; unknown types are accepted as
free-form strings and default to a safe shape. This mirrors the provider-registry
pattern used everywhere else in RedForge — a new type is a registration (or simply a
new string), never an edit to the registry engine or the Artifact aggregate.

Each type declares its **backing** (Constitution §6.3):
- ``file``  — bytes on disk; the registry owns location + checksum + size.
- ``data``  — a row in an owning context's table; the registry holds a thin
  reference (``table_ref``). No data migration for existing subsystems.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactTypeDef:
    key: str
    label: str
    backing: str            # "file" | "data"
    category: str           # "model" | "dataset" | "result" | "report" | "misc"

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label,
                "backing": self.backing, "category": self.category}


# Canonical known types (Constitution §6.3 + the Epic's list). This set is the
# *default* registry; it is not a closed universe — see ``get_artifact_type``.
_KNOWN: dict[str, ArtifactTypeDef] = {}


def register_artifact_type(defn: ArtifactTypeDef) -> None:
    """Register (or override) a known artifact type. First-party types are
    registered below; plugins/later epics register more the same way."""
    _KNOWN[defn.key] = defn


def _seed() -> None:
    for defn in (
        ArtifactTypeDef("foundation_model", "Foundation Model", "data", "model"),
        ArtifactTypeDef("runtime_model", "Runtime Model", "data", "model"),
        ArtifactTypeDef("dataset", "Dataset", "data", "dataset"),
        ArtifactTypeDef("training_run", "Training Run", "data", "result"),
        ArtifactTypeDef("checkpoint", "Checkpoint", "file", "model"),
        ArtifactTypeDef("adapter", "LoRA Adapter", "file", "model"),
        ArtifactTypeDef("merged_model", "Merged Model", "file", "model"),
        ArtifactTypeDef("gguf", "GGUF Export", "file", "model"),
        ArtifactTypeDef("report", "Engineering Report", "data", "report"),
        ArtifactTypeDef("benchmark", "Benchmark Result", "data", "result"),
        ArtifactTypeDef("evaluation", "Evaluation Result", "data", "result"),
        ArtifactTypeDef("security_result", "Security Result", "data", "result"),
        ArtifactTypeDef("log", "Log", "file", "misc"),
        ArtifactTypeDef("plugin", "Plugin", "file", "misc"),
        ArtifactTypeDef("generated_file", "Generated File", "file", "misc"),
    ):
        register_artifact_type(defn)


_seed()

# The default backing for an unknown/free-form type: file-backed misc. Unknown
# types are honestly labeled (category "misc") rather than rejected — new types
# require no architecture change.
_UNKNOWN_DEFAULT = ArtifactTypeDef("unknown", "Unknown", "file", "misc")


def get_artifact_type(key: str) -> ArtifactTypeDef:
    """Return the descriptor for a type key. Unknown keys yield a safe default with
    the key preserved — never a KeyError. This is what makes types extensible
    without code changes."""
    known = _KNOWN.get(key)
    if known is not None:
        return known
    return ArtifactTypeDef(key=key, label=key.replace("_", " ").title(),
                           backing=_UNKNOWN_DEFAULT.backing, category=_UNKNOWN_DEFAULT.category)


def list_artifact_types() -> list[dict]:
    return [d.to_dict() for d in _KNOWN.values()]


def is_file_backed(key: str) -> bool:
    return get_artifact_type(key).backing == "file"
