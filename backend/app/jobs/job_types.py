"""Job type registry (RedForge V3, Epic 2).

Job kinds are **extensible without architecture change** (the Epic's requirement).
Each kind declares a default per-kind concurrency limit — the central enforcement
point for "only one training job at a time" and similar (Constitution §8.4). Unknown
kinds are accepted with a safe default. A new kind is a registration (or a new
string), never an edit to the scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobTypeDef:
    key: str
    label: str
    concurrency: int          # max concurrent jobs of this kind (single-machine)
    default_max_attempts: int = 1

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label,
                "concurrency": self.concurrency, "default_max_attempts": self.default_max_attempts}


_KNOWN: dict[str, JobTypeDef] = {}


def register_job_type(defn: JobTypeDef) -> None:
    _KNOWN[defn.key] = defn


def _seed() -> None:
    for defn in (
        # Single-GPU assumption: training is strictly serialized (fixes the prior
        # architecture's unbounded-concurrent-training defect).
        JobTypeDef("training", "Training", concurrency=1, default_max_attempts=1),
        JobTypeDef("export", "Export", concurrency=1),
        JobTypeDef("benchmark", "Benchmark", concurrency=2),
        JobTypeDef("evaluation", "Evaluation", concurrency=2),
        JobTypeDef("security_scan", "Security Scan", concurrency=2),
        JobTypeDef("dataset_import", "Dataset Import", concurrency=2),
        JobTypeDef("dataset_processing", "Dataset Processing", concurrency=2),
        JobTypeDef("model_download", "Model Download", concurrency=2, default_max_attempts=3),
        JobTypeDef("model_discovery", "Model Discovery", concurrency=2),
        # Strictly serialized: two pip installs into one virtualenv corrupt it.
        # Not auto-retried — the installer resumes from its own phase state instead.
        JobTypeDef("training_runtime_install", "Install Training Runtime",
                   concurrency=1, default_max_attempts=1),
        JobTypeDef("model_sync", "Model Sync", concurrency=4),
        JobTypeDef("cache_build", "Cache Build", concurrency=2),
        JobTypeDef("plugin_task", "Plugin Task", concurrency=2),
        JobTypeDef("diagnostics", "Diagnostics", concurrency=4),
    ):
        register_job_type(defn)


_seed()

_UNKNOWN_DEFAULT = JobTypeDef("unknown", "Unknown", concurrency=2)


def get_job_type(key: str) -> JobTypeDef:
    known = _KNOWN.get(key)
    if known is not None:
        return known
    return JobTypeDef(key=key, label=key.replace("_", " ").title(),
                      concurrency=_UNKNOWN_DEFAULT.concurrency,
                      default_max_attempts=_UNKNOWN_DEFAULT.default_max_attempts)


def list_job_types() -> list[dict]:
    return [d.to_dict() for d in _KNOWN.values()]
