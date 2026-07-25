"""Foundation Platform — pure domain model (RedForge V3, Epic 1).

A **Foundation Model** is a *training-domain* model identity: a specific,
addressable set of pretrained weights in the Hugging Face ecosystem, independent
of any runtime and independent of any fine-tune (Constitution §5.4, §10.1).

This module is pure: no SQLAlchemy, no FastAPI, no I/O. It defines the domain
objects the Foundation Model and Model Resolution services operate on. Persistence
is the repository's job (:mod:`app.foundation_models.repository`); these objects
never touch the database. This is the layering the V3 Constitution mandates —
services own business logic over domain objects; repositories own persistence.

Critically: a Foundation Model is NOT a Runtime Model. The two are distinct
identities related only by derivation (train → checkpoint → export → runtime).
Nothing here merges them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WeightFormat(str, Enum):
    """The on-disk weight format of a foundation model's checkpoint."""
    SAFETENSORS = "safetensors"
    PYTORCH_BIN = "pytorch_bin"
    GGUF = "gguf"
    UNKNOWN = "unknown"


class Quantization(str, Enum):
    """Quantization scheme. A quantized variant is a DIFFERENT foundation model
    from its full-precision original — they are not interchangeable training
    inputs, so quantization is part of a foundation model's identity."""
    NONE = "none"
    BNB_4BIT = "bnb_4bit"
    BNB_8BIT = "bnb_8bit"
    GGUF_Q4_K_M = "gguf_q4_k_m"
    GGUF_Q5_K_M = "gguf_q5_k_m"
    GGUF_Q8_0 = "gguf_q8_0"
    OTHER = "other"
    UNKNOWN = "unknown"


class FoundationModelStatus(str, Enum):
    """Lifecycle status (Constitution §5.4: referenced → local → in-use → retained).

    Epic 1 tracks the reference/local distinction; download orchestration is a
    later epic (a Job), so ``DOWNLOADING`` is defined but not yet driven."""
    REFERENCED = "referenced"   # identity known, weights not local
    DOWNLOADING = "downloading"  # reserved for the Job-driven download (later epic)
    LOCAL = "local"             # weights cached on this machine
    INVALID = "invalid"         # a recorded, honest failure (e.g. cache vanished)


class ModelSource(str, Enum):
    """How this foundation-model identity entered RedForge."""
    HF_HUB = "hf_hub"                       # referenced/pulled from the Hub
    LOCAL_IMPORT = "local_import"           # imported from a local path
    RESOLVED_FROM_RUNTIME = "resolved_from_runtime"  # inferred from an installed runtime model


def _coerce(enum_cls, value, default):
    """Best-effort enum coercion — unknown strings degrade to a sensible default
    rather than raising, so a hand-authored or legacy value never crashes a read."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


@dataclass
class FoundationModel:
    """A training-domain model identity. Identity is (hf_repo, revision, format,
    quantization) — two rows differing only in quantization are different models."""

    id: str
    hf_repo: str                                    # e.g. "meta-llama/Llama-3.1-8B-Instruct"
    revision: Optional[str] = None                  # pinned commit SHA (optional)
    architecture: Optional[str] = None              # llama, qwen2, mistral, phi3, ...
    parameter_count: Optional[int] = None           # raw parameter count if known
    format: WeightFormat = WeightFormat.SAFETENSORS
    quantization: Quantization = Quantization.NONE
    status: FoundationModelStatus = FoundationModelStatus.REFERENCED
    source: ModelSource = ModelSource.HF_HUB
    license: Optional[str] = None
    cache_path: Optional[str] = None                # local weights dir; None = not yet local
    checksum: Optional[str] = None                  # populated once local + verified
    metadata: dict = field(default_factory=dict)    # provider/HF metadata, resolution evidence, etc.
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    # -- identity --------------------------------------------------------------

    @property
    def identity_key(self) -> str:
        """The tuple that uniquely identifies this foundation model, as a string.
        Used by the repository to dedupe on register (a re-register of the same
        identity returns the existing row rather than creating a duplicate)."""
        return f"{self.hf_repo}@{self.revision or 'latest'}|{self.format.value}|{self.quantization.value}"

    @property
    def is_local(self) -> bool:
        return self.status == FoundationModelStatus.LOCAL

    # -- serialization ---------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hf_repo": self.hf_repo,
            "revision": self.revision,
            "architecture": self.architecture,
            "parameter_count": self.parameter_count,
            "format": self.format.value,
            "quantization": self.quantization.value,
            "status": self.status.value,
            "source": self.source.value,
            "license": self.license,
            "cache_path": self.cache_path,
            "checksum": self.checksum,
            "metadata": self.metadata or {},
            "identity_key": self.identity_key,
            "is_local": self.is_local,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def coerce_format(value) -> WeightFormat:
        return _coerce(WeightFormat, value, WeightFormat.UNKNOWN)

    @staticmethod
    def coerce_quantization(value) -> Quantization:
        return _coerce(Quantization, value, Quantization.UNKNOWN)

    @staticmethod
    def coerce_status(value) -> FoundationModelStatus:
        return _coerce(FoundationModelStatus, value, FoundationModelStatus.REFERENCED)

    @staticmethod
    def coerce_source(value) -> ModelSource:
        return _coerce(ModelSource, value, ModelSource.HF_HUB)


# ---------------------------------------------------------------------------
# Model Resolution domain (runtime model  ->  foundation model identity)
# ---------------------------------------------------------------------------

@dataclass
class ResolutionCandidate:
    """One possible foundation-model identity for a runtime model, with the
    evidence and confidence behind it. Never presented as fact unless a single
    high-confidence candidate exists (Constitution §2.14 — honest over simulated)."""

    hf_repo: str
    confidence: float                 # 0.0–1.0
    reason: str                       # human-readable evidence
    architecture: Optional[str] = None
    parameter_count: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "hf_repo": self.hf_repo,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "architecture": self.architecture,
            "parameter_count": self.parameter_count,
        }


@dataclass
class ResolutionResult:
    """The outcome of resolving a runtime model to a foundation-model identity.

    ``resolved`` is only set when exactly one unambiguous, high-confidence
    candidate exists; otherwise it is None and the caller presents ``candidates``
    for the operator to confirm (ambiguity handling)."""

    runtime_ref: str
    candidates: list[ResolutionCandidate] = field(default_factory=list)
    resolved: Optional[ResolutionCandidate] = None
    facts: dict = field(default_factory=dict)   # raw introspected facts (evidence)

    @property
    def is_ambiguous(self) -> bool:
        return self.resolved is None and len(self.candidates) > 1

    def to_dict(self) -> dict:
        return {
            "runtime_ref": self.runtime_ref,
            "candidates": [c.to_dict() for c in self.candidates],
            "resolved": self.resolved.to_dict() if self.resolved else None,
            "is_ambiguous": self.is_ambiguous,
            "facts": self.facts or {},
        }


class RuntimeResolutionStatus(str, Enum):
    """Where a *discovered runtime model* sits on the resolution axis (Epic 4.5).

    This is distinct from runtime *availability* (whether the model is currently
    installed/served) — a model can be RESOLVED yet not currently available. The
    two axes are stored separately so a Foundation identity, once resolved, is
    never lost just because the runtime model was removed."""
    RESOLVED = "resolved"                 # confidently mapped to a Foundation identity
    NEEDS_RESOLUTION = "needs_resolution"  # discovered, but no confident mapping — operator decides
    UNRESOLVED = "unresolved"              # not yet attempted


@dataclass
class DiscoveredRuntimeModel:
    """A runtime model RedForge found installed locally (e.g. an Ollama tag) plus
    the outcome of resolving it to a Foundation identity (Epic 4.5).

    RuntimeModel and FoundationModel remain *separate identities* (Constitution
    §5.4, §11.2): this record represents runtime **availability + resolution
    state**, linking to a Foundation identity by reference (``foundation_model_id``)
    when one was confidently resolved. It is never merged into ``FoundationModel``."""

    id: str
    runtime_ref: str                                 # e.g. "llama3.1:8b"
    provider: str = "ollama"                          # detected runtime provider
    resolution: RuntimeResolutionStatus = RuntimeResolutionStatus.UNRESOLVED
    available: bool = True                             # currently served by the runtime?
    foundation_model_id: Optional[str] = None          # set when resolved+registered
    confidence: Optional[float] = None                 # confidence of the auto-resolution
    candidates: list = field(default_factory=list)     # candidate dicts when ambiguous
    facts: dict = field(default_factory=dict)          # introspected evidence
    last_synced_at: datetime = field(default_factory=_utcnow)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @property
    def display_status(self) -> str:
        """The single status the UI shows: availability trumps resolution so an
        offline model reads honestly as 'unavailable' regardless of its mapping."""
        if not self.available:
            return "unavailable"
        return self.resolution.value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "runtime_ref": self.runtime_ref,
            "provider": self.provider,
            "resolution": self.resolution.value,
            "available": self.available,
            "status": self.display_status,
            "foundation_model_id": self.foundation_model_id,
            "confidence": round(self.confidence, 3) if self.confidence is not None else None,
            "candidates": self.candidates or [],
            "facts": self.facts or {},
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def coerce_resolution(value) -> "RuntimeResolutionStatus":
        return _coerce(RuntimeResolutionStatus, value, RuntimeResolutionStatus.UNRESOLVED)


@dataclass
class RuntimeModelFacts:
    """Introspected facts about a runtime model, extracted by a ModelResolver from
    whatever the runtime actually exposes. The raw material resolution scores
    candidates against."""

    runtime_ref: str
    family: Optional[str] = None
    parameter_size: Optional[str] = None    # e.g. "8.0B" as the runtime reports it
    quantization_level: Optional[str] = None
    from_reference: Optional[str] = None     # a Modelfile FROM line / source pointer, if any
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "runtime_ref": self.runtime_ref,
            "family": self.family,
            "parameter_size": self.parameter_size,
            "quantization_level": self.quantization_level,
            "from_reference": self.from_reference,
        }
