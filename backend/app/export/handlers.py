"""Export Engine — Job handler (RedForge V3, Epic 3).

Export executes as a Job (Constitution §10.8, §8). The handler reconstructs the
export configuration from the job params and runs the merge → GGUF → install
pipeline, publishing artifacts with lineage.
"""
from __future__ import annotations

from app.export.domain import ExportConfiguration
from app.export.service import perform_export
from app.jobs.domain import JobResult


async def _handle_export(job, ctx) -> JobResult:
    raw = (job.params or {}).get("config") or {}
    if not raw.get("source_artifact_id"):
        return JobResult(success=False, message="source_artifact_id is required")
    config = ExportConfiguration(
        source_artifact_id=raw["source_artifact_id"], target=raw.get("target", "gguf"),
        base_model=raw.get("base_model", ""), quantization=raw.get("quantization", "q4_k_m"),
        model_name=raw.get("model_name"))
    result = await perform_export(ctx, config)
    return JobResult(success=result.success, data={"export": result.to_dict()},
                     artifact_ids=result.artifact_ids(), message=result.message)


def register_export_handlers() -> None:
    from app.jobs.handlers import handler_registry
    handler_registry.register("export", _handle_export)
