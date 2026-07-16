import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api import models, attacks, runs, evaluate, dashboard, reports, benchmarks, analytics, mutations, agent, leaderboard, history, dataset, benchmark_dataset, sessions, evaluation_engine, pipeline, system, runtime_status, providers, model_manager, health, onboarding, projects, playground, assistant, datasets, training, recommendations, registry, benchmark_center
from app.config import settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging, get_logger
from app.static_serving import mount_frontend
from app.db.database import init_db, AsyncSessionLocal
from app.attacks.library import seed_attacks
from app.scoring.weighted_engine import WeightedScoringEngine
from app.scoring.scoring_interface import set_scoring_engine
from app.version import __version__


ALLOWED_ORIGINS = settings.ALLOWED_ORIGINS


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every HTTP response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        # Only set HSTS in production (not localhost)
        if request.url.hostname not in ("localhost", "127.0.0.1"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def _enforce_single_process() -> None:
    """RedForge keeps live state (runtime cache, training/pull progress, log ring
    buffer) in memory, so it MUST run as a single process. Refuse to start if a
    multi-worker signal indicates otherwise — those setups silently break live
    progress and job tracking. Override with REDFORGE_ALLOW_MULTIWORKER=1 only if
    you understand the consequences."""
    import os

    if os.environ.get("REDFORGE_ALLOW_MULTIWORKER") == "1":
        return
    for var in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        val = os.environ.get(var, "")
        if val.isdigit() and int(val) > 1:
            raise RuntimeError(
                f"RedForge must run single-process, but {var}={val}. Live progress and "
                "job tracking rely on in-memory state. Run with one worker, or set "
                "REDFORGE_ALLOW_MULTIWORKER=1 to override."
            )


async def _recover_orphaned_jobs() -> None:
    """Reconcile jobs left mid-flight by a previous crash/restart.

    Background jobs (evaluations, training, benchmarks, agent runs) execute in the
    process and do not survive a restart. Without this, their rows stay 'running'
    forever. Mark any pending/running/paused job as 'interrupted' at startup so
    the UI never shows a permanently-stuck run. Never raises."""
    from sqlalchemy import update

    from app.db.models import AgentRun, BenchmarkResult, BenchmarkRun, EvaluationSession, TrainingRun

    ACTIVE = ("running", "pending", "paused")
    log = get_logger("startup")
    total = 0
    try:
        async with AsyncSessionLocal() as db:
            for model, terminal in (
                (EvaluationSession, "interrupted"),
                (TrainingRun, "interrupted"),
                (BenchmarkRun, "failed"),      # legacy benchmark schema has no 'interrupted'
                (BenchmarkResult, "failed"),   # Benchmark Center jobs don't survive a restart
                (AgentRun, "failed"),
            ):
                status_col = getattr(model, "status", None)
                if status_col is None:
                    continue
                result = await db.execute(
                    update(model).where(status_col.in_(ACTIVE)).values(status=terminal)
                )
                total += result.rowcount or 0
            await db.commit()
        if total:
            log.warning("recovered %d orphaned job(s) from a previous run → interrupted", total)
    except Exception as exc:  # noqa: BLE001 - recovery must never block startup
        log.warning("orphaned-job recovery skipped: %s", exc)


async def _log_startup_health() -> None:
    """Non-blocking startup validation: run the health engine once and log a
    summary. Never raises — startup proceeds regardless of health findings."""
    try:
        from app.health import Status, health_service

        report = await health_service.run()
        log = get_logger("startup")
        s = report.summary
        log.info(
            "system health: %s (%d ok, %d warning, %d error, ready=%s)",
            report.status, s.healthy, s.warning, s.error, report.ready,
        )
        for c in report.checks:
            if c.status != Status.HEALTHY:
                log.warning("health · %s: %s%s", c.name, c.message,
                            f" — {c.suggested_fix}" if c.suggested_fix else "")
    except Exception as exc:  # noqa: BLE001
        get_logger("startup").warning("startup health check skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    _enforce_single_process()
    get_logger("startup").info("RedForge API starting up (single-process, local-only)")
    set_scoring_engine(WeightedScoringEngine())
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_attacks(db)
    # Reconcile jobs left 'running' by a previous crash/restart — never leave a
    # job permanently active.
    await _recover_orphaned_jobs()
    # Health validation must not delay readiness: it probes the runtime provider
    # (network, timed) and is log-only. Run it in the background so /healthz comes
    # up immediately. Keep a reference so the task is not garbage-collected.
    app.state.startup_health_task = asyncio.create_task(_log_startup_health())
    yield


app = FastAPI(
    title="RedForge API",
    version=__version__,
    lifespan=lifespan,
)

# Security headers on every response
app.add_middleware(SecurityHeadersMiddleware)

# CORS — restricted to known frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)

app.include_router(models.router)
app.include_router(attacks.router)
app.include_router(runs.router)
app.include_router(evaluate.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(benchmarks.router)
app.include_router(analytics.router)
app.include_router(mutations.router)
app.include_router(agent.router)
app.include_router(leaderboard.router)
app.include_router(history.router)
app.include_router(dataset.router)
app.include_router(benchmark_dataset.router)
app.include_router(sessions.router)
app.include_router(evaluation_engine.router)
app.include_router(pipeline.router)
app.include_router(system.router)
app.include_router(runtime_status.router)
app.include_router(providers.router)
app.include_router(model_manager.router)
app.include_router(health.router)
app.include_router(onboarding.router)
# --- RedForge V2 (AI Studio) — additive; nothing in v1.2 depends on these ---
app.include_router(projects.router)
app.include_router(playground.router)
app.include_router(assistant.router)
app.include_router(datasets.router)
app.include_router(training.router)
app.include_router(recommendations.router)
app.include_router(registry.router)
app.include_router(benchmark_center.router)


# Standardized structured error responses for every endpoint.
register_error_handlers(app)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"name": "RedForge API", "version": app.version, "status": "online"}


# Serve the built frontend (production single-process mode). Must be LAST so the
# SPA catch-all never shadows the API. In dev this is a no-op (Vite serves the UI).
mount_frontend(app)
