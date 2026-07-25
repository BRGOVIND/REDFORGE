# RedForge V3 — Epic 4: Experiment Platform (Implementation Notes)
## The Experiment as the operator's primary unit of work

**Status:** Shipped. Additive, non-breaking. Follows the V3 Constitution.
**Builds on:** Epic 1 (Foundation Platform), Epic 2 (Artifact Registry + Job System +
Event Bus), Epic 3 (Dataset / Training / Export).
**Scope:** A new bounded context, `app/experiments/`, that makes the **Experiment** the
top-level object an operator works with. An Experiment *references and contextualizes* a
line of inquiry — its subject, configuration, jobs, artifacts, timeline, metrics, notes,
and tags — without ever *owning* or *producing* those entities. The engines "publish
into" an experiment purely through the Epic-2 Event Bus.

This is an implementation companion to `REDFORGE_V3_CONSTITUTION.md` (§3.3, §5.3, §7,
§8.6, §14) and the Epic 1/2/3 docs.

---

## 1. What This Epic Delivers

The operator now has a **workspace unit** above the individual run. A single experiment:

- Holds a **configuration** (foundation model ref, dataset ref, strategy, provider,
  hyperparameters) — the recipe, by reference.
- Captures a **reproducibility snapshot** at creation (and on demand): foundation model
  identity, dataset version + content hash, strategy/provider, hyperparameters, resource
  estimate, GPU info, RedForge version, and platform metadata.
- Builds an **event-driven timeline** automatically: training started/completed,
  checkpoints, job lifecycle, artifacts published — all appearing without the experiment
  code ever importing the Job System or the engines.
- Aggregates, **by reference**, every artifact and job produced under it.
- Records **metrics** (e.g. `final_loss`, `training_duration_seconds`) harvested from
  events.
- Supports **Markdown notes** and **user tags**.
- Can be **cloned** into a fresh line of inquiry (config + subject refs + tags + optional
  notes; artifacts are referenced from the parent, never duplicated).
- Can be **compared side-by-side** with other experiments.

Everything is local-first and runs offline. Nothing in Epics 1–3 was redesigned.

---

## 2. Strangler-Fig Strategy (extend, don't replace)

The core constraint (§14): an Experiment **MUST NOT** directly import Jobs, Training,
Export, Benchmark, or Evaluation. It learns about their work by **observing named events**
on the Epic-2 Event Bus. This keeps the dependency arrows pointing *into* the Experiment
context and never out of it.

The association is carried end-to-end as an `experiment_id` string that rides in
**existing** JSON columns — **no existing table was altered**:

- **Jobs** — `experiment_id` is added to the `Job` domain object and persisted inside the
  existing `job_metadata` JSON column (`app/jobs/`). `JobService.submit()` accepts it;
  every job lifecycle event (`job.started/completed/failed/cancelled`) now carries
  `experiment_id` in its payload.
- **Artifacts** — the `ArtifactRecord.experiment_id` column reserved in Epic 2 is now
  populated. `JobContext.publish_artifact` auto-injects the running job's `experiment_id`,
  so artifacts produced under an experiment are tagged automatically. `artifact.published`
  events include it, and `ArtifactRepository.search(experiment_id=…)` filters by it.
- **Training** — the V3 training run stores `experiment_id` in its existing `metrics`
  JSON; `training.started/checkpoint_saved/completed` events carry it. Critically, the
  final-metrics overwrite at completion **preserves** the association.
- **Export** — `ExportService.submit()` threads `experiment_id` into the job it submits.

New API prefix `/api/experiments` — no collision with any existing route.

---

## 3. Bounded Context (`app/experiments/`)

Strict layering, dependency inversion, pure domain (§4, §5.3):

```
domain.py        pure dataclasses — no SQLAlchemy, no FastAPI
repository.py    ABCs + SQL implementations (session_factory injectable)
service.py       application service — depends on repo interfaces only
subscriber.py    Event Bus handlers — read event payloads only, no engine imports
__init__.py      exports + module singleton `experiment_service`
```

### Domain model (`domain.py`)

- `ExperimentStatus` — `draft | active | concluded | archived`.
- `ExperimentConfiguration` — the recipe: `foundation_model_id`, `base_model`,
  `dataset_id`, `dataset_version`, `strategy`, `provider`, `hyperparameters`, `adapter`.
- `ExperimentSnapshot` — reproducibility capture: `foundation_model`, `dataset_version`,
  `dataset_content_hash`, `strategy`, `provider`, `hyperparameters`, `resource_estimate`,
  `gpu`, `redforge_version`, `platform`, `captured_at`.
- `ExperimentTimelineEvent` — `kind`, `title`, `payload`, `source` (`system|user`), `at`.
- `ExperimentNote` — Markdown `body` + `created_at`.
- `ExperimentJobReference` — `job_id`, `job_type`, `status`, `updated_at`.
- `Experiment` — the aggregate root: identity, status, description, configuration,
  snapshot, tags, metrics, `project_id`, `parent_experiment_id` (set for clones),
  timestamps, `concluded_at`.

The domain **references, never produces**. There is no `runs`/`artifacts` collection on
the aggregate — those live in their own contexts and are looked up by reference.

### Repository (`repository.py`)

Four ABCs (`ExperimentRepository`, `TimelineRepository`, `NoteRepository`,
`JobRefRepository`) with SQL implementations over four new tables. `_SessionMixin` makes
the session factory injectable (tests use in-memory SQLite). `SqlJobRefRepository.upsert`
is a select-or-insert so repeated job events update status idempotently. Deleting an
experiment cascades to its timeline / notes / job-refs.

### Service (`service.py`)

`ExperimentService(experiment_repo, timeline_repo, note_repo, jobref_repo, artifact_query)`.
Lifecycle: `create` (captures a best-effort snapshot + seeds the timeline), `snapshot`
(re-capture), `get`, `list`, `update` (name/description/tags/status; sets `concluded_at`
on conclude), `delete`. Reads: `timeline`, `artifacts` (via
`artifact_query.search(experiment_id=…)`), `jobs`, `notes`. Notes/tags:
`add_note`/`delete_note`; tags via `update`. Event-facing helpers used by the subscriber:
`record_timeline`, `upsert_job_ref`, `record_metric`. Plus `clone` and `compare`.

`_build_snapshot` is **best-effort** — it reuses `foundation_model_service`,
`dataset_platform`, `app.resources.detect_resources`, `app.version`, and the training
`estimation` module read-only, each wrapped so a lookup failure never blocks experiment
creation (§2.13/§2.14 graceful degradation).

### Subscriber (`subscriber.py`)

`register_experiment_subscribers(service, bus)` binds handlers to:
`job.started`, `job.completed`, `job.failed`, `job.cancelled`, `training.completed`,
`training.checkpoint_saved`, `artifact.published`. Each handler reads **only the event
payload**; if there's no `experiment_id`, it returns immediately. It never imports Jobs or
any engine. `job.completed` records the produced `artifacts`; `training.completed` harvests
`final_loss` and `training_duration_seconds` into experiment metrics. Registered at startup
alongside the Epic-3 job handlers in `main.py`.

---

## 4. Timeline Model

The timeline is an append-only log per experiment, populated from two sources:

1. **User/system actions** in the service (`experiment.created`, `experiment.cloned`,
   `snapshot.captured`, `note`).
2. **Platform events** via the subscriber (`job.started/completed/failed/cancelled`,
   `checkpoint.created`, `artifact.published`).

Because it is fed by the Event Bus, adding a new event-producing context later requires
**no change** to the Experiment code — only a new subscription (or reuse of the existing
job/artifact events, which already carry `experiment_id`). This is the "engines publish
into the Experiment" mechanism (§7, §8.6) realized without coupling.

---

## 5. Snapshot Model (reproducibility)

A snapshot answers "what exactly would I need to reproduce this?" at a point in time. It is
captured on `create` and re-captured on demand via `POST /{id}/snapshot`. It deliberately
stores **resolved identities and hashes** (foundation model identity, dataset content hash
+ version, RedForge version, platform, GPU, resource estimate) rather than live references,
so it remains meaningful even if the underlying dataset later changes.

---

## 6. Clone & Compare Workflows

- **Clone** (`POST /{id}/clone`) starts a *new line of inquiry* from an existing one. It
  copies the configuration, subject references, and tags; optionally copies notes; sets
  `parent_experiment_id`; captures a fresh snapshot; and seeds an `experiment.cloned`
  timeline entry. **Artifacts are never duplicated** — a clone begins with none of its own
  and references the parent's lineage.
- **Compare** (`GET /compare?ids=a,b,c`) returns a per-experiment column: status, strategy,
  provider, base model, hyperparameters, metrics, artifact counts by type, total
  artifacts/jobs, training duration, final loss, and GPU. Missing ids are skipped rather
  than erroring.

---

## 7. Database (additive only)

Four new tables in `app/db/models.py`, all following existing patterns (String(36) uuid
PKs, JSON columns, `_utcnow` defaults, FK to `experiments.id`):

- `experiments` — the aggregate (configuration/snapshot/tags/metrics as JSON).
- `experiment_timeline` — timeline events.
- `experiment_notes` — Markdown notes.
- `experiment_job_refs` — job references (idempotent upsert on `experiment_id`+`job_id`).

**No existing table was renamed, dropped, or altered.** The cross-context associations
reuse existing JSON columns (`job_metadata`, training `metrics`) and the reserved
`artifact.experiment_id` column.

---

## 8. API (additive; `/api/experiments`)

Literal routes precede `/{id}` so `/compare` is never shadowed.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/experiments` | list (filter by `project_id`, `status`) |
| POST | `/api/experiments` | create |
| GET | `/api/experiments/compare?ids=…` | side-by-side comparison |
| GET | `/api/experiments/{id}` | fetch one |
| PATCH | `/api/experiments/{id}` | update name/description/tags/status |
| DELETE | `/api/experiments/{id}` | delete (cascades children) |
| POST | `/api/experiments/{id}/clone` | clone |
| POST | `/api/experiments/{id}/snapshot` | re-capture snapshot |
| GET | `/api/experiments/{id}/timeline` | timeline events |
| GET | `/api/experiments/{id}/artifacts` | referenced artifacts |
| GET | `/api/experiments/{id}/jobs` | job references |
| GET | `/api/experiments/{id}/notes` | notes |
| POST | `/api/experiments/{id}/notes` | add a note |

Router wired into `main.py`; subscriber registered at startup.

---

## 9. UI (additive; existing design system only)

- **Nav** — a new **Experiments** item in the *Workspace* group (the primary unit of work),
  plus Command-Palette entries.
- **Experiments page** (`ExperimentsPage.tsx`) — card grid, status filter, a **3-step
  creation wizard** (Identity → Subject → Plan), a **Compare** mode (multi-select →
  comparison table).
- **Experiment dashboard** (`ExperimentDetailPage.tsx`) — header with status, tags editor,
  and actions (clone, re-snapshot, conclude, archive, delete); metrics tiles; a
  configuration panel; a reproducibility-snapshot panel; and tabbed **Timeline / Artifacts
  / Jobs / Notes** panels that poll lightly so a running experiment fills in live.
- **Clone dialog** and **Compare dialog** reuse the shared `ui` primitives; no new design
  system was introduced.

Typed API surface in `api/endpoints.ts` (`xp*`), types in `api/types.ts`, hooks in
`hooks/queries.ts`. `tsc --noEmit` and `vite build` both clean.

---

## 10. Tests

`tests/test_experiments.py` (17 tests) covers: domain round-trip + status coercion;
service create/read/update/notes/delete-cascade; snapshot re-capture; clone (config/tags/
optional notes, artifacts **not** duplicated, parent referenced); comparison; the event
subscriber (job lifecycle → timeline + job-refs, training metrics harvest, artifact
timeline, no-`experiment_id` events ignored, idempotent job-ref upsert); and the full API
surface. All offline against in-memory SQLite with a fake artifact-query.

**Regression:** full backend suite **520 passed** (503 pre-Epic-4 baseline + 17 new); no
existing test modified its expectations. Frontend `tsc` + `vite build` green.

---

## 11. Constitution Conformance Checklist

- **§3.3 / §5.3 / §7 — Experiment is the primary unit of work.** ✅ New top-level context;
  references, never owns.
- **§14 — no direct cross-context dependencies.** ✅ Experiments import no Jobs/engine
  code; association flows through Event Bus payloads only. Runtime remains unaware.
- **§4/§5 — layering + dependency inversion + pure domain.** ✅ domain → repository (ABCs)
  → service → API; no SQLAlchemy/FastAPI in domain or service.
- **§8.6 — event-driven integration.** ✅ Timeline/metrics/job-refs populated by
  subscriptions to existing named events.
- **Additive migrations only.** ✅ Four new tables; zero alterations to existing tables;
  associations ride in existing JSON columns.
- **§2.13/§2.14 — graceful degradation.** ✅ Snapshot building and subscriber handlers are
  best-effort; a failure never blocks creation or the publisher.
- **Local-first, no cloud.** ✅ Entirely in-process/SQLite.
- **Existing app/APIs/UI/tests unchanged.** ✅ 503 prior tests still green.

---

## 12. Deferred Work (later epics)

- **Experiment reports** — `ExperimentReportReference` and export-to-Markdown/PDF are
  scoped but not yet built; the timeline + comparison provide the data.
- **Benchmark / Evaluation / Security publish-in** — these contexts don't yet stamp
  `experiment_id` on their jobs; once they do (same one-line plumbing as Training/Export),
  their events flow into the timeline with no change to the Experiment context.
- **Diff view** in compare (per-hyperparameter deltas) — currently a side-by-side table.
- **Experiment-scoped resource/cost rollups** beyond the two harvested training metrics.
