from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api import models, attacks, runs, evaluate, dashboard, reports, benchmarks, analytics, mutations, agent, leaderboard, history, dataset, benchmark_dataset, sessions, evaluation_engine, pipeline, system, runtime_status
from app.config import settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging, get_logger
from app.static_serving import mount_frontend
from app.db.database import init_db, AsyncSessionLocal
from app.attacks.library import seed_attacks
from app.scoring.weighted_engine import WeightedScoringEngine
from app.scoring.scoring_interface import set_scoring_engine


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    get_logger("startup").info("RedForge API starting up")
    set_scoring_engine(WeightedScoringEngine())
    await init_db()
    async with AsyncSessionLocal() as db:
        await seed_attacks(db)
    yield


app = FastAPI(
    title="RedForge API",
    version="1.0.0",
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


# Standardized structured error responses for every endpoint.
register_error_handlers(app)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"name": "RedForge API", "version": app.version, "status": "online"}


# Serve the built frontend (production single-process mode). Must be LAST so the
# SPA catch-all never shadows the API. In dev this is a no-op (Vite serves the UI).
mount_frontend(app)
