"""Foundation Platform — Model Resolution Service (RedForge V3, Epic 1).

Maps a **runtime model** the operator already has (e.g. an Ollama tag) to its
likely **foundation-model identity** (a Hugging Face repo), and back. This closes
the gap the whole V3 redesign turns on: an installed GGUF has no reliable pointer
to the HF checkpoint it came from, so "fine-tune the model I already have" is
impossible without this bridge.

Honesty is constitutional here (§2.14): resolution is **confidence-scored and
evidence-bearing**, never a silent guess presented as fact. A single unambiguous,
high-confidence candidate auto-resolves; anything else returns candidates for the
operator to confirm. The reverse direction (foundation → runtime) is exact when it
can be — it reports only runtime models RedForge can actually see are derived.

Resolution is deterministic (§2.11): the same facts always yield the same result.
It is isolated behind :class:`ModelResolver` implementations (one per runtime
family, registered like every other provider) so a new runtime's introspection is
a one-file addition.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional

from app.foundation_models.domain import ResolutionCandidate, ResolutionResult, RuntimeModelFacts
from app.foundation_models.runtime_adapter import IntrospectFn, default_introspect

# ---------------------------------------------------------------------------
# Curated mapping catalog — (family, parameter bucket) -> candidate HF repos.
# Small, hand-curated, extensible (the same shape as onboarding's model catalog).
# Order within a list is preference order; the first is the canonical original.
# ---------------------------------------------------------------------------

_CATALOG: dict[tuple[str, str], list[str]] = {
    ("llama", "1b"): ["meta-llama/Llama-3.2-1B"],
    ("llama", "3b"): ["meta-llama/Llama-3.2-3B"],
    ("llama", "8b"): ["meta-llama/Llama-3.1-8B", "meta-llama/Meta-Llama-3-8B"],
    ("llama", "70b"): ["meta-llama/Llama-3.3-70B-Instruct", "meta-llama/Meta-Llama-3-70B"],
    ("qwen", "1.5b"): ["Qwen/Qwen2.5-1.5B"],
    ("qwen", "3b"): ["Qwen/Qwen2.5-3B"],
    ("qwen", "7b"): ["Qwen/Qwen2.5-7B"],
    ("qwen", "14b"): ["Qwen/Qwen2.5-14B"],
    ("qwen2", "7b"): ["Qwen/Qwen2.5-7B"],
    # Qwen3 family (Ollama reports details.family == "qwen3"). Canonical HF repos.
    ("qwen3", "0.6b"): ["Qwen/Qwen3-0.6B"],
    ("qwen3", "1.7b"): ["Qwen/Qwen3-1.7B"],
    ("qwen3", "4b"): ["Qwen/Qwen3-4B"],
    ("qwen3", "8b"): ["Qwen/Qwen3-8B"],
    ("qwen3", "14b"): ["Qwen/Qwen3-14B"],
    ("qwen3", "32b"): ["Qwen/Qwen3-32B"],
    ("mistral", "7b"): ["mistralai/Mistral-7B-v0.3", "mistralai/Mistral-7B-Instruct-v0.3"],
    ("phi3", "3.8b"): ["microsoft/Phi-3-mini-4k-instruct"],
    ("phi", "3.8b"): ["microsoft/Phi-3-mini-4k-instruct"],
    ("gemma", "2b"): ["google/gemma-2-2b"],
    ("gemma", "9b"): ["google/gemma-2-9b"],
}

# Known parameter buckets we normalize a reported size to (in billions).
_BUCKETS_B = [0.5, 0.6, 1.0, 1.5, 1.7, 2.0, 3.0, 3.8, 4.0, 7.0, 8.0, 9.0, 13.0, 14.0, 30.0, 32.0, 34.0, 70.0]

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b", re.IGNORECASE)
_HF_REPO_RE = re.compile(r"([A-Za-z0-9][\w.-]+/[\w.-]+)")

# Known model FAMILIES, most-specific first ("qwen3" before "qwen"). The model NAME is
# the reliable signal for family; a runtime's introspected ``family`` is often the
# ARCHITECTURE instead (e.g. Ollama reports Mistral's family as "llama"), which
# mis-maps the catalog — so a name match takes precedence.
_FAMILY_TOKENS = ("llama", "qwen3", "qwen2", "qwen", "mistral", "phi3", "phi", "gemma")


def _family_from_name(ref: Optional[str]) -> Optional[str]:
    low = (ref or "").lower()
    return next((f for f in _FAMILY_TOKENS if f in low), None)


def _normalize_bucket(parameter_size: Optional[str]) -> Optional[str]:
    """'8.0B' / '7b' / '13B' -> a canonical bucket key like '8b'. Deterministic."""
    if not parameter_size:
        return None
    m = _SIZE_RE.search(parameter_size)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    nearest = min(_BUCKETS_B, key=lambda b: abs(b - val))
    # keep the '.5'/'.8' style buckets exact, integers as ints
    text = str(nearest).rstrip("0").rstrip(".") if nearest != int(nearest) else str(int(nearest))
    return f"{text}b"


def _bucket_to_params(bucket: Optional[str]) -> Optional[int]:
    if not bucket:
        return None
    m = _SIZE_RE.search(bucket)
    if not m:
        return None
    try:
        return int(float(m.group(1)) * 1_000_000_000)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Resolvers — one per runtime family. Introspect whatever the runtime exposes.
# ---------------------------------------------------------------------------

class ModelResolver(ABC):
    """Extracts structured facts from a runtime model. Registered per runtime
    family; adding a runtime's introspection is a one-class addition."""

    name: str = "resolver"

    @abstractmethod
    async def introspect(self, runtime_ref: str) -> RuntimeModelFacts: ...


class OllamaResolver(ModelResolver):
    """Reads Ollama's ``/api/show`` payload — the richest local introspection:
    ``details.family``, ``details.parameter_size``, ``details.quantization_level``,
    and the Modelfile ``FROM`` line (which sometimes names the source directly)."""

    name = "ollama"

    def __init__(self, introspect_fn: Optional[IntrospectFn] = None) -> None:
        self._introspect = introspect_fn or default_introspect

    async def introspect(self, runtime_ref: str) -> RuntimeModelFacts:
        raw = await self._introspect(runtime_ref) or {}
        details = raw.get("details") or {}
        modelfile = raw.get("modelfile") or ""
        from_ref = None
        for line in modelfile.splitlines():
            s = line.strip()
            if s.upper().startswith("FROM "):
                from_ref = s[5:].strip()
                break
        # Size: prefer the runtime's reported parameter_size; else parse it from the
        # NAME (e.g. "qwen3:4b") so models that aren't currently installed in Ollama
        # (no /api/show payload) still resolve from their tag alone.
        size = details.get("parameter_size")
        if not size:
            m = _SIZE_RE.search(runtime_ref.lower())
            size = m.group(0) if m else None
        return RuntimeModelFacts(
            runtime_ref=runtime_ref,
            # Prefer the family implied by the model NAME; fall back to the runtime's
            # reported family (which may be the architecture, e.g. Mistral → "llama").
            family=_family_from_name(runtime_ref) or details.get("family"),
            parameter_size=size,
            quantization_level=details.get("quantization_level"),
            from_reference=from_ref,
            raw={"details": details},
        )


class GenericResolver(ModelResolver):
    """Fallback for runtimes with no reliable introspection API — derives what it
    can from the model name alone (family keyword + a size token)."""

    name = "generic"

    async def introspect(self, runtime_ref: str) -> RuntimeModelFacts:
        low = runtime_ref.lower()
        family = _family_from_name(runtime_ref)
        m = _SIZE_RE.search(low)
        return RuntimeModelFacts(
            runtime_ref=runtime_ref,
            family=family,
            parameter_size=(m.group(0) if m else None),
            quantization_level=None,
            from_reference=None,
            raw={"derived_from": "name"},
        )


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------

class ModelResolutionService:
    """Runtime <-> Foundation resolution. Keeps resolution logic isolated from the
    Foundation registry (the FoundationModelService composes this service; it does
    not reimplement it)."""

    # A single unambiguous candidate must clear this to auto-resolve.
    AUTO_RESOLVE_THRESHOLD = 0.85
    # ...and must beat the runner-up by at least this margin.
    AUTO_RESOLVE_MARGIN = 0.15

    def __init__(self, introspect_fn: Optional[IntrospectFn] = None,
                 provider_name: Optional[str] = None) -> None:
        # Resolvers are keyed by runtime family; default set mirrors the built-in
        # runtime providers. Injectable introspect_fn keeps this offline-testable.
        self._resolvers: dict[str, ModelResolver] = {
            "ollama": OllamaResolver(introspect_fn),
            "generic": GenericResolver(),
        }
        self._forced_provider = provider_name  # tests can pin the resolver

    def _resolver_for_active_provider(self) -> ModelResolver:
        name = self._forced_provider
        if name is None:
            try:
                from app.config import settings
                name = settings.RUNTIME_PROVIDER.lower()
            except Exception:  # noqa: BLE001
                name = "generic"
        return self._resolvers.get(name, self._resolvers["generic"])

    # -- runtime -> foundation ------------------------------------------------

    async def resolve_runtime_to_foundation(self, runtime_ref: str) -> ResolutionResult:
        """Introspect a runtime model and score candidate foundation identities."""
        resolver = self._resolver_for_active_provider()
        facts = await resolver.introspect(runtime_ref)
        candidates = self._score_candidates(facts)
        resolved = self._pick_resolved(candidates)
        return ResolutionResult(
            runtime_ref=runtime_ref, candidates=candidates,
            resolved=resolved, facts=facts.to_dict(),
        )

    def _score_candidates(self, facts: RuntimeModelFacts) -> list[ResolutionCandidate]:
        candidates: list[ResolutionCandidate] = []
        seen: set[str] = set()

        def add(repo: str, confidence: float, reason: str):
            if repo in seen:
                return
            seen.add(repo)
            candidates.append(ResolutionCandidate(
                hf_repo=repo, confidence=confidence, reason=reason,
                architecture=facts.family,
                parameter_count=_bucket_to_params(_normalize_bucket(facts.parameter_size)),
            ))

        # (1) Strongest evidence: a Modelfile FROM line that names an HF-style repo.
        if facts.from_reference:
            m = _HF_REPO_RE.search(facts.from_reference)
            if m and "/" in m.group(1) and not facts.from_reference.startswith(("/", ".", "~")):
                add(m.group(1), 0.95, "Modelfile FROM line names a Hugging Face repo")

        # (2) Catalog match on (family, parameter bucket).
        bucket = _normalize_bucket(facts.parameter_size)
        fam = (facts.family or "").lower()
        if fam and bucket:
            repos = _CATALOG.get((fam, bucket), [])
            if repos:
                # Single catalog candidate -> high confidence; multiple -> split lower
                # (kept ambiguous for Discovery; the Training seam picks the canonical).
                base = 0.88 if len(repos) == 1 else 0.72
                for i, repo in enumerate(repos):
                    add(repo, round(base - i * 0.05, 3),
                        f"family '{fam}' + size '{bucket}' match in curated catalog")

        # (3) Family-only weak signal (no size, or size not in catalog).
        if fam and not any(c.reason.startswith("family") or "FROM" in c.reason for c in candidates):
            fam_repos = sorted({r for (f, _b), repos in _CATALOG.items() if f == fam for r in repos})
            for repo in fam_repos[:3]:
                add(repo, 0.45, f"family '{fam}' match only (size unknown)")

        candidates.sort(key=lambda c: (-c.confidence, c.hf_repo))
        return candidates

    def _pick_resolved(self, candidates: list[ResolutionCandidate]) -> Optional[ResolutionCandidate]:
        if not candidates:
            return None
        top = candidates[0]
        if top.confidence < self.AUTO_RESOLVE_THRESHOLD:
            return None
        if len(candidates) == 1:
            return top
        if top.confidence - candidates[1].confidence >= self.AUTO_RESOLVE_MARGIN:
            return top
        return None  # ambiguous — let the operator confirm

    # -- foundation -> runtime (reverse lineage) ------------------------------

    async def resolve_foundation_to_runtime(self, foundation: "object",
                                            session_factory=None) -> list[dict]:
        """Report runtime models RedForge can see are derived from this foundation
        model. Today, before the Export/Artifact epics exist, this is a best-effort
        read over the existing Runtime Registry (registered checkpoints whose base
        model matches). It is honest: an empty list means "nothing derived yet",
        never a fabricated mapping. Exactness improves automatically once the Export
        pipeline records real lineage (later epic)."""
        hf_repo = getattr(foundation, "hf_repo", None)
        if not hf_repo:
            return []
        try:
            from app.runtime_registry import runtime_registry
            factory = session_factory
            if factory is None:
                from app.db.database import AsyncSessionLocal
                factory = AsyncSessionLocal
            async with factory() as db:
                registered = await runtime_registry.list(db)
        except Exception:  # noqa: BLE001
            return []
        # Match on base_model containing the repo's short name (best-effort, honest).
        short = hf_repo.split("/")[-1].lower()
        out = []
        for m in registered:
            base = (m.get("base_model") or "").lower()
            if short and (short in base or base in short):
                out.append({
                    "registry_id": m.get("id"), "runtime_model": m.get("runtime_model"),
                    "label": m.get("label"), "provider": m.get("provider"),
                    "fallback": m.get("fallback"), "match": "base_model name",
                })
        return out
