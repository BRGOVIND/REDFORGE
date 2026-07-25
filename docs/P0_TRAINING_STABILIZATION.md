# RedForge — P0 Training Stabilization Sprint

> **UPDATE (follow-up): the reload fix was moved from the launcher into the application.**
> The first iteration set `UNSLOTH_COMPILE_LOCATION` and reload-excludes **only inside
> `cli/redforge/process.py::_start_dev`**. That fixes exactly one launcher
> (`redforge start --dev`). Any other entry point — a bare `uvicorn app.main:app
> --reload`, an IDE run config, `python -m uvicorn`, or a **stale pip-installed CLI** —
> never set the env var, so Unsloth defaulted its cache to the relative
> `unsloth_compiled_cache` (= CWD `backend/`) and the reloader restarted mid-training.
> The real fix now lives in **`app/main.py`** so it applies to every launcher. See
> "Follow-up: launcher-independent reload fix" at the end. The section below is kept for
> the original root-cause analysis.

**Goal:** make one complete Unsloth training run succeed end-to-end (launch → live
progress → checkpoint → completion) without the dev server reloading, without orphaned
jobs, and without schema errors. Implementation debugging only — no architecture change,
no new features, no touching Benchmark Center / Evaluation.

**Headline result (real GPU run, RTX 4060, legacy `/api/training` path, under the dev
reloader):**

```
SUMMARY  terminal=completed  reloads=0  security_http=200  logs=15  ckpts=1
checkpoint step=4  loss=3.766  path=outputs
Saved checkpoint (LoRA adapter) → training complete → status=completed
port free after shutdown (no orphaned worker)
```

---

## Root cause — per issue

### 1. WatchFiles reload kills training  *(Configuration + External-library interaction)*
- **Where uvicorn starts / how reload is configured.** The **only** `--reload` invocation
  in the repo is `cli/redforge/process.py::_start_dev` (`redforge start --dev`).
  Production `start()` never uses `--reload`.
- **Why `unsloth_compiled_cache` was watched.** uvicorn's `WatchFilesReload.__init__`
  (`uvicorn/supervisors/watchfilesreload.py`) drops any `reload_dir` that is a child of
  the CWD and then **unconditionally appends the CWD**. The backend runs with
  `cwd = backend/`, so the reloader always watches the whole of `backend/` — the old
  `--reload-dir app` narrowed nothing. uvicorn's default include is `*.py`. Unsloth
  compiles kernels and writes them as **`unsloth_compiled_cache/*.py` into the CWD**
  (`UNSLOTH_COMPILE_LOCATION` defaults to `unsloth_compiled_cache`, resolved relative to
  CWD). Those generated `.py` files matched `*.py`, so WatchFiles fired → "Reloading" →
  "Shutting down" → the worker (holding all in-memory job state) was killed →
  the run was reported `interrupted`.
- **Why previous attempts failed.** `--reload-dir app` is a no-op (CWD is always watched);
  the `.redforge/*` and `*.db` excludes were irrelevant because those files are `*.json`/
  `*.db` and never matched the `*.py` include in the first place. The real trigger — `.py`
  files under the watched CWD — was never excluded.

### 2. `checkpoint_security.runtime_id` — no such column  *(Schema drift / missing migration)*
- The ORM (`app/db/models.py::CheckpointSecurity`) declares `runtime_id` and `provider`
  (added in "Phase 2.5" for Runtime-Registry linkage). The live 248 MB `redforge.db`'s
  `checkpoint_security` table predates them.
- RedForge has **no Alembic**; startup schema management is `Base.metadata.create_all`
  (`app/db/database.py`). `create_all` creates *missing tables* but **never ALTERs an
  existing table to add a column**. So the table stayed at its old shape, and both the
  security-timeline `SELECT` (`continuous_security.timeline`) and the checkpoint-security
  `INSERT` (`schedule`) referenced a column SQLite didn't have → `OperationalError`.

### 3. Training logs not streamed  *(Implementation gap)*
- The legacy path already streams `progress_store` logs over `/progress` + `/stream`, and
  the store turns any event **message** into a log line. But (a) there was a silent window
  at launch while `torch`/`unsloth` imported (tens of seconds) before the first phase
  message, and (b) real per-step events from Unsloth's HF-Trainer callback carry metrics
  but **no message**, so step/loss/epoch never became terminal lines — only chart points.

### 4. The run itself never completed  *(External-library / Implementation bug, found by the E2E)*
- Two defects in the Unsloth recipe (`_unsloth_impl.py`), only reachable on real GPU:
  - **`trainer.train()` crashed at its automatic end-of-epoch save.** Transformers 5.5.0
    performs an internal `save_model(_internal_call=True)` → `torch.save(self.args)`, and
    Unsloth's dynamic patching makes TRL's `SFTConfig` unpicklable
    (`Can't pickle SFTConfig: it's not the same object as trl...SFTConfig`). Training
    finished all steps (loss fell 5.38→3.77) and then died at the save.
  - **The Unsloth provider never emitted checkpoint events**, so no `Checkpoint` row/
    artifact was ever persisted (unlike the simulation provider).

---

## Files changed

| File | Issue | Change |
|---|---|---|
| `cli/redforge/process.py` | #1 | `start()` sets `UNSLOTH_COMPILE_LOCATION` to the writable runtime home (outside CWD) so Unsloth never writes `.py` into the watched tree. `_start_dev()` pre-creates each generated runtime dir (`unsloth_compiled_cache`, `outputs`, `checkpoints`, `runs`, `artifacts`, `logs`, `.redforge`) and passes each **absolute** path as `--reload-exclude` (uvicorn's `exclude_dirs` fast-path), and uses the absolute `app/` reload dir. No wildcard excludes (a trailing `*` argv element is glob-expanded on Windows and breaks uvicorn's CLI). Reload stays enabled for source edits. |
| `backend/app/db/database.py` | #2 | New `_reconcile_columns()` run inside `init_db()` after `create_all`: walks every existing mapped table and `ALTER TABLE ADD COLUMN`s any column the ORM declares but the DB lacks. **Strictly additive** — never drops/renames/retypes/rewrites; columns added nullable. Logs what it adds. |
| `backend/app/training/store.py` | #3 | Step events without a message now also append a real terminal line: `step N/T · epoch E · loss L · lr …`. |
| `backend/app/training/runner.py` | #3 | Emits an immediate `starting training run…` log line at launch so the terminal shows activity before the provider's first event. |
| `backend/app/training/providers/_unsloth_impl.py` | #3/#4 | Early `Loading training engine…` phase before the slow imports; `save_strategy="no", report_to="none"` (stops the crashing internal save); saves the LoRA adapter via `model.save_pretrained` (+ tokenizer); emits a **checkpoint event** with final metrics; carries final loss/steps into the terminal `completed` event; wider traceback capture. |
| `backend/app/training/providers/_transformers_impl.py` | #4 | Same adapter-save + `save_strategy="no"` + checkpoint-event + final-metrics changes, kept consistent with the Unsloth recipe. |

No table altered destructively, no endpoint removed, no context redesigned.

---

## Validation (real run, driven over HTTP under `uvicorn --reload`)

The workflow was exercised against a live backend started with the exact new
`_start_dev` reloader configuration, driving the real legacy `/api/training` pipeline:
Wizard → `POST /api/training/launch` → `training_service.create` (TrainingRun) →
`asyncio` background runner → `manager.get_provider("unsloth")` → real Unsloth
LoRA/QLoRA → checkpoint → completion.

- **Task 1 — reload eliminated.** Across a full real run (model load + compile + 4 steps
  + save): `WatchFiles detected changes = 0`, `Reloading = 0`, `Shutting down = 0`. The
  server stayed responsive throughout (uninterrupted `200 OK` on `/progress`). Zero `.py`
  files land under `backend/unsloth_compiled_cache`; the cache is written to the relocated
  `UNSLOTH_COMPILE_LOCATION` outside the watched tree.
- **Task 2 — schema.** Startup migration added `checkpoint_security.runtime_id` and
  `checkpoint_security.provider` additively (row count unchanged). `GET /api/training/{id}/
  security` returns **HTTP 200** (mid-run and final), no `OperationalError`.
- **Task 3 — logs.** Live terminal output from launch: `starting training run…`,
  `Loading training engine…`, `Downloading base model…`, `Attaching LoRA adapters…`,
  `Preparing dataset…`, `Creating trainer…`, `Compiling kernels & training…`,
  `step 1/4 · epoch 0.25 · loss 5.3757 · lr 0.00e+00` … `step 4/4 · … loss 3.7663`,
  `Saving LoRA adapter…`, `Saved checkpoint (LoRA adapter)`, `training complete`.
- **Task 4 — lifecycle.** Every stage executed: launch `202` → TrainingRun row → background
  runner → Unsloth provider → 4 real GPU training steps (real losses) → adapter saved to
  the run output dir → `Checkpoint` row persisted → run finalized.
- **Task 5 — end-to-end.**
  - ✅ backend never reloaded (`reloads=0`)
  - ✅ no orphaned jobs (server never restarted; port freed cleanly on shutdown)
  - ✅ no schema errors (`/security` 200)
  - ✅ live logs appear (15 lines, phases + per-step loss)
  - ✅ checkpoint created (`GET /{id}/checkpoints` → 1: `step=4 loss=3.766 path=outputs`)
  - ✅ artifact saved (LoRA adapter written via `save_pretrained`; `Checkpoint` row persisted)
  - ✅ TrainingRun marked **completed**

**Regression:** targeted suites green — training/continuous-security/phase25/export/jobs/
training-platform (43), errors/release-hardening (10), training-lab/phase25 (19). App
imports clean.

**Environment note:** the real training path is GPU-only and remains `# pragma: no cover`
in CI; it was validated here on a real RTX 4060 with the full ML stack. The `save_strategy`
crash is specific to Unsloth + Transformers 5.5.0 + TRL and would recur on any similar
stack, which is why it is fixed at the recipe level rather than worked around.

---

## Follow-up: launcher-independent reload fix

### Why the first fix failed
The mitigation lived only in `cli/redforge/process.py::_start_dev`: it set
`UNSLOTH_COMPILE_LOCATION` and passed absolute `--reload-exclude` dirs. That is correct
**only when RedForge is launched via `redforge start --dev`.** The earlier validation
also passed a driver that *replicated* `_start_dev` (it set the env var and the excludes
itself), so it proved the launcher config — not the app. A user launching any other way
(bare `uvicorn app.main:app --reload`, IDE, `python -m uvicorn`, or a pip-installed CLI
whose copy of `process.py` predates the edit) never got the env var, so:

- `unsloth_zoo/compiler.py` reads `UNSLOTH_COMPILE_LOCATION` **once at import**; unset →
  default **relative** `"unsloth_compiled_cache"` → resolved against CWD (`backend/`).
- Unsloth then wrote `unsloth_compiled_cache/*.py` (incl. `moe_utils.py`) into `backend/`.
- The reloader always watches CWD with a `*.py` include → **reload → restart → orphaned
  job**. The relative path in the user's log (`unsloth_compiled_cache\moe_utils.py`) is
  the fingerprint of "env var was never set".

### The fix (root cause, in the application)
`backend/app/main.py` now relocates the cache at **module import**, before anything
imports unsloth:

```python
def _relocate_unsloth_cache() -> str:
    default = str(Path.home() / ".cache" / "redforge" / "unsloth_compiled_cache")
    loc = os.environ.setdefault("UNSLOTH_COMPILE_LOCATION", default)  # operator override wins
    Path(loc).mkdir(parents=True, exist_ok=True)
    return loc
_UNSLOTH_CACHE_DIR = _relocate_unsloth_cache()
```

Because **every** launcher imports `app.main:app`, the cache is now always outside any
source tree (`~/.cache/redforge/unsloth_compiled_cache`), so the reloader never sees a
generated `.py`. A defensive `setdefault` is also done at the single unsloth-import
choke point in `_unsloth_impl._work`. `process.py` no longer sets the env var
(app.main is the single source of truth) but keeps the absolute-dir excludes as
defense-in-depth. Reload for real source edits is unchanged.

### Startup instrumentation (Step 6)
`app/main.py::_log_reload_diagnostics()` logs at startup:
```
── startup diagnostics ─────────────────────────────
  cwd                       : ...\backend
  launcher argv             : ...uvicorn app.main:app ... --reload
  under uvicorn --reload    : True
  UNSLOTH_COMPILE_LOCATION  : C:\Users\<user>\.cache\redforge\unsloth_compiled_cache
  unsloth actual cache dir  : C:\Users\<user>\.cache\redforge\unsloth_compiled_cache
  unsloth_cache_inside_cwd  : False  (MUST be False under --reload)
```

### Validation — the user's worst case
Ran a **real** Unsloth QLoRA run driven over HTTP against a **bare
`python -m uvicorn app.main:app --reload`** (CWD=`backend/`, **no** `UNSLOTH_COMPILE_LOCATION`
in the environment, **no** `--reload-exclude`, **no** `--reload-dir`):

```
launcher: -m uvicorn app.main:app --host 127.0.0.1 --port 8792 --reload
UNSLOTH_COMPILE_LOCATION in env at launch: None      ← the user's condition
Will watch for changes in these directories: ['...\backend']   ← reloader watches CWD
unsloth_cache_inside_cwd  : False
...
step 1/4 · loss 6.62 ... step 4/4 · loss 4.04
Saving LoRA adapter… → Saved checkpoint → training complete
RELOAD COUNTERS (whole run): WatchFiles_changes=0  Reloading=0  ShuttingDown=0  StartedServerProcess=1
checkpoint step=4 loss=4.043 path=outputs
final run status=completed  metrics={final_loss: 4.043, steps: 4, epochs: 1.0}
.py under backend/unsloth_compiled_cache (should be 0): 0
moe_utils.py now at: C:\Users\<user>\.cache\redforge\unsloth_compiled_cache\moe_utils.py
```

`StartedServerProcess=1` = a single start (no restart). The exact file from the report
(`moe_utils.py`) is now written to the home cache, and **zero** `.py` land in `backend/`.

### Files changed (follow-up)
| File | Why |
|---|---|
| `backend/app/main.py` | `_relocate_unsloth_cache()` at import (launcher-independent cache relocation) + `_log_reload_diagnostics()` startup instrumentation. |
| `backend/app/training/providers/_unsloth_impl.py` | Defensive `setdefault` of the cache location right before the unsloth import; logs the cache dir. |
| `cli/redforge/process.py` | Removed the launcher-local env-set (app.main owns it now); kept absolute-dir reload-excludes as defense-in-depth. |

### Remaining issues discovered during validation
- None affecting the training pipeline. Two **test-harness** (not product) issues were
  found and fixed in the driver only: (a) `proc.terminate()` orphaned uvicorn's reload
  *worker* child — the product's `stop()` already uses `taskkill /T`, so this was a
  driver bug; (b) the Windows console (cp1252) couldn't print a `→` in a log line — the
  provider message now uses ASCII `->`.
- The startup `system health` check still warns `Backend API not running on :8000` when
  the server runs on a non-default port — cosmetic, pre-existing, unrelated to training.
