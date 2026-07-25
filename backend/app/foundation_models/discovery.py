"""Foundation Platform — automatic runtime-model discovery (RedForge V3, Epic 4.5).

This is the UX-integration layer that makes RedForge feel like a polished desktop
app: on startup (and on demand / on a light schedule) it discovers the runtime
models the operator already has installed, resolves each to a Foundation identity
through the **existing** :class:`ModelResolutionService`, and auto-registers the
confidently-resolved ones as Foundation Models — so the Training Wizard lists them
with no Hugging Face knowledge required.

Architecture (no redesign — reuse only):
- Runtime is read through the existing read-only ``runtime_adapter`` seam (Runtime
  stays unaware — Constitution §11.2, §14).
- Resolution is delegated **entirely** to ``FoundationModelService.resolve`` /
  ``ModelResolutionService``. Discovery never maps names to repos itself.
- Registration is delegated to ``FoundationModelService.register`` (idempotent on
  identity — no duplicate Foundation Models).
- RuntimeModel and FoundationModel remain separate identities; a
  ``DiscoveredRuntimeModel`` links to a Foundation identity by reference and is
  marked *unavailable* (never deleted) when its runtime model disappears.
- Integration is event-driven, over the existing Event Bus.

Honest over simulated (§2.14): only a confident, unambiguous resolution
auto-registers. Anything else is recorded as ``needs_resolution`` with its
candidates, for the operator to confirm — never a fabricated mapping.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.foundation_models.domain import DiscoveredRuntimeModel, RuntimeResolutionStatus
from app.foundation_models.repository import RuntimeModelRepository, SqlRuntimeModelRepository
from app.logging_config import get_logger

logger = get_logger("model-discovery")

# Platform events (dotted, lowercase — consistent with job.*/artifact.*/training.*).
# Spec names → emitted names:
#   RuntimeModelsDiscovered   -> runtime.models_discovered
#   FoundationModelResolved   -> foundation.model_resolved
#   FoundationModelRegistered -> foundation.model_registered
#   RuntimeSyncCompleted      -> runtime.sync_completed
#   RuntimeSyncFailed         -> runtime.sync_failed
RUNTIME_MODELS_DISCOVERED = "runtime.models_discovered"
FOUNDATION_MODEL_RESOLVED = "foundation.model_resolved"
FOUNDATION_MODEL_REGISTERED = "foundation.model_registered"
RUNTIME_SYNC_COMPLETED = "runtime.sync_completed"
RUNTIME_SYNC_FAILED = "runtime.sync_failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DiscoveryService:
    """Discovers + resolves + registers local runtime models. Every dependency is
    injectable so the whole pipeline is unit-testable offline with a fake runtime."""

    def __init__(self, foundation_service=None, runtime_repo: Optional[RuntimeModelRepository] = None,
                 list_models_fn=None, provider_status_fn=None, bus=None) -> None:
        self._foundation = foundation_service
        self._repo = runtime_repo or SqlRuntimeModelRepository()
        self._list_models = list_models_fn
        self._provider_status = provider_status_fn
        self._bus = bus

    # -- lazy default wiring (kept out of __init__ so imports stay cheap) ------

    def _foundation_service(self):
        if self._foundation is not None:
            return self._foundation
        from app.foundation_models.service import foundation_model_service
        return foundation_model_service

    async def _models(self) -> list[str]:
        if self._list_models is not None:
            return await self._list_models()
        from app.foundation_models.runtime_adapter import list_runtime_models
        return await list_runtime_models()

    async def _status(self) -> dict:
        if self._provider_status is not None:
            return await self._provider_status()
        from app.foundation_models.runtime_adapter import runtime_provider_status
        return await runtime_provider_status()

    async def _emit(self, name: str, payload: dict) -> None:
        try:
            bus = self._bus
            if bus is None:
                from app.events import event_bus as bus
            await bus.publish(name, payload)
        except Exception:  # noqa: BLE001 - telemetry must never break discovery
            pass

    # -- reads ----------------------------------------------------------------

    async def list_tracked(self, *, provider: Optional[str] = None,
                           resolution: Optional[str] = None,
                           available: Optional[bool] = None) -> list[dict]:
        return [m.to_dict() for m in await self._repo.list(
            provider=provider, resolution=resolution, available=available)]

    async def list_unresolved(self) -> list[dict]:
        """Runtime models that are available but not confidently resolved — the ones
        needing an operator decision."""
        return [m.to_dict() for m in await self._repo.list(
            resolution=RuntimeResolutionStatus.NEEDS_RESOLUTION.value, available=True)]

    async def get_tracked(self, runtime_model_id: str) -> Optional[dict]:
        m = await self._repo.get(runtime_model_id)
        return m.to_dict() if m else None

    # -- discovery pipeline ---------------------------------------------------

    async def run_discovery(self) -> dict:
        """The startup/refresh/sync pipeline. Idempotent. Discovers installed
        runtime models, resolves + auto-registers the confident ones, records the
        rest as ``needs_resolution``, and reconciles availability (vanished models
        are marked unavailable, never deleted). Returns a summary."""
        status = await self._status()
        provider = status.get("name", "unknown")
        online = bool(status.get("online"))

        try:
            refs = await self._models()
        except Exception as exc:  # noqa: BLE001 - the whole point is to degrade honestly
            await self._emit(RUNTIME_SYNC_FAILED, {"provider": provider, "error": str(exc)})
            logger.warning("runtime discovery failed for provider %s: %s", provider, exc)
            return {"provider": provider, "online": online, "error": str(exc),
                    "discovered": 0, "resolved": 0, "needs_resolution": 0,
                    "registered": 0, "unavailable": 0}

        await self._emit(RUNTIME_MODELS_DISCOVERED,
                         {"provider": provider, "count": len(refs), "refs": refs})

        resolved_n = needs_n = registered_n = 0
        seen: set[str] = set()
        for ref in refs:
            seen.add(ref)
            outcome = await self._process_one(provider, ref)
            resolved_n += int(outcome["resolved"])
            needs_n += int(outcome["needs_resolution"])
            registered_n += int(outcome["registered"])

        # Availability reconciliation — only when the runtime gave us a trustworthy
        # listing. Offline/unreachable means "can't see", NOT "removed": we must not
        # mark models unavailable just because the runtime was briefly unreachable.
        unavailable_n = 0
        if online:
            for tracked in await self._repo.list(provider=provider, available=True):
                if tracked.runtime_ref not in seen:
                    tracked.available = False
                    tracked.updated_at = _utcnow()
                    await self._repo.update(tracked)
                    unavailable_n += 1

        summary = {"provider": provider, "online": online, "discovered": len(refs),
                   "resolved": resolved_n, "needs_resolution": needs_n,
                   "registered": registered_n, "unavailable": unavailable_n}
        await self._emit(RUNTIME_SYNC_COMPLETED, summary)
        logger.info("discovery: %s", summary)
        return summary

    async def _process_one(self, provider: str, ref: str) -> dict:
        """Resolve one runtime ref, auto-register if confident, and upsert its
        tracking row. Returns per-model outcome flags."""
        foundation = self._foundation_service()
        prior = await self._repo.get_by_ref(provider, ref)
        result = await foundation.resolve(ref)
        resolved = result.resolved

        fm_id = prior.foundation_model_id if prior else None
        confidence: Optional[float] = None
        resolution = RuntimeResolutionStatus.NEEDS_RESOLUTION
        newly_registered = False

        if resolved is not None:
            fm = await foundation.register(
                hf_repo=resolved.hf_repo, architecture=resolved.architecture,
                parameter_count=resolved.parameter_count, source="resolved_from_runtime",
                metadata={"resolved_from": ref, "confidence": resolved.confidence,
                          "reason": resolved.reason, "auto_resolved": True,
                          "runtime_provider": provider})
            confidence = resolved.confidence
            resolution = RuntimeResolutionStatus.RESOLVED
            # Emit registered only on a genuine new link (idempotent register may
            # have returned an existing identity) — avoids event spam on re-sync.
            newly_registered = not prior or prior.foundation_model_id != fm["id"]
            fm_id = fm["id"]
            await self._emit(FOUNDATION_MODEL_RESOLVED,
                             {"runtime_ref": ref, "provider": provider,
                              "foundation_model_id": fm_id, "hf_repo": resolved.hf_repo,
                              "confidence": resolved.confidence})
            if newly_registered:
                await self._emit(FOUNDATION_MODEL_REGISTERED,
                                 {"id": fm_id, "hf_repo": resolved.hf_repo,
                                  "source": "resolved_from_runtime", "runtime_ref": ref})

        record = DiscoveredRuntimeModel(
            id=(prior.id if prior else str(uuid4())), runtime_ref=ref, provider=provider,
            resolution=resolution, available=True, foundation_model_id=fm_id,
            confidence=confidence, candidates=[c.to_dict() for c in result.candidates],
            facts=result.facts or {}, last_synced_at=_utcnow(),
            created_at=(prior.created_at if prior else _utcnow()))
        await self._repo.upsert(record)

        return {"resolved": resolution == RuntimeResolutionStatus.RESOLVED,
                "needs_resolution": resolution == RuntimeResolutionStatus.NEEDS_RESOLUTION,
                "registered": newly_registered}

    # -- manual resolution ----------------------------------------------------

    async def resolve_one(self, runtime_model_id: str, hf_repo: Optional[str] = None) -> Optional[dict]:
        """Operator-driven resolution of a specific tracked runtime model. If
        ``hf_repo`` is given, register that identity directly (the 'I know what this
        is' path); otherwise adopt the top candidate. Registers the Foundation
        Model, links it, and flips the runtime model to ``resolved``. Returns the
        updated runtime model + the foundation model, or None if unknown."""
        tracked = await self._repo.get(runtime_model_id)
        if tracked is None:
            return None
        foundation = self._foundation_service()

        if hf_repo:
            fm = await foundation.register(
                hf_repo=hf_repo, source="resolved_from_runtime",
                metadata={"resolved_from": tracked.runtime_ref, "auto_resolved": False,
                          "manual": True, "runtime_provider": tracked.provider})
        else:
            if not tracked.candidates:
                return {"runtime_model": tracked.to_dict(), "foundation_model": None,
                        "note": "no candidates to resolve to; search Hugging Face or register manually"}
            best = tracked.candidates[0]
            fm = await foundation.register(
                hf_repo=best["hf_repo"], architecture=best.get("architecture"),
                parameter_count=best.get("parameter_count"), source="resolved_from_runtime",
                metadata={"resolved_from": tracked.runtime_ref, "confidence": best.get("confidence"),
                          "reason": best.get("reason"), "auto_resolved": False,
                          "runtime_provider": tracked.provider})

        tracked.foundation_model_id = fm["id"]
        tracked.resolution = RuntimeResolutionStatus.RESOLVED
        tracked.confidence = (fm.get("metadata") or {}).get("confidence")
        tracked.updated_at = _utcnow()
        updated = await self._repo.update(tracked)
        await self._emit(FOUNDATION_MODEL_RESOLVED,
                         {"runtime_ref": tracked.runtime_ref, "provider": tracked.provider,
                          "foundation_model_id": fm["id"], "hf_repo": fm["hf_repo"],
                          "confidence": tracked.confidence})
        await self._emit(FOUNDATION_MODEL_REGISTERED,
                         {"id": fm["id"], "hf_repo": fm["hf_repo"],
                          "source": "resolved_from_runtime", "runtime_ref": tracked.runtime_ref})
        return {"runtime_model": (updated or tracked).to_dict(), "foundation_model": fm}


# Module-level singleton (matches the codebase's service pattern). Tests construct
# their own instance with injected fakes.
discovery_service = DiscoveryService()


# ---------------------------------------------------------------------------
# Job integration — background discovery via the existing Job System (Epic 2).
# ---------------------------------------------------------------------------

async def _handle_runtime_discovery(job, ctx) -> "object":
    """The ``runtime_discovery`` Job handler: run the discovery pipeline in the
    background so startup/refresh never blocks the UI. Reuses the module singleton."""
    from app.jobs.domain import JobResult
    await ctx.report_progress(0.1, "scanning installed runtime models")
    summary = await discovery_service.run_discovery()
    await ctx.report_progress(1.0, "discovery complete")
    msg = (f"discovered {summary.get('discovered', 0)} runtime model(s); "
           f"{summary.get('resolved', 0)} resolved, {summary.get('needs_resolution', 0)} need attention")
    return JobResult(success="error" not in summary, data=summary, message=msg)


def register_discovery_handlers() -> None:
    """Register the ``runtime_discovery`` (and ``runtime_sync`` alias) job kinds.
    Additive; safe to call more than once."""
    from app.jobs.handlers import handler_registry
    from app.jobs.job_types import JobTypeDef, register_job_type
    register_job_type(JobTypeDef("runtime_discovery", "Runtime Discovery", concurrency=1))
    register_job_type(JobTypeDef("runtime_sync", "Runtime Sync", concurrency=1))
    handler_registry.register("runtime_discovery", _handle_runtime_discovery)
    handler_registry.register("runtime_sync", _handle_runtime_discovery)
