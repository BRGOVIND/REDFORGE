# RedForge V3 — Epic 4.5: Automatic Foundation Model Discovery (Implementation Notes)
## Runtime models become Foundation Models, automatically

**Status:** Shipped. Additive, non-breaking. Follows the V3 Constitution.
**Type:** UX-integration + automation epic — **not** a new architecture. It connects
the existing Foundation Model Platform (Epic 1) to the existing Runtime engine so
RedForge feels like a polished desktop app instead of exposing internal wiring.
**Builds on:** Epic 1 (Foundation Platform + ModelResolutionService), Epic 2 (Job
System + Event Bus).

Companion to `REDFORGE_V3_CONSTITUTION.md` (§2.14, §5.4, §11.2, §14) and
`V3_EPIC1_FOUNDATION_PLATFORM.md`.

---

## 1. The Problem It Solves

Before this epic, an operator had to **manually register** every Foundation Model —
typing Hugging Face repo names by hand. That is wrong UX: the operator usually already
has models installed (e.g. via `ollama pull`). RedForge should simply find them.

After this epic:

```
ollama already has:  llama3.1:8b, qwen2.5:7b, mistral, deepseek-r1
        ↓
launch RedForge  →  automatic startup discovery
        ↓
ModelResolutionService resolves each  →  FoundationModelService registers the confident ones
        ↓
Training Wizard immediately lists them — no HF repo knowledge required
```

Manual registration still exists — it's just no longer the primary path (it's the
advanced fallback for custom or unknown models).

---

## 2. What Was Reused (no redesign)

Everything load-bearing already existed; Epic 4.5 is **wiring**:

- **Runtime read** — the Epic-1 read-only `runtime_adapter` seam (`list_runtime_models`,
  and a new `runtime_provider_status`). Runtime stays entirely unaware of Foundation
  (Constitution §11.2, §14).
- **Resolution** — delegated **entirely** to the Epic-1 `ModelResolutionService`
  (`OllamaResolver` reading `/api/show`, the curated catalog, confidence scoring).
  Discovery contains **zero** name→repo logic; that would violate "resolution belongs
  only inside ModelResolutionService."
- **Registration** — delegated to `FoundationModelService.register`, which is idempotent
  on identity — so no duplicate Foundation Models are ever created.
- **Background execution** — the Epic-2 Job System (`runtime_discovery` job kind).
- **Integration** — the Epic-2 Event Bus.

The one genuinely new concept is a lightweight **discovered runtime model** record —
runtime *availability + resolution state*, kept separate from Foundation *identity*.

---

## 3. New Pieces (all additive)

| Piece | Location | Role |
|---|---|---|
| `DiscoveredRuntimeModel` + `RuntimeResolutionStatus` | `foundation_models/domain.py` | Pure domain: a discovered runtime model and where it sits on the resolution axis. |
| `RuntimeModelRecord` (table `runtime_models`) | `db/models.py` | Persistence for discovery state. **New table; nothing existing altered.** |
| `RuntimeModelRepository` + `SqlRuntimeModelRepository` | `foundation_models/repository.py` | Dependency-inverted persistence; `upsert` keyed on (provider, runtime_ref) → no duplicates. |
| `runtime_provider_status()` | `foundation_models/runtime_adapter.py` | Read-only provider identity + reachability. |
| `DiscoveryService` (+ `discovery_service` singleton) | `foundation_models/discovery.py` | The pipeline: discover → resolve → register → reconcile → emit. |
| `runtime_discovery` Job handler | `foundation_models/discovery.py` | Background/startup execution via the Job System. |
| `POST /foundation-models/discover`, `POST /foundation-models/sync` | `api/foundation_models.py` | Run the pipeline synchronously (immediate UI results). |
| `/api/runtime-models` router | `api/runtime_models.py` | List / unresolved / resolve discovered runtime models. |

---

## 4. Startup Flow

```
Application startup (lifespan)
  → init_db()  (create_all provisions the new runtime_models table)
  → _register_v3_job_handlers()  → register_discovery_handlers()   (runtime_discovery)
  → _recover_orphaned_jobs()
  → background task: _startup_model_discovery()
        → job_service.submit(type="runtime_discovery")   ← non-blocking
```

Discovery runs as a **background Job** — it never blocks readiness or the UI. If the
runtime is offline, discovery honestly finds nothing and the app starts normally.

---

## 5. Discovery Flow (`DiscoveryService.run_discovery`)

```
provider status (name + online?)
  ↓
list installed runtime models   (runtime_adapter, offline-honest → [])
  ↓   emit runtime.models_discovered
for each runtime ref:
    resolve via ModelResolutionService
        confident + unambiguous?  →  FoundationModelService.register(source=resolved_from_runtime)
                                      emit foundation.model_resolved
                                      emit foundation.model_registered (only on a NEW link)
                                      resolution = RESOLVED, link foundation_model_id
        otherwise                 →  resolution = NEEDS_RESOLUTION, keep candidates (never guessed)
    upsert runtime_models row     (keyed on provider+runtime_ref → idempotent, no dupes)
  ↓
availability reconciliation (only if online):
    any previously-available tracked model NOT in the current list  →  available = False
    (Foundation identities are NEVER deleted)
  ↓   emit runtime.sync_completed  (or runtime.sync_failed on a listing error)
return summary {discovered, resolved, needs_resolution, registered, unavailable, online}
```

`discover` and `sync` are the **same idempotent pipeline** — re-running it registers
newly-installed models and reconciles availability without creating duplicates.

---

## 6. Resolution Flow (unchanged engine, honest outcomes)

Resolution is **only** `ModelResolutionService`. A single unambiguous candidate with
`confidence ≥ 0.85` (and a `≥ 0.15` margin over the runner-up) **auto-resolves and
auto-registers**. Everything else is recorded as `needs_resolution` with its scored
candidates for the operator to confirm — never a fabricated mapping (§2.14).

Manual resolution (`POST /runtime-models/{id}/resolve`):
- with an explicit `hf_repo` → register that identity (the "I know what this is" path),
- without one → adopt the top candidate,

then link it and flip the runtime model to `resolved`.

---

## 7. Sync Behavior — availability vs. identity

The two axes are deliberately separate (Constitution §5.4):

- **Runtime availability** is *state*: `ollama rm qwen2.5:7b` → the tracked model is
  marked `available: False`. `ollama pull` it again → `available: True`.
- **Foundation identity** is *permanent*: a vanished runtime model **never** deletes its
  Foundation Model. A resolved-but-unavailable model still shows its identity; it just
  can't currently be served.

Critically, **offline ≠ removed**: if the runtime is unreachable, discovery does *not*
mark everything unavailable (it can't see them, which is not evidence of removal). The
`online` flag guards availability reconciliation.

---

## 8. Events (Event Bus)

Emitted with dotted, lowercase names consistent with the rest of the platform
(`job.*`, `artifact.*`, `training.*`). Spec name → emitted name:

| Spec (PascalCase) | Emitted | Payload |
|---|---|---|
| RuntimeModelsDiscovered | `runtime.models_discovered` | provider, count, refs |
| FoundationModelResolved | `foundation.model_resolved` | runtime_ref, foundation_model_id, hf_repo, confidence, provider |
| FoundationModelRegistered | `foundation.model_registered` | id, hf_repo, source, runtime_ref |
| RuntimeSyncCompleted | `runtime.sync_completed` | provider, discovered, resolved, needs_resolution, registered, unavailable |
| RuntimeSyncFailed | `runtime.sync_failed` | provider, error |

Telemetry is best-effort — an emit failure never breaks discovery, and a subscriber
failure never breaks the publisher (the Event Bus already swallows those).

---

## 9. Supported Providers

**Ollama** is implemented (via the existing `OllamaResolver`). The architecture already
generalizes to future providers — a new runtime family is a one-class `ModelResolver`
addition plus a provider-status read — but **only Ollama** is shipped here, per the epic
boundary. LM Studio / llama.cpp / vLLM / OpenAI-compatible runtimes are explicitly
deferred.

---

## 10. API (additive)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/foundation-models/discover` | Run discovery + auto-register confident models; returns a summary |
| POST | `/api/foundation-models/sync` | Reconcile with current runtime state (same idempotent pipeline) |
| GET | `/api/runtime-models` | List discovered runtime models (filter provider/resolution/available) |
| GET | `/api/runtime-models/unresolved` | Available models needing an operator decision |
| GET | `/api/runtime-models/{id}` | One discovered runtime model |
| POST | `/api/runtime-models/{id}/resolve` | Resolve → register (top candidate or explicit `hf_repo`) |

Every pre-existing endpoint is unchanged. The read-only `GET /foundation-models/discover`
(Epic-1 proposer) still exists; the new `POST` form is the execute-and-register action.

---

## 11. UI (additive; existing design system only)

- **Foundation Models page** — primary action reordered to **Discover local models**
  (primary), **Register manually** (secondary), **Resolve** (advanced). A new **Local
  runtime models** panel lists discovered models with runtime-availability + resolution
  badges, "Detected from", last-synced, and per-row **Resolve** / **Import…** actions,
  plus a **Sync** button.
- **First-run experience** — a welcome banner invites discovery when nothing is
  registered yet ("Discover my models"); once models exist, a lighter banner surfaces
  any that "require manual resolution."
- **Training Wizard (Experiment creation, Subject step)** — a small warning when
  unresolved local models exist ("⚠ N local models require manual resolution"), linking
  to the Foundation page. It never blocks training with already-resolved models.

`tsc --noEmit` clean, `vite build` clean.

---

## 12. Tests

`tests/test_model_discovery.py` (14 tests), fully offline (fake runtime list + fake
introspector + in-memory SQLite; no live Ollama, matches CI): discovery registers
confident + flags ambiguous; idempotent no-duplicates; sync marks vanished models
unavailable while keeping Foundation identity; offline does **not** mark unavailable;
manual resolve (top candidate + explicit repo); unknown → None; `list_unresolved`;
events emitted; `runtime.sync_failed` on a listing error; the `runtime_discovery`
background Job; and the full API surface.

**Regression:** full backend suite **534 passed** (520 pre-Epic-4.5 baseline + 14 new),
0 failures. No existing test modified.

---

## 13. Constitution Conformance Checklist

- ✅ **Resolution only in `ModelResolutionService`** — discovery contains no mapping logic.
- ✅ **Honest over simulated (§2.14)** — only confident, unambiguous matches auto-register;
  the rest are `needs_resolution` with real candidates; unknowns never fabricated.
- ✅ **Runtime isolation (§11.2, §14)** — Foundation reads Runtime through the read-only
  adapter; Runtime gains no awareness of Foundation.
- ✅ **Separate identities (§5.4)** — RuntimeModel (availability/state) and FoundationModel
  (identity) stay distinct; linked by reference; runtime removal never deletes identity.
- ✅ **No duplicates** — idempotent register (identity key) + idempotent upsert (provider+ref).
- ✅ **Additive, non-breaking** — one new table, additive endpoints, extended UI; every
  existing test passes.
- ✅ **Background, non-blocking** — discovery runs via the Job System at startup; UI never
  waits on it.
- ✅ **Event-driven integration** — no new direct cross-context dependency.
- ✅ **Local-first** — entirely local; offline-honest throughout.

---

## 14. Deferred (later)

- Additional runtime providers (LM Studio, llama.cpp, vLLM, OpenAI-compatible).
- A scheduled periodic re-sync (today: startup + manual refresh + provider reconnect via
  a manual sync); the Job kind is ready for a scheduler to drive.
- "Search Hugging Face" assist for `needs_resolution` models with no catalog candidate
  (today: manual `hf_repo` entry).
