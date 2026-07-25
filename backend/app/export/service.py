"""Export Engine — orchestration + service (RedForge V3, Epic 3).

Turns a training artifact into a runtime model through the merge → GGUF → install
pipeline (Constitution §10.8), producing artifacts with lineage
(checkpoint/adapter → merged_model → gguf → runtime_model). Runs as a Job; uses
target runtimes' native tooling; never imports the Runtime Engine.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from app.export.domain import ExportConfiguration, ExportResult
from app.export.providers import get_export_provider
from app.logging_config import get_logger

logger = get_logger("export")


def _export_root(source_path: str, config: ExportConfiguration) -> str:
    base = os.path.dirname(source_path) if source_path else os.getcwd()
    return os.path.join(base, "export", config.target)


def _write_manifest(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


async def perform_export(ctx, config: ExportConfiguration) -> ExportResult:
    """The export pipeline. ``ctx`` provides artifact get/publish + progress. Produces
    merged_model → gguf → (runtime_model) artifacts with lineage."""
    source = await ctx.get_artifact(config.source_artifact_id)
    if source is None:
        return ExportResult(success=False, message="source artifact not found")
    source_path = (source.get("location") or {}).get("file_path") or ""
    workdir = _export_root(source_path, config)
    simulated_any = False

    # 1) Merge (adapter + base -> merged model). Full-finetune checkpoints pass
    #    through; either way we produce a merged_model artifact for lineage clarity.
    await ctx.report_progress(0.2, "merging adapter into base weights")
    merged_path = os.path.join(workdir, "merged_model.json")
    _write_manifest(merged_path, {"base_model": config.base_model, "source": source_path,
                                  "merged": True, "simulated": True})
    simulated_any = True
    merged_art = await ctx.publish_artifact(
        type="merged_model", name=f"{config.base_model or 'model'} (merged)", file_path=merged_path,
        parents=[(config.source_artifact_id, "derived_from")],
        metadata={"base_model": config.base_model, "simulated": True})

    # 2) GGUF conversion.
    await ctx.report_progress(0.5, "converting to GGUF")
    gguf_provider = get_export_provider("gguf")
    # provider.run() is synchronous and, on the real path, shells out to llama.cpp
    # (a long, blocking subprocess). Offload it so the single-process event loop
    # stays responsive during the conversion. Harmless for the simulated path.
    gguf_step = await asyncio.to_thread(
        gguf_provider.run, source_path=merged_path, workdir=workdir, config=config)
    simulated_any = simulated_any or gguf_step.get("simulated", False)
    gguf_art = await ctx.publish_artifact(
        type="gguf", name=f"{config.base_model or 'model'} {config.quantization}.gguf",
        file_path=gguf_step["output_path"], parents=[(merged_art["id"], "derived_from")],
        metadata={"quantization": config.quantization, "simulated": gguf_step.get("simulated"),
                  "note": gguf_step.get("note")})

    result = ExportResult(success=True, target=config.target,
                          merged_model_artifact_id=merged_art["id"],
                          gguf_artifact_id=gguf_art["id"], simulated=simulated_any)

    # 3) Optional runtime install (Ollama).
    if config.target == "ollama":
        await ctx.report_progress(0.8, "importing into Ollama")
        ollama_provider = get_export_provider("ollama")
        # Real path shells out to the `ollama` CLI — offload so the loop stays free.
        step = await asyncio.to_thread(
            ollama_provider.run, source_path=gguf_step["output_path"], workdir=workdir, config=config)
        simulated_any = simulated_any or step.get("simulated", False)
        rt_art = await ctx.publish_artifact(
            type="runtime_model", name=step["runtime_model_name"],
            file_path=os.path.join(workdir, "Modelfile"),
            parents=[(gguf_art["id"], "derived_from")],
            metadata={"provider": "ollama", "runtime_model": step["runtime_model_name"],
                      "simulated": step.get("simulated"), "note": step.get("note")})
        result.runtime_model_artifact_id = rt_art["id"]
        result.runtime_model_name = step["runtime_model_name"]
        result.simulated = simulated_any

    await ctx.report_progress(1.0, "export complete")
    result.message = "export complete" + (" (simulated — install real toolchain for production)"
                                          if result.simulated else "")
    return result


class ExportService:
    """API-facing facade: submit an export Job, read export jobs."""

    async def submit(self, *, source_artifact_id: str, target: str = "gguf",
                     base_model: str = "", quantization: str = "q4_k_m",
                     model_name: Optional[str] = None, project_id: Optional[str] = None,
                     experiment_id: Optional[str] = None) -> dict:
        from app.jobs import job_service
        config = ExportConfiguration(source_artifact_id=source_artifact_id, target=target,
                                     base_model=base_model, quantization=quantization,
                                     model_name=model_name)
        return await job_service.submit(type="export", target_ref=source_artifact_id,
                                        project_id=project_id, experiment_id=experiment_id,
                                        params={"config": config.to_dict()})

    async def history(self, *, limit: int = 100) -> list[dict]:
        from app.jobs import job_service
        return await job_service.list(type="export", limit=limit)


export_service = ExportService()
