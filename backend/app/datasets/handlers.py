"""Dataset Platform — Job handlers (RedForge V3, Epic 3).

Dataset processing executes through the Execution Platform (Constitution §12, §8).
Registers a ``dataset_processing`` handler so validation/splitting run as tracked,
cancellable Jobs. Registered from ``register_dataset_handlers()`` at startup.
"""
from __future__ import annotations

from app.jobs.domain import JobResult


async def _handle_dataset_processing(job, ctx) -> JobResult:
    """Process a dataset as a job. params: {dataset_id, operation: validate|split, ...}."""
    from app.datasets import dataset_platform
    params = job.params or {}
    dataset_id = params.get("dataset_id")
    operation = params.get("operation", "validate")
    if not dataset_id:
        return JobResult(success=False, message="dataset_id is required")

    await ctx.report_progress(0.2, f"{operation} starting")
    if operation == "validate":
        res = await dataset_platform.validate(dataset_id)
        if res is None:
            return JobResult(success=False, message="dataset not found")
        await ctx.report_progress(1.0, f"validated (score {res['score']})")
        return JobResult(success=True, data={"validation": res}, message="validation complete")

    if operation == "split":
        res = await dataset_platform.split(
            dataset_id, train=params.get("train", 0.8), val=params.get("val", 0.1),
            test=params.get("test", 0.1), seed=params.get("seed", 42))
        if res is None:
            return JobResult(success=False, message="dataset not found")
        await ctx.report_progress(1.0, "split complete")
        # the split published a new dataset artifact — record it on the result
        return JobResult(success=True, data={"split": res},
                         artifact_ids=[res["artifact_id"]] if res.get("artifact_id") else [],
                         message="split complete")

    return JobResult(success=False, message=f"unknown operation '{operation}'")


def register_dataset_handlers() -> None:
    from app.jobs.handlers import handler_registry
    handler_registry.register("dataset_processing", _handle_dataset_processing)
