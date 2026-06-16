from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import BenchmarkRun, ModelScore, Attack
from app.benchmarking.benchmark_runner import run_benchmark_background, default_ollama_call
from app.benchmarking.benchmark_scheduler import BENCHMARK_JOBS, register_job, get_job

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


# ---------- Pydantic schemas ----------

class BenchmarkCreateRequest(BaseModel):
    name: str
    model_list: list[str]
    attack_ids: Optional[list[int]] = None  # None = all attacks


class ModelScoreOut(BaseModel):
    model_name: str
    injection_rate: float
    jailbreak_rate: float
    hallucination_rate: float
    data_leakage_rate: float
    avg_latency_ms: float
    overall_score: float

    model_config = {"from_attributes": True}


class BenchmarkRunOut(BaseModel):
    id: int
    name: str
    model_list: list[str]
    attack_suite: list[int]
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    model_scores: list[ModelScoreOut] = []

    model_config = {"from_attributes": True}


class BenchmarkStatusOut(BaseModel):
    benchmark_run_id: int
    status: str
    progress: int
    error: Optional[str] = None


# ---------- Endpoints ----------

@router.post("", response_model=BenchmarkRunOut, status_code=202)
async def create_benchmark(
    req: BenchmarkCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if req.attack_ids:
        attack_ids = req.attack_ids
    else:
        result = await db.execute(select(Attack.id))
        attack_ids = [row[0] for row in result.all()]

    if not attack_ids:
        raise HTTPException(status_code=400, detail="No attacks available to benchmark")
    if not req.model_list:
        raise HTTPException(status_code=400, detail="model_list must not be empty")

    run = BenchmarkRun(
        name=req.name,
        model_list=req.model_list,
        attack_suite=attack_ids,
        status="pending",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    register_job(run.id)

    from app.db.database import AsyncSessionLocal
    background_tasks.add_task(
        run_benchmark_background,
        run.id,
        req.model_list,
        attack_ids,
        AsyncSessionLocal,
        default_ollama_call,
    )

    return BenchmarkRunOut(
        id=run.id,
        name=run.name,
        model_list=run.model_list,
        attack_suite=run.attack_suite,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        model_scores=[],
    )


@router.get("/{benchmark_id}/status", response_model=BenchmarkStatusOut)
async def get_benchmark_status(benchmark_id: int):
    job = get_job(benchmark_id)
    if job is None:
        # job may not be in memory (e.g. server restart); return DB status
        return BenchmarkStatusOut(
            benchmark_run_id=benchmark_id,
            status="unknown",
            progress=0,
        )
    return BenchmarkStatusOut(
        benchmark_run_id=job.benchmark_run_id,
        status=job.status,
        progress=job.progress,
        error=job.error,
    )


@router.get("/{benchmark_id}", response_model=BenchmarkRunOut)
async def get_benchmark(benchmark_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BenchmarkRun)
        .where(BenchmarkRun.id == benchmark_id)
        .options(selectinload(BenchmarkRun.model_scores))
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    return run


@router.get("", response_model=list[BenchmarkRunOut])
async def list_benchmarks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BenchmarkRun)
        .options(selectinload(BenchmarkRun.model_scores))
        .order_by(BenchmarkRun.created_at.desc())
    )
    return result.scalars().all()
