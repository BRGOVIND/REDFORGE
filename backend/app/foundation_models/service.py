"""Foundation Platform — application service (RedForge V3, Epic 1).

Owns the business logic of the Foundation Model bounded context. Depends on the
:class:`FoundationModelRepository` *interface* (dependency inversion) and composes
the :class:`ModelResolutionService` — it never touches SQLAlchemy and never
reimplements resolution. This is the V3 layering: services own logic, repositories
own persistence, resolution stays isolated.

Responsibilities (Epic 1 scope): register, list, get, resolve, discover, sync,
cache, and the Training compatibility seam (``ensure_foundation_for_base_model``).
Actual weight downloading and checksum-over-large-files are Job-driven work for a
later epic; here those degrade honestly (offline-safe, status-truthful) rather
than pretending.
"""
from __future__ import annotations

import os
from typing import Optional
from uuid import uuid4

from app.foundation_models.domain import (
    FoundationModel,
    FoundationModelStatus,
    ModelSource,
    Quantization,
    ResolutionResult,
    WeightFormat,
)
from app.foundation_models.repository import FoundationModelRepository, SqlFoundationModelRepository
from app.foundation_models.resolution import ModelResolutionService
from app.foundation_models.runtime_adapter import list_runtime_models
from app.logging_config import get_logger

logger = get_logger("foundation-models")


class FoundationModelService:
    """The Foundation Model context's public API. Constructed with an injectable
    repository and resolution service so it is fully unit-testable without a live
    DB or provider."""

    def __init__(self, repository: Optional[FoundationModelRepository] = None,
                 resolution: Optional[ModelResolutionService] = None) -> None:
        self._repo = repository or SqlFoundationModelRepository()
        self._resolution = resolution or ModelResolutionService()

    # -- register / read ------------------------------------------------------

    async def register(self, *, hf_repo: str, revision: Optional[str] = None,
                       architecture: Optional[str] = None, parameter_count: Optional[int] = None,
                       format: str = "safetensors", quantization: str = "none",
                       source: str = "hf_hub", license: Optional[str] = None,
                       cache_path: Optional[str] = None, metadata: Optional[dict] = None) -> dict:
        """Register a foundation-model identity. Idempotent on identity
        (hf_repo@revision|format|quantization): re-registering the same identity
        returns the existing record rather than creating a duplicate."""
        model = FoundationModel(
            id=str(uuid4()), hf_repo=hf_repo.strip(), revision=revision,
            architecture=architecture, parameter_count=parameter_count,
            format=FoundationModel.coerce_format(format),
            quantization=FoundationModel.coerce_quantization(quantization),
            source=FoundationModel.coerce_source(source), license=license,
            cache_path=cache_path, metadata=metadata or {},
        )
        # Status is honest about locality from the start.
        model.status = self._status_for(cache_path)
        existing = await self._repo.get_by_identity(model.identity_key)
        if existing is not None:
            return existing.to_dict()
        created = await self._repo.add(model)
        logger.info("registered foundation model %s (%s)", created.id, created.hf_repo)
        return created.to_dict()

    async def get(self, model_id: str) -> Optional[dict]:
        m = await self._repo.get(model_id)
        return m.to_dict() if m else None

    async def list(self, *, status: Optional[str] = None, source: Optional[str] = None,
                   limit: int = 200) -> list[dict]:
        return [m.to_dict() for m in await self._repo.list(status=status, source=source, limit=limit)]

    async def delete(self, model_id: str) -> bool:
        return await self._repo.delete(model_id)

    # -- resolve --------------------------------------------------------------

    async def resolve(self, runtime_ref: str) -> ResolutionResult:
        """Resolve a runtime model to candidate foundation identities. Delegates to
        the isolated resolution service — no resolution logic lives here."""
        return await self._resolution.resolve_runtime_to_foundation(runtime_ref)

    async def runtimes_for(self, model_id: str, session_factory=None) -> list[dict]:
        """Reverse lineage: runtime models derived from this foundation model."""
        m = await self._repo.get(model_id)
        if m is None:
            return []
        return await self._resolution.resolve_foundation_to_runtime(m, session_factory=session_factory)

    # -- discover -------------------------------------------------------------

    async def discover(self) -> list[dict]:
        """Propose foundation-model candidates from the runtime models the operator
        already has installed. Each installed runtime model is resolved; those with
        a confident candidate become registerable suggestions. Offline-honest:
        returns [] if the runtime is unreachable. Nothing is persisted here —
        discovery proposes; ``register`` disposes."""
        installed = await list_runtime_models()
        out: list[dict] = []
        for ref in installed:
            result = await self._resolution.resolve_runtime_to_foundation(ref)
            best = result.resolved or (result.candidates[0] if result.candidates else None)
            out.append({
                "runtime_ref": ref,
                "suggested": best.to_dict() if best else None,
                "candidate_count": len(result.candidates),
                "is_ambiguous": result.is_ambiguous,
            })
        return out

    # -- sync / cache ---------------------------------------------------------

    async def sync(self, model_id: str) -> Optional[dict]:
        """Reconcile a foundation model's recorded state with the local filesystem:
        verify the cache path still exists and update ``status`` truthfully. Real
        Hub-metadata refresh is a network op that degrades honestly offline (it is
        skipped, not faked). Returns the updated record."""
        m = await self._repo.get(model_id)
        if m is None:
            return None
        m.status = self._status_for(m.cache_path)
        if m.cache_path and not self._path_exists(m.cache_path):
            # Recorded as local but the files are gone — mark honestly.
            m.status = FoundationModelStatus.INVALID
            m.metadata = {**(m.metadata or {}), "sync_note": "cache_path missing on disk"}
        updated = await self._repo.update(m)
        return updated.to_dict() if updated else None

    async def cache(self, model_id: str, cache_path: str) -> Optional[dict]:
        """Record that a foundation model's weights are locally available at
        ``cache_path`` and update status. Epic 1 records/verifies an already-present
        local path; it does NOT download (downloading is a Job in a later epic). If
        the path does not exist, the status is left honest (not flipped to local)."""
        m = await self._repo.get(model_id)
        if m is None:
            return None
        m.cache_path = cache_path
        m.status = self._status_for(cache_path)
        updated = await self._repo.update(m)
        return updated.to_dict() if updated else None

    # -- Training compatibility seam (does NOT modify Training) ----------------

    async def ensure_foundation_for_base_model(self, base_model: str) -> dict:
        """The strangler-fig seam between the existing Training subsystem and the
        Foundation Platform. Given a legacy ``base_model`` string (an Ollama tag or
        an HF repo), resolve/register the corresponding foundation-model identity
        and return it — WITHOUT modifying Training. Training does not call this yet
        (that wiring is a later epic); the seam exists, is tested, and is ready.

        Resolution rules:
          * If the string already looks like an HF repo (``owner/name``), register
            it directly with source ``hf_hub``.
          * Otherwise treat it as a runtime model, resolve it, and register the
            confident candidate with source ``resolved_from_runtime`` (recording the
            confidence/evidence in metadata). If resolution is not confident, still
            register an honest ``referenced`` identity carrying the raw string and a
            note that it is unverified — never a silently-fabricated identity."""
        base = base_model.strip()
        if "/" in base and " " not in base and not base.startswith(("/", ".", "~")):
            return await self.register(hf_repo=base, source="hf_hub")

        result = await self._resolution.resolve_runtime_to_foundation(base)
        best = result.resolved
        # Training needs ONE concrete base model. When resolution is not auto-confident
        # but the top candidate is a strong (family+size) catalog match, use its
        # canonical first repo (e.g. mistral:latest → mistralai/Mistral-7B-v0.3). This
        # is a Training-seam policy only; Discovery keeps its stricter ambiguity
        # semantics (it lets the operator choose among generations/variants).
        if best is None and result.candidates:
            top = result.candidates[0]
            if "curated catalog" in top.reason and top.confidence >= 0.7:
                best = top
        if best is not None:
            return await self.register(
                hf_repo=best.hf_repo, architecture=best.architecture,
                parameter_count=best.parameter_count, source="resolved_from_runtime",
                metadata={"resolved_from": base, "confidence": best.confidence,
                          "reason": best.reason, "auto_resolved": True},
            )
        # Honest fallback: record the unverified identity, do not fabricate a repo.
        note = ("no confident foundation-model match; recorded as unverified. "
                f"{len(result.candidates)} candidate(s) available for confirmation.")
        return await self.register(
            hf_repo=base, source="resolved_from_runtime",
            metadata={"resolved_from": base, "auto_resolved": False, "unverified": True,
                      "note": note, "candidates": [c.to_dict() for c in result.candidates]},
        )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _path_exists(path: Optional[str]) -> bool:
        try:
            return bool(path) and os.path.exists(path)
        except Exception:  # noqa: BLE001
            return False

    def _status_for(self, cache_path: Optional[str]) -> FoundationModelStatus:
        if cache_path and self._path_exists(cache_path):
            return FoundationModelStatus.LOCAL
        return FoundationModelStatus.REFERENCED


# Module-level singleton (consistent with the codebase's service pattern). Uses the
# default SQL repository + default resolution; tests construct their own instances
# with injected fakes.
foundation_model_service = FoundationModelService()
