"""Individual system-health checks.

Each function takes a shared :class:`HealthContext` and returns an
:class:`Outcome` (status + message + fix + metadata). A check's **severity** is a
fixed property assigned by the service (see the registry in ``service.py``), not
set here.

Checks are **provider-agnostic**: the runtime/model checks iterate the registry
and delegate to the Runtime Manager (``provider_manager``) — no provider-specific
branching. All detection reuses existing services (``resource_monitor``,
``static_serving``, the DB, the runtime), so no discovery logic is duplicated.
"""
from __future__ import annotations

import os
import platform
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.health.models import Outcome, error, healthy, warning
from app.resources.resource_monitor import ResourceSnapshot

MIN_PYTHON = (3, 11)
_SUPPORTED_ARCH = {"x86_64", "amd64", "arm64", "aarch64"}


@dataclass
class HealthContext:
    resources: ResourceSnapshot
    provider_default: str
    provider_snapshot: dict[str, Any]     # provider_manager.check(default)
    providers_available: list[str]
    app_port: int
    include_network: bool = False


def app_port() -> int:
    try:
        return int(os.environ.get("REDFORGE_PORT", "8000"))
    except ValueError:
        return 8000


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _db_dir() -> Optional[Path]:
    url = settings.DATABASE_URL
    if ":///" not in url:
        return None
    raw = url.split(":///", 1)[1]  # e.g. "./redforge.db"
    try:
        return Path(raw).resolve().parent
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

async def check_os(ctx: HealthContext) -> Outcome:
    system = platform.system() or "unknown"
    release = platform.release()
    return healthy(
        f"{system} {release}".strip(),
        system=system, release=release, version=platform.version(),
    )


async def check_architecture(ctx: HealthContext) -> Outcome:
    machine = (platform.machine() or "").lower()
    if machine in _SUPPORTED_ARCH:
        return healthy(machine, machine=machine)
    return warning(
        f"Unrecognized architecture '{machine}'",
        fix="RedForge targets x86_64/arm64; other architectures are untested.",
        machine=machine,
    )


async def check_python_version(ctx: HealthContext) -> Outcome:
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    required = f">={MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    if (v.major, v.minor) >= MIN_PYTHON:
        return healthy(version, version=version, required=required)
    return error(
        f"Python {version} is too old",
        fix=f"Install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ and reinstall RedForge.",
        version=version, required=required,
    )


# ---------------------------------------------------------------------------
# Runtime (provider-agnostic)
# ---------------------------------------------------------------------------

async def check_runtime_providers(ctx: HealthContext) -> Outcome:
    providers = ctx.providers_available
    default = ctx.provider_default
    if not providers:
        return error("No runtime providers registered")
    if default in providers:
        return healthy(
            f"{len(providers)} provider(s) registered · default '{default}'",
            available=providers, default=default,
        )
    return warning(
        f"Default provider '{default}' is not registered",
        fix="Set REDFORGE_RUNTIME_PROVIDER to one of: " + ", ".join(providers),
        available=providers, default=default,
    )


async def check_provider_health(ctx: HealthContext) -> Outcome:
    snap = ctx.provider_snapshot
    default = ctx.provider_default
    online = bool(snap.get("online"))
    meta = {
        "provider": default,
        "online": online,
        "base_url": snap.get("base_url"),
        "version": snap.get("version"),
    }
    if online:
        return healthy(f"Provider '{default}' is reachable", **meta)
    return error(
        f"Provider '{default}' is offline or unreachable",
        fix=f"Ensure the '{default}' provider is running and reachable"
        + (f" at {snap.get('base_url')}." if snap.get("base_url") else "."),
        **meta,
    )


async def check_installed_models(ctx: HealthContext) -> Outcome:
    snap = ctx.provider_snapshot
    default = ctx.provider_default
    count = snap.get("model_count")
    models = snap.get("models") or []
    if not snap.get("online"):
        return warning(
            "Cannot list models — active provider is offline",
            provider=default, count=None,
        )
    if count:
        return healthy(
            f"{count} model(s) installed",
            provider=default, count=count, models=models[:25],
        )
    return warning(
        "No models installed for the active provider",
        fix="Install at least one model for the active provider before evaluating.",
        provider=default, count=0,
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

async def check_cpu(ctx: HealthContext) -> Outcome:
    r = ctx.resources
    n = r.cpu_count
    meta = {"cpu_count": n, "load_avg_1m": r.load_avg_1m}
    if not n:
        return healthy("CPU detected", **meta)
    return healthy(f"{n} logical core{'s' if n != 1 else ''}", **meta)


async def check_ram(ctx: HealthContext) -> Outcome:
    r = ctx.resources
    avail, total = r.ram_available_mb, r.ram_total_mb
    meta = {"available_mb": avail, "total_mb": total, "source": r.source}
    if avail is None:
        return warning("Available RAM could not be determined", **meta)
    msg = f"{avail} MB available of {total} MB"
    if avail >= 2000:
        return healthy(msg, **meta)
    return warning(
        msg + " — low",
        fix="Close other applications or choose a smaller model.",
        **meta,
    )


async def check_disk(ctx: HealthContext) -> Outcome:
    r = ctx.resources
    free, total = r.disk_free_mb, r.disk_total_mb
    meta = {"free_mb": free, "total_mb": total}
    if free is None:
        return warning("Free disk space could not be determined", **meta)
    msg = f"{free} MB free"
    if free >= 5000:
        return healthy(msg, **meta)
    if free >= 1000:
        return warning(msg + " — running low", fix="Free up disk space.", **meta)
    return error(msg + " — critically low",
                 fix="Free up disk space before running evaluations.", **meta)


async def check_gpu(ctx: HealthContext) -> Outcome:
    gpu = ctx.resources.gpu
    meta = {
        "available": gpu.available, "name": gpu.name,
        "total_mb": gpu.total_mb, "free_mb": gpu.free_mb, "backend": gpu.backend,
    }
    if gpu.available:
        return healthy(gpu.name or "GPU detected", **meta)
    return warning("No GPU detected — evaluations will run on CPU", **meta)


async def check_cuda(ctx: HealthContext) -> Outcome:
    gpu = ctx.resources.gpu
    meta = {"backend": gpu.backend, "vram_total_mb": gpu.total_mb}
    if gpu.available and gpu.backend == "cuda":
        return healthy(f"CUDA acceleration available ({gpu.name})", **meta)
    if gpu.available and gpu.backend == "metal":
        return healthy("GPU acceleration via Metal (CUDA not applicable)", **meta)
    return warning("CUDA not available — using CPU", **meta)


# ---------------------------------------------------------------------------
# Process / IO
# ---------------------------------------------------------------------------

async def check_ports(ctx: HealthContext) -> Outcome:
    port = ctx.app_port
    in_use = _port_open(port)
    return healthy(
        f"Application port {port} is {'in use' if in_use else 'free'}",
        app_port=port, in_use=in_use,
    )


async def check_backend_status(ctx: HealthContext) -> Outcome:
    port = ctx.app_port
    if _port_open(port):
        return healthy(f"Backend API reachable on :{port}", port=port, reachable=True)
    return warning(
        f"Backend API not running on :{port}",
        fix="Start RedForge with: redforge start",
        port=port, reachable=False,
    )


async def check_frontend_status(ctx: HealthContext) -> Outcome:
    from app.static_serving import resolve_static_dir

    static = resolve_static_dir()
    if static is not None:
        return healthy("Frontend build present", static_dir=str(static))
    return warning(
        "No frontend build found (dev mode, or needs a build)",
        fix="Build the UI (npm run build) or use a packaged release.",
        static_dir=None,
    )


async def check_database(ctx: HealthContext) -> Outcome:
    from sqlalchemy import text

    from app.db.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return healthy("Database reachable", url=settings.DATABASE_URL)
    except Exception as exc:  # noqa: BLE001
        return error(
            "Database not reachable",
            fix="Initialize the database with: redforge install",
            url=settings.DATABASE_URL, detail=str(exc),
        )


async def check_permissions(ctx: HealthContext) -> Outcome:
    target = _db_dir() or Path.cwd()
    try:
        with tempfile.NamedTemporaryFile(dir=str(target), prefix=".rf-health-", delete=True):
            pass
        return healthy("Data directory is writable", path=str(target))
    except Exception as exc:  # noqa: BLE001
        return error(
            f"Data directory is not writable: {target}",
            fix="Grant write permission to the RedForge data directory.",
            path=str(target), detail=str(exc),
        )


async def check_network(ctx: HealthContext) -> Outcome:
    # Optional — only run when explicitly requested.
    import httpx

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.head("https://github.com")
        if resp.status_code < 500:
            return healthy("Internet reachable", status=resp.status_code)
        return warning("Internet check returned an error", status=resp.status_code)
    except Exception as exc:  # noqa: BLE001
        return warning(
            "No internet connectivity (offline use is fully supported)",
            detail=str(exc),
        )
