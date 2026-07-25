import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path


def _relocate_unsloth_cache() -> str:
    """Move Unsloth's generated compiled-kernel cache OUT of any source tree — done
    HERE, at app import, so it is launcher-independent.

    Unsloth (via unsloth_zoo/compiler.py) reads ``UNSLOTH_COMPILE_LOCATION`` ONCE at
    its import time; unset, it defaults to the RELATIVE ``"unsloth_compiled_cache"``,
    i.e. the process CWD (= ``backend/``). It then writes ``*.py`` kernel files
    (e.g. ``unsloth_compiled_cache/moe_utils.py``) there. Under ``uvicorn --reload``
    the reloader always watches the CWD with a ``*.py`` include, so those generated
    files trigger a reload that kills the in-flight training worker.

    Setting the env var in the launcher only helps ONE launcher (``redforge start
    --dev``). Setting it here, before ``app.main`` finishes importing and long before
    the training worker lazily imports unsloth, fixes EVERY entry point — bare
    ``uvicorn app.main:app --reload``, an IDE runner, ``python -m uvicorn``, a stale
    installed CLI — because they all import this module. We ``setdefault`` so an
    explicit operator override still wins. The target is under the user cache dir,
    which is never inside a watched source tree regardless of CWD."""
    default = str(Path.home() / ".cache" / "redforge" / "unsloth_compiled_cache")
    loc = os.environ.setdefault("UNSLOTH_COMPILE_LOCATION", default)
    try:
        Path(loc).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return loc


# MUST run before anything imports unsloth (the training worker imports it lazily).
_UNSLOTH_CACHE_DIR = _relocate_unsloth_cache()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api import models, attacks, runs, evaluate, dashboard, reports, benchmarks, analytics, mutations, agent, leaderboard, history, dataset, benchmark_dataset, sessions, evaluation_engine, pipeline, system, runtime_status, providers, model_manager, health, onboarding, projects, playground, assistant, datasets, training, recommendations, registry, benchmark_center, evaluation_workbench, foundation_models, artifacts, jobs, dataset_platform, training_platform, export, experiments, runtime_models, hardware, tasks, model_hub
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
    forever. Mark any pending/running/paused job with a terminal status **and a
    meaningful error + completed_at** so the UI never shows a permanently-stuck
    run and never a failure with a null error field. Never raises.

    This is the fix for the "status=failed, error=null, completed_at=null" record:
    previously this used a bulk UPDATE that only set ``status``, leaving the error
    and timestamp empty. Every terminal transition now carries a reason."""
    from sqlalchemy import select

    from app.db.models import (
        AgentRun, BenchmarkResult, BenchmarkRun, EvaluationSession, JobRecord, TrainingRun,
        V3TrainingRunRecord, WorkbenchSession,
    )

    ACTIVE = ("running", "pending", "paused")
    REASON = "interrupted: the RedForge process restarted while this job was in-flight."
    log = get_logger("startup")
    total = 0
    try:
        async with AsyncSessionLocal() as db:
            for model, terminal in (
                (EvaluationSession, "interrupted"),
                (TrainingRun, "interrupted"),
                (BenchmarkRun, "failed"),      # legacy benchmark schema has no 'interrupted'
                (BenchmarkResult, "failed"),   # Benchmark Center jobs don't survive a restart
                (WorkbenchSession, "failed"),  # Evaluation Workbench sessions don't survive a restart
                (JobRecord, "interrupted"),    # V3 Execution Platform jobs don't survive a restart
                (V3TrainingRunRecord, "failed"),  # V3 training runs don't survive a restart
                (AgentRun, "failed"),
            ):
                status_col = getattr(model, "status", None)
                if status_col is None:
                    continue
                # Per-row so we can also populate error/completed_at wherever those
                # columns exist (they don't on every legacy table). Counts are tiny.
                rows = (await db.execute(
                    select(model).where(status_col.in_(ACTIVE)))).scalars().all()
                for row in rows:
                    row.status = terminal
                    if hasattr(row, "completed_at") and getattr(row, "completed_at") is None:
                        row.completed_at = _utcnow()
                    if hasattr(row, "error") and not getattr(row, "error"):
                        row.error = REASON
                    # Some tables carry the reason in a JSON metrics/summary blob.
                    if hasattr(row, "metrics") and isinstance(getattr(row, "metrics"), dict) \
                            and "error" not in row.metrics:
                        row.metrics = {**row.metrics, "error": REASON}
                    total += 1
            await db.commit()
        if total:
            log.warning("recovered %d orphaned job(s) from a previous run → terminal + reason", total)
    except Exception as exc:  # noqa: BLE001 - recovery must never block startup
        log.warning("orphaned-job recovery skipped: %s", exc)


async def _startup_model_discovery() -> None:
    """Kick off automatic runtime-model discovery in the background (Epic 4.5).

    Submits a ``runtime_discovery`` Job so the operator's locally-installed runtime
    models (e.g. Ollama tags) are discovered, resolved, and auto-registered as
    Foundation Models — without blocking startup or the UI. Offline-honest and
    never raises: if the runtime is unreachable, discovery simply finds nothing."""
    try:
        from app.jobs import job_service
        job = await job_service.submit(type="runtime_discovery")
        get_logger("startup").info("automatic model discovery queued (job %s)", job.get("id"))
    except Exception as exc:  # noqa: BLE001 - discovery must never block startup
        get_logger("startup").warning("startup model discovery skipped: %s", exc)


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


def _register_v3_job_handlers() -> None:
    """Register the Epic-3 Job handlers into the Execution Platform. Each context
    exposes a ``register_*_handlers`` function; additive and independent."""
    log = get_logger("startup")
    try:
        from app.datasets.handlers import register_dataset_handlers
        register_dataset_handlers()
        from app.training.execution import register_training_handlers
        register_training_handlers()
        from app.export.handlers import register_export_handlers
        register_export_handlers()
        # Epic 4: bind the Experiment subscriber so engines "publish into" the
        # experiment timeline/metrics via the Event Bus (no direct coupling).
        from app.experiments import register_experiment_subscribers
        register_experiment_subscribers()
        # Epic 4.5: register the automatic runtime-model discovery job handler so
        # discovery can run in the background via the Job System.
        from app.foundation_models import register_discovery_handlers
        register_discovery_handlers()
        # Model Hub: register the model_download job handler (one-click downloads).
        from app.model_hub import register_model_hub_handlers
        register_model_hub_handlers()
    except Exception as exc:  # noqa: BLE001 - handler registration must not block startup
        log.warning("V3 job handler registration incomplete: %s", exc)


def _log_reload_diagnostics() -> None:
    """Startup instrumentation for the dev-reload / Unsloth-cache configuration, so the
    exact watched-vs-generated layout is verifiable in the backend log. The decisive
    line is ``unsloth_cache_inside_cwd`` — it MUST be False, or the reloader will watch
    Unsloth's generated ``.py`` files and restart mid-training."""
    import sys
    log = get_logger("startup")
    cwd = Path.cwd().resolve()
    cache = Path(os.environ.get("UNSLOTH_COMPILE_LOCATION", "unsloth_compiled_cache")).resolve()
    inside = cwd == cache or cwd in cache.parents
    # uvicorn relaunches the worker with the original argv, so ``--reload`` there is a
    # reliable signal that the dev reloader is active.
    under_reload = "--reload" in sys.argv or os.environ.get("RUN_MAIN") == "true"
    log.info("── startup diagnostics ─────────────────────────────")
    log.info("  cwd                       : %s", cwd)
    log.info("  launcher argv             : %s", " ".join(sys.argv))
    log.info("  under uvicorn --reload    : %s", under_reload)
    log.info("  UNSLOTH_COMPILE_LOCATION  : %s", os.environ.get("UNSLOTH_COMPILE_LOCATION"))
    log.info("  unsloth actual cache dir  : %s", cache)
    log.info("  unsloth_cache_inside_cwd  : %s  (MUST be False under --reload)", inside)
    if inside:
        log.warning("  Unsloth cache is INSIDE the CWD — a dev reloader watching CWD will "
                    "restart mid-training. UNSLOTH_COMPILE_LOCATION should point outside the tree.")
    log.info("────────────────────────────────────────────────────")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    _enforce_single_process()
    get_logger("startup").info("RedForge API starting up (single-process, local-only)")
    _log_reload_diagnostics()
    set_scoring_engine(WeightedScoringEngine())
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_attacks(db)
    # Register V3 Job handlers (dataset processing, training, export) so the
    # Execution Platform can dispatch them. Additive; never raises.
    _register_v3_job_handlers()
    # Reconcile jobs left 'running' by a previous crash/restart — never leave a
    # job permanently active.
    await _recover_orphaned_jobs()
    # Health validation must not delay readiness: it probes the runtime provider
    # (network, timed) and is log-only. Run it in the background so /healthz comes
    # up immediately. Keep a reference so the task is not garbage-collected.
    app.state.startup_health_task = asyncio.create_task(_log_startup_health())
    # Automatic Foundation Model discovery (Epic 4.5) — background, non-blocking.
    app.state.startup_discovery_task = asyncio.create_task(_startup_model_discovery())
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
app.include_router(evaluation_workbench.router)
# --- RedForge V3 (Foundation Platform) — additive; nothing existing depends on it ---
app.include_router(foundation_models.router)
# --- RedForge V3 Epic 4.5 (Automatic Model Discovery) — discovered runtime models ---
app.include_router(runtime_models.router)
# --- RedForge V3 Epic 2 (Platform Core) — Artifact Registry + Job System ---
app.include_router(artifacts.router)
app.include_router(jobs.router)
# --- RedForge V3 Epic 3 (AI Engineering Pipeline) — Dataset/Training/Export ---
app.include_router(dataset_platform.router)
app.include_router(training_platform.router)
app.include_router(export.router)
# --- RedForge V3 Epic 4 (Experiment Platform) — the operator's unit of work ---
app.include_router(experiments.router)
# --- Hardware Compatibility Engine — GPU detection + pre-flight memory assessment ---
app.include_router(hardware.router)
# --- Global Task Manager — unified view/control over ALL long-running work (Jobs) ---
app.include_router(tasks.router)
# --- Model Hub — browse + one-click download curated models (downloads run as Jobs) ---
app.include_router(model_hub.router)


# Standardized structured error responses for every endpoint.
register_error_handlers(app)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"name": "RedForge API", "version": app.version, "status": "online"}


# Serve the built frontend (production single-process mode). Must be LAST so the
# SPA catch-all never shadows the API. In dev this is a no-op (Vite serves the UI).
mount_frontend(app)
