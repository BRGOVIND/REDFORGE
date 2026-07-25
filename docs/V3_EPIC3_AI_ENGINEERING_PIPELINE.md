# RedForge V3 — Epic 3: AI Engineering Pipeline (Implementation Notes)
## Training Platform + Dataset Platform + Export Engine

**Status:** Shipped. Additive, non-breaking. Follows the V3 Constitution.
**Builds on:** Epic 1 (Foundation Platform) + Epic 2 (Artifact Registry + Job System).
**Scope:** The three bounded contexts that complete the local AI engineering pipeline —
Dataset Platform, Training Platform, Export Engine — all executing through the Epic-2
Job System and publishing Epic-2 Artifacts with full lineage.

This is an implementation companion to `REDFORGE_V3_CONSTITUTION.md` (§10, §11, §12,
§13), `TRAINING_FOUNDATION_ARCHITECTURE.md`, and the Epic 1/2 docs.

---

## 1. What This Epic Delivers

A user can now take a Foundation Model through the **complete lifecycle, entirely
locally**: register/download a foundation model (Epic 1) → import/prepare a dataset →
configure a training run → train via a provider → produce checkpoints → produce an
adapter → merge → export GGUF → import into Ollama → view every artifact and its
lineage → track everything as Jobs.

The **Mock/Simulation path runs the entire pipeline end-to-end without a GPU**,
producing real local files + artifacts + lineage, honestly flagged `simulated`. Real
providers (Unsloth, Transformers) and real export (llama.cpp/Ollama) are present and
GPU-/toolchain-gated, degrading honestly when unavailable (§2.14).

---

## 2. Strangler-Fig Strategy (extend, don't replace)

The existing V2 `datasets_lab`, `training` (manager/runner/service), and their APIs +
488 tests are **untouched and still working**. The V3 contexts are additive:

- **Dataset Platform** (`app/datasets/`) reuses `datasets_lab`'s pure helpers
  (`parsers`, `analysis`, `splitting`) — no parser/analyzer duplication (§2.16) — and
  adds the V3 domain, repository pattern, artifact publication, and Job processing.
- **Training Platform** (new modules in `app/training/`, no collisions) reuses the
  existing `TrainingProvider` ABC + `UnslothProvider`/`SimulationProvider` via
  `manager.get_provider()`, and registers a new `TransformersProvider`. Strategy
  separation lives in the V3 config→`TrainingConfig` translation, so the existing
  providers are never modified.
- **Export Engine** (`app/export/`) is fresh — merge → GGUF → Ollama providers.

New API prefixes (`/api/dataset-platform`, `/api/training-platform`, `/api/export`)
avoid collision with the legacy `/api/datasets`, `/api/training`.

---

## 3. Dataset Platform (`app/datasets/`)

| Module | Responsibility |
|---|---|
| `domain.py` | `Dataset`, `DatasetVersion`, `DatasetFormat`/`DatasetStatus`, `DatasetSchema`, `DatasetStatistics`, `DatasetValidationResult`, `DatasetPreview`. Pure. |
| `repository.py` | `DatasetRepository`, `DatasetVersionRepository` (ABCs) + SQL impls. |
| `service.py` | `DatasetPlatformService` — import/register/preview/validate/split; composes `datasets_lab` helpers; publishes a `dataset` artifact per version. |
| `handlers.py` | `dataset_processing` Job handler (validate/split as Jobs, §12). |

- **Every version is published to the Artifact Registry** (kind `dataset`, data-backed,
  referencing `v3_dataset_versions`), with version-to-version lineage edges.
- **Processing runs through the Job System** (`POST /{id}/process` → `dataset_processing`
  job → validate/split).
- Formats: JSON, JSONL, CSV, TXT, MD (via `datasets_lab` parsers). Content hashing +
  deterministic splitting reused.

---

## 4. Training Platform (`app/training/` V3 modules)

| Module | Responsibility |
|---|---|
| `domain.py` | `TrainingRun`, `TrainingConfiguration`, `HyperparameterSet`, `AdapterConfiguration`, `TrainingCheckpoint`, `TrainingEstimate`, `TrainingStatus`. Pure. |
| `strategies.py` | Strategy registry: LoRA/QLoRA/SFT (implemented) + DPO/ORPO/PPO/RLHF (architecture-ready, honestly flagged `implemented=False`). Strategy↔provider compatibility. |
| `providers/transformers.py` | New `TransformersProvider` (fallback, GPU-gated). Registered from the V3 layer — existing providers untouched. |
| `estimation.py` | Resource estimate (VRAM/disk/duration/checkpoint & adapter size), hardware-aware warnings. |
| `repository.py` | `TrainingRunRepository`, `CheckpointRepository` (ABCs) + SQL impls. |
| `execution.py` | The `training` Job handler — drives the provider, translates progress, persists checkpoints as **real files + Artifacts**, publishes run + adapter artifacts with lineage. Emits `training.*` events. |
| `platform_service.py` | `TrainingPlatformService` — create/estimate/launch/list/get/checkpoints/logs/cancel. |

### The three axes, separated (Constitution §10.2)
- **Strategy** (`strategies.py`) — *what algorithm*; each declares dataset shape +
  compatible providers. New alignment methods are new registered specs, no redesign.
- **Provider** (existing + Transformers) — *who executes*; `resolve_provider` filters by
  strategy compatibility then availability, with `simulation` the guaranteed floor.
- **Execution** (`execution.py`) — *how*; runs as a Job, provider- and strategy-agnostic.

### Providers
- **UnslothProvider** (existing, reused) — primary, real GPU LoRA/QLoRA/SFT.
- **TransformersProvider** (new) — fallback, GPU-gated SFT/LoRA.
- **Simulation/Mock** (existing `SimulationProvider`, reused) — dev-only, never offered as
  a production option (`dev_only: true` in the providers listing).

### Training execution & artifact publication (Constitution §10.5, §10.11)
Training **never executes from an API request** — `launch` submits a `training` Job.
The handler drives the provider and **automatically publishes**: a `training_run`
artifact (parents: consumed dataset + foundation model), a `checkpoint` artifact per
checkpoint (real local file + checksum, parent = run), and an `adapter` artifact
(parent = best checkpoint). Lineage: `foundation_model → training_run → checkpoint →
adapter`. Central per-kind concurrency (training = 1) fixes unbounded concurrent training.

---

## 5. Export Engine (`app/export/`)

| Module | Responsibility |
|---|---|
| `domain.py` | `ExportConfiguration`, `ExportResult`, `ExportTarget`. Pure. |
| `providers.py` | `ExportProvider` ABC + `GGUFExportProvider`, `OllamaExportProvider` (+ registry). LM Studio/llama.cpp/vLLM are architecture-ready future targets, honestly listed. |
| `service.py` | `perform_export` (the merge → GGUF → install pipeline) + `ExportService` (submit as a Job). |
| `handlers.py` | The `export` Job handler. |

### Export flow (Constitution §10.8)
`checkpoint/adapter → merge → merged_model → GGUF → gguf → (Ollama import) →
runtime_model`, each stage publishing an artifact with a `derived_from` edge to the
prior — so a runtime model traces all the way back to the checkpoint (verified in
tests). Export **uses the target runtime's native tooling** (`ollama create`) — it
never imports the Runtime Engine (§11.2). Real conversion/import is opt-in via
`REDFORGE_ENABLE_REAL_EXPORT=1` (requires both the toolchain and real merged weights);
default is honest simulated mode — real files + lineage, flagged `simulated`.

---

## 6. Database (additive only)

**Four new tables:** `v3_datasets`, `v3_dataset_versions`, `v3_training_runs`,
`v3_training_checkpoints` (provisioned by `create_all`). **No existing table altered.**
`v3_training_runs` is added to the startup orphan-recovery loop. The Export Engine
needs no new table — its outputs are Artifacts + Jobs.

---

## 7. Job Integration

The V3 handlers register at startup (`_register_v3_job_handlers` in `main.py`):
`dataset_processing`, `training`, `export` — joining Epic-2's `model_discovery`,
`model_sync`, `diagnostics`. Every long-running Epic-3 operation is a Job with uniform
progress, cancellation, recovery, retry, and per-kind concurrency (§8).

---

## 8. UI (additive; existing design system only)

- New **Pipeline** nav group: Datasets · Fine-Tune · Exports (routes `/pipeline/*`).
- `PipelineDatasetsPage` — import/list, preview + validation drawer, split (as a Job),
  artifact links.
- `PipelineTrainingPage` — runs dashboard + an **8-step Training Wizard** (Foundation
  Model → Dataset → Strategy → Provider → Hyperparameters → **Resource Estimate** →
  Review → Launch).
- `PipelineTrainingDetailPage` — live progress, checkpoints table, logs, artifact
  links, and a one-click **Export to Ollama**.
- `PipelineExportsPage` — export form (pick adapter/checkpoint → target → quantization),
  provider availability, live export history with runtime-model artifact links.
- No existing page, layout, style, or routing changed. Pages compose only existing
  primitives.

---

## 9. Tests

- `test_dataset_platform.py` (6): register/publish-artifact, import bytes, preview,
  validate, split→new-version-with-lineage, `dataset_processing` job, API.
- `test_training_platform.py` (6): strategies + provider resolution, create + estimate,
  refuse unimplemented strategy, **full training-as-a-Job end-to-end** (real checkpoint
  files → adapter → lineage), launch-submits-job, API.
- `test_export.py` (3): providers listed, **full merge→GGUF→Ollama pipeline with
  lineage back to the checkpoint** (simulated), API.

**Regression:** full backend suite **503 passed** (488 Epic-2 baseline + 15 new), 0
failures. Frontend `tsc` clean, `vite build` clean (4 new lazy chunks), version guard OK.

---

## 10. Constitution Conformance Checklist

- ✅ **Bounded contexts** — Dataset/Training/Export each with a public API + hidden internals (§3.5, §3.7, §3.9).
- ✅ **Repository pattern + dependency inversion** — services depend on interfaces, never SQLAlchemy (§4).
- ✅ **Pure domain models** — no framework leakage (§4).
- ✅ **Provider-based** — training + export providers in flat registries; new providers are one-file additions (§2.3, §9).
- ✅ **Strategy/provider/execution separation** — the founding training flaw's fix, realized (§10.2).
- ✅ **Jobs execute all training/export/processing** — never inline (§8, §10.5).
- ✅ **Artifact-oriented** — everything produced is published with lineage; nothing manually registered by the user (§2.4, §6, §10.11).
- ✅ **Runtime remains unaware of Training** — Training/Export never import the Runtime Engine; Export uses Ollama's native CLI (§11.2, §14).
- ✅ **Honest over simulated** — dev provider is dev-only; simulated export/training are labeled; unimplemented strategies flagged (§2.14).
- ✅ **Local-first** — datasets, models, artifacts, logs, jobs, exports all local; only `LocalStorageProvider` (§2.1).
- ✅ **Additive, non-breaking** — 4 new tables, additive endpoints/pages; every existing test passes (§16).

---

## 11. Deferred Work (later epics)

- **Real GPU training + export** — the Unsloth/Transformers recipes and llama.cpp/Ollama
  conversion are present and gated; they run when a GPU + toolchain are available
  (`REDFORGE_ENABLE_REAL_EXPORT=1`). No architecture change needed to enable.
- **DPO/ORPO/PPO/RLHF** — registered as architecture-ready strategies; implementing them
  is adding a strategy spec + provider support, no redesign.
- **Experiments** (Constitution §7) — the aggregation root that will own these runs;
  the `experiment_id` slot is reserved on artifacts. A later epic.
- **Migrating Benchmark/Evaluation/Security to consume V3 artifacts** and onto the Job
  System — deferred; they keep their existing behavior for now.
- **Retiring the legacy `datasets_lab` / `training` subsystems** once the V3 platforms
  fully supersede them — strangler-fig completion, a later step.
- **LM Studio / llama.cpp / vLLM export providers** — architecture-ready, listed as
  not-yet-implemented; each is a one-provider addition.
