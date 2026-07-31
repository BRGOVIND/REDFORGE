"""Training Runtime API — install and inspect the optional training engine.

The installer is submitted as a Job so it flows through the ONE execution platform
and appears in the Global Task Manager (progress, ETA, logs, cancel, retry) like
every other long-running operation. No terminal, ever.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.jobs import job_service
from app.logging_config import get_logger
from app.training_runtime import runtime_service, uninstall as uninstall_runtime

router = APIRouter(prefix="/api/training-runtime", tags=["training-runtime"])
logger = get_logger("training-runtime-api")

JOB_TYPE = "training_runtime_install"


class InstallRequest(BaseModel):
    # Discard any partial state and install from scratch (repairs a broken install).
    force: bool = False


@router.get("")
async def get_runtime(refresh: bool = Query(False, description="bypass the short cache")) -> dict:
    """Status of the managed training runtime, the hardware, and the install plan."""
    report = await runtime_service.report(refresh=refresh)
    return report.to_dict()


@router.post("/install", status_code=202)
async def install(req: InstallRequest) -> dict:
    """Queue the runtime installation as a Job.

    Returns 409 if it is already installed (use ``force`` to reinstall) or if an
    installation is already running — two concurrent pip installs into the same
    virtual environment would corrupt it.
    """
    report = await runtime_service.report(refresh=True)
    if report.ready and not req.force:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "already_installed",
                "message": "The training runtime is already installed and verified.",
                "fix": "Pass force=true to reinstall it.",
            },
        )

    # Two concurrent pip installs into the same virtualenv would corrupt it.
    active = []
    for status in ("running", "queued"):
        active += await job_service.list(type=JOB_TYPE, status=status, limit=5)
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "install_in_progress",
                "message": "A training runtime installation is already in progress.",
                "fix": "Open the task panel to watch or cancel it.",
                "job_id": active[0].get("id"),
            },
        )

    job = await job_service.submit(type=JOB_TYPE, params={"force": req.force})
    logger.info("queued training runtime install job=%s force=%s", job.get("id"), req.force)
    return {"job_id": job.get("id"), "status": job.get("status"), "runtime": report.to_dict()}


@router.post("/verify")
async def verify() -> dict:
    """Re-run detection and report the authoritative state."""
    runtime_service.invalidate()
    report = await runtime_service.report(refresh=True)
    return report.to_dict()


@router.delete("")
async def remove() -> dict:
    """Delete the managed runtime. Never touches models, datasets or runs."""
    import asyncio

    running = await job_service.list(type=JOB_TYPE, status="running", limit=5)
    if running:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "install_in_progress",
                "message": "Cannot remove the runtime while it is being installed.",
                "fix": "Cancel the installation task first.",
            },
        )
    removed = await asyncio.to_thread(uninstall_runtime)
    runtime_service.invalidate()
    report = await runtime_service.report(refresh=True)
    return {"removed": removed, "runtime": report.to_dict()}
