# RedForge V3 — Epic 1: Foundation Platform (Implementation Notes)

**Status:** Shipped. Additive, non-breaking. Follows the V3 Constitution.
**Scope:** The Foundation Model bounded context only. No Training/Runtime/Benchmark/
Evaluation/Security behavior changed. No Artifact Registry, Job System, Experiments,
Export Engine, or Plugin System — those are later epics.

This document records *what was built* and *how it maps to the Constitution*. It is
an implementation companion to `REDFORGE_V3_CONSTITUTION.md` (§3.6, §5.4, §9, §10.1)
and `TRAINING_FOUNDATION_ARCHITECTURE.md` (§1–3).

---

## 1. What This Epic Delivers

The **Foundation Model Platform** — the training-domain model-identity bounded
context. A `FoundationModel` is what a training provider *loads* (a Hugging Face
checkpoint), as distinct from a Runtime Model, which is what the Runtime Manager
*serves*. The two are **separate identities related only by derivation** — the exact
conflation the whole V3 redesign exists to correct. This epic introduces the new
identity and the resolution bridge between the two, **without** touching Training or
Runtime.

It is the first V3-pattern-compliant bounded context in the codebase: it introduces
the **repository pattern + dependency inversion** the Constitution mandates (services
depend on a repository *interface*, never on SQLAlchemy). Existing contexts migrate
toward this pattern in later epics; Foundation Platform is the reference.

---

## 2. New Bounded Context — `app/foundation_models/`

| Module | Layer | Responsibility |
|---|---|---|
| `domain.py` | Domain (pure) | `FoundationModel` dataclass, resolution value types (`ResolutionResult`, `ResolutionCandidate`, `RuntimeModelFacts`), enums (`WeightFormat`, `Quantization`, `FoundationModelStatus`, `ModelSource`). No SQLAlchemy, no I/O. |
| `repository.py` | Persistence boundary | `FoundationModelRepository` (ABC) + `SqlFoundationModelRepository` (SQLAlchemy impl). Maps the ORM row ↔ the pure domain object in both directions. The **only** place that knows the ORM row exists. |
| `service.py` | Application service | `FoundationModelService` — register/list/get/resolve/discover/sync/cache + the Training compatibility seam. Depends on the repository *interface*. Composes the resolution service. |
| `resolution.py` | Isolated capability | `ModelResolutionService` + `ModelResolver` (ABC) + `OllamaResolver` + `GenericResolver` + curated mapping catalog. Runtime↔Foundation mapping, confidence-scored. |
| `runtime_adapter.py` | Read-only Runtime seam | Reads the Runtime Manager (`get_runtime()`) for introspection. Injectable; offline-honest. Runtime remains entirely unaware of it. |
| `__init__.py` | Public API | Exports + the `foundation_model_service` singleton. |

**Layering (Constitution §4):** domain (pure) → repository (persistence) → service
(logic) → resolution (isolated). Dependencies flow downward only.

---

## 3. Canonical Domain Model

`FoundationModel` (matches Constitution §5.4):

| Field | Meaning |
|---|---|
| `id` | uuid4 |
| `hf_repo` | Hugging Face repo id (e.g. `meta-llama/Llama-3.1-8B`) |
| `revision` | pinned commit SHA (optional) |
| `architecture` | llama / qwen2 / mistral / phi3 / … |
| `parameter_count` | raw parameter count if known |
| `format` | `WeightFormat` — safetensors / pytorch_bin / gguf / unknown |
| `quantization` | `Quantization` — none / bnb_4bit / bnb_8bit / gguf_q4_k_m / … **(part of identity)** |
| `status` | `FoundationModelStatus` — referenced / downloading / local / invalid |
| `source` | `ModelSource` — hf_hub / local_import / resolved_from_runtime |
| `license`, `cache_path`, `checksum` | provenance / locality |
| `metadata` | provider/HF metadata + resolution evidence |

**Identity** is `(hf_repo, revision, format, quantization)` — a quantized variant is a
*different* foundation model from its full-precision original (they are not
interchangeable training inputs). Register is idempotent on this identity.

**RuntimeModel is NOT merged with FoundationModel.** The existing `RegisteredModel`
(Runtime Registry) remains the runtime-model identity; nothing in this epic touches
it beyond reading it (read-only) for reverse-lineage.

---

## 4. Model Resolution (Constitution §2.14 — honest over simulated)

`ModelResolutionService.resolve_runtime_to_foundation(runtime_ref)`:
1. A `ModelResolver` (one per runtime family) introspects the runtime model.
   `OllamaResolver` reads `/api/show` — `details.family`, `details.parameter_size`,
   `details.quantization_level`, and the Modelfile `FROM` line. `GenericResolver`
   falls back to name-pattern matching.
2. Candidates are scored against a **curated catalog** (`(family, param-bucket) →
   HF repos`) plus strong direct evidence (a `FROM` line naming an HF repo scores
   ~0.95).
3. A single unambiguous, high-confidence candidate **auto-resolves**
   (`confidence ≥ 0.85`, and beats the runner-up by `≥ 0.15`); anything else returns
   `resolved=None` with the candidate list for the operator to confirm (ambiguity
   handling). **Never a silent guess presented as fact.**

Resolution is **deterministic** (§2.11): identical facts always yield identical
results.

Reverse direction (`resolve_foundation_to_runtime`) is a **lineage read** — honest
and exact where it can be. Until the Export/Artifact epics record real derivations,
it best-effort reads the existing Runtime Registry; an empty result means "nothing
derived yet," never a fabricated mapping.

---

## 5. Compatibility Layer (nothing existing modified)

### Runtime (unchanged)
The Constitution forbids Runtime from knowing about Foundation Models (§11.2). The
dependency is one-directional: **Foundation reads Runtime; Runtime never reads
Foundation.** `runtime_adapter.py` is that read-only seam — it calls the Runtime
Manager's public `show_model`/`list_models` only, modifies nothing, and the Runtime
Engine gains no awareness of foundation models. It is injectable so resolution is
fully testable offline.

### Training (unchanged)
Training is **not modified**. The strangler-fig seam is
`FoundationModelService.ensure_foundation_for_base_model(base_model)` (also exposed
at `POST /api/foundation-models/ensure`): given a legacy `base_model` string, it
resolves/registers the corresponding foundation-model identity and returns it —
without Training calling it yet (that wiring is a later epic). The seam exists, is
tested, and is ready. **No column was added to `training_runs`** (honoring "create
new tables only"); the association will be wired when Training adopts the seam.

---

## 6. Database (additive only)

**One new table:** `foundation_models` (a new `Base` subclass, provisioned by
`create_all` at startup). **No existing table altered** — no column added, renamed,
or removed anywhere. `FoundationModelRecord` lives in `db/models.py` for `create_all`
registration but is touched only by the repository — no service imports it.

---

## 7. API (additive) — `/api/foundation-models`

Literal routes precede `/{model_id}` (route-ordering convention preserved).

| Method | Path | Purpose |
|---|---|---|
| GET | `/discover` | Propose foundation candidates from installed runtime models (read-only) |
| POST | `/resolve` | Resolve a runtime model → foundation candidates (confidence-scored) |
| GET | `` | List foundation models (filters: status, source) |
| POST | `` | Register a foundation model (idempotent on identity) |
| POST | `/ensure` | Compatibility seam: resolve/register for a legacy base-model string |
| GET | `/{id}` | Get one |
| GET | `/{id}/status` | Status / locality |
| GET | `/{id}/runtimes` | Reverse lineage (honest; empty until Export epic) |
| POST | `/{id}/sync` | Reconcile recorded state with the local filesystem |
| POST | `/{id}/cache` | Record a local weights path + update status |
| DELETE | `/{id}` | Remove |

Every existing endpoint is unchanged. One line added to `main.py` (import +
`include_router`).

---

## 8. UI (additive; existing design system only)

- New nav item **Foundation** (Build group) + route `/foundation-models`.
- New `FoundationModelsPage`: model cards with **status indicators**, a **Register**
  dialog, a **Resolve** dialog (confidence bars, candidate confirmation), a
  **Discover** strip (installed runtime models → suggested foundations), and a
  **metadata drawer** (full metadata, identity, reverse-lineage, sync/remove).
- No page, layout, style, routing, or design-system change elsewhere. The page
  composes only existing primitives (`Card`, `Button`, `Badge`, `PageHeader`,
  `EmptyState`, `Skeleton`).

---

## 9. Tests

`tests/test_foundation_models.py` (10 tests): domain identity/coercion; repository
CRUD + identity dedup (in-memory SQLite, dependency-inverted); service idempotent
register; resolution ambiguous-vs-confident; the `ensure_foundation_for_base_model`
seam (HF-repo / resolved / honest-unverified paths); sync marking a missing cache
invalid; API register/list/get/status/resolve/ensure/delete.

**Regression:** full backend suite **472 passed** (462 prior + 10 new), 0 failures.
Frontend `tsc` clean, `vite build` clean, version guard OK.

---

## 10. Constitution Conformance Checklist

- ✅ **Bounded context** with a clear public API and hidden internals (§3.6).
- ✅ **Dependency inversion** — service depends on repository interface, not SQLAlchemy (§4).
- ✅ **Layering** — no upward dependencies; domain is pure (§4.3).
- ✅ **Runtime isolation** — Foundation reads Runtime; Runtime never reads Foundation (§11.2, §14).
- ✅ **No Runtime → Training / Training → Runtime coupling introduced** (§14).
- ✅ **Honest over simulated** — resolution is confidence-scored; unverified identities are labeled, never fabricated (§2.14).
- ✅ **Deterministic** resolution (§2.11).
- ✅ **Single source of truth** — Foundation identity has one owner; Runtime Model stays separate (§2.16).
- ✅ **Additive, non-breaking** — new table only, new endpoints only, new page only; every existing test passes (§migration principles, §16).
- ✅ **No hidden magic** — the Training seam is an explicit, named, tested method, not a buried side effect (§2.15).

---

## 11. What This Epic Deliberately Did NOT Do

Per the epic's explicit boundaries: no Training Providers, no Export Engine, no
Artifact Registry, no Experiments, no Plugin System, no Job System, and no changes to
Benchmark / Evaluation / Security. The Foundation Platform stands alone, ready for the
next epic (Foundation ↔ Training wiring + Artifact Registry) to build on it.

---

## 12. Follow-up — Automatic Discovery (Epic 4.5)

Epic 1 shipped the identity, the resolution engine, and a *manual* register/resolve/
discover surface. **Epic 4.5** (`V3_EPIC4_5_MODEL_DISCOVERY.md`) turns that into a
polished desktop experience without changing this context's architecture — it only
adds an automation layer on top:

- A new **`DiscoveryService`** (`foundation_models/discovery.py`) that, on startup and
  on demand, scans installed runtime models, resolves each through the **unchanged**
  `ModelResolutionService`, and auto-registers the confidently-resolved ones via the
  **unchanged, idempotent** `FoundationModelService.register`.
- A new `runtime_provider_status()` read on the existing read-only `runtime_adapter`
  (Runtime stays unaware — §11.2, §14).
- A new **`runtime_models`** table + `RuntimeModelRepository` tracking discovered
  runtime models' *availability + resolution state* — kept strictly separate from
  Foundation *identity* (a vanished runtime model is marked unavailable, never deleted).
- Additive endpoints (`POST /foundation-models/discover|sync`, `/api/runtime-models/*`),
  a `runtime_discovery` background Job, and Event Bus events.

The Epic-1 contracts here (domain, resolution, service register/idempotency, runtime
isolation) were reused verbatim — Epic 4.5 added no mapping logic and altered no
existing table or endpoint.
