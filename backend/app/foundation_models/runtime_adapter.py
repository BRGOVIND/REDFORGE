"""Foundation Platform — Runtime compatibility adapter (RedForge V3, Epic 1).

The Constitution forbids the Runtime Engine from knowing anything about Foundation
Models (§11.2). The dependency is therefore one-directional: **Foundation reads
Runtime, Runtime never reads Foundation.** Runtime is a leaf every other context
may depend on; depending *on* it (read-only introspection) is allowed and is
exactly what Model Resolution needs.

This adapter is that read-only seam. It calls the existing Runtime Manager
(`get_runtime()`) to introspect an installed runtime model and returns plain
facts — without modifying the Runtime Engine in any way and without the Runtime
Engine gaining any awareness of foundation models. It is injectable so resolution
is testable offline (no live provider required).
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

# introspect_fn(runtime_ref) -> raw provider metadata dict (or None)
IntrospectFn = Callable[[str], Awaitable[Optional[dict]]]


async def default_introspect(runtime_ref: str) -> Optional[dict]:
    """Read a runtime model's metadata through the existing Runtime Manager.

    Best-effort and offline-honest: returns None if the runtime is unreachable or
    the model is unknown (never raises). Uses ONLY the Runtime Engine's public
    ``show_model`` — it does not reach into runtime internals, and the Runtime
    Engine remains entirely unaware this call is for foundation-model resolution."""
    try:
        from app.runtime.manager import get_runtime
        return await get_runtime().show_model(runtime_ref)
    except Exception:  # noqa: BLE001 - introspection is advisory; never break resolution
        return None


async def list_runtime_models(limit: int = 200) -> list[str]:
    """List the model names the active runtime provider currently serves.

    Read-only over the Runtime Manager's public surface; used by discovery to
    propose foundation-model candidates from what the operator already has.
    Offline-honest: returns [] if the runtime is unreachable."""
    try:
        from app.runtime.manager import get_runtime
        names = await get_runtime().list_models()
        return list(names)[:limit]
    except Exception:  # noqa: BLE001
        return []


async def runtime_provider_status() -> dict:
    """Report the active runtime provider's identity + reachability (Epic 4.5).

    Read-only over the Runtime Manager (Runtime stays unaware of Foundation). Used
    by automatic discovery to label where models were 'detected from' and to decide
    whether an empty model list means 'offline' (honest) vs. 'genuinely none'.
    Offline-honest: never raises; reports ``online: False`` if unreachable."""
    name, label, online = "unknown", "Runtime", False
    try:
        from app.runtime.manager import get_runtime
        runtime = get_runtime()
        provider = getattr(runtime, "provider", None)
        name = (getattr(provider, "name", None) or "unknown").lower()
        label = getattr(provider, "label", None) or name.title()
        online = bool(await runtime.health())
    except Exception:  # noqa: BLE001 - status is advisory; never break discovery
        pass
    return {"name": name, "label": label, "online": online}
