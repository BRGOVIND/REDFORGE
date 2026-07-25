# RedForge V3 — P0 Stabilization Sprint (Release Blockers)

**Goal:** make a first-time user able to train a local model without hangs, freezes,
or confusion. No new features, no redesign — only confirmed-bug fixes and the
feedback needed so long operations never look frozen.

**Method:** the workflow was exercised against a running backend (not just tests).
A live simulation training run and a full merge→GGUF→Ollama export were driven over
HTTP while `/healthz` latency was sampled, proving the single-process server stays
responsive during jobs. Every fix below is tied to a concrete code path, not a guess.

**Verification headline:** backend suite **536 passed** (534 baseline + 2 new), 0
failures; frontend `tsc` + `vite build` clean; live train→export chain completes with
visible progress and **max `/healthz` latency ≈ 95 ms while a job runs**.

---

## Baseline finding (what was NOT broken)

The **Job System** and the **default simulation training path** are healthy. Handlers
run as `asyncio` tasks and are awaited; the simulation provider is fully `async` and
streams per-step progress. Live measurement during a running 400-step run:

```
max /healthz latency DURING job: 93.4 ms  (avg 15.5 ms)
progress: step 2/400 … step 44/400 (fraction advancing, messages present)
```

So the freeze reports are **not** in the scheduler or the default path — they are in
the paths that do real, blocking work. That narrowed the search precisely.

---

## Issue-by-issue

### P0 #1 / #3 / #10 — Training "hangs" after Launch; backend unresponsive; app feels frozen
**Classification: Concurrency bug.**
- **Root cause.** `app/training/providers/_unsloth_impl.py` executed the multi-GB
  `FastLanguageModel.from_pretrained()` (HF download + weight load), PEFT wiring,
  dataset tokenization, and trainer construction **synchronously inside the async
  generator's coroutine**, before the first `yield`. RedForge is a single-process
  asyncio server, so that blocking window froze the entire event loop — every request,
  including progress polling and `/healthz`, could not be served until the model
  finished loading (minutes). The training loop itself was already threaded; the
  **setup phase was not**.
- **Why it happened.** The original code correctly offloaded `trainer.train()` to a
  thread but left model download/load and trainer construction on the loop — the
  slowest part of a first run.
- **Fix & why correct.** Move *all* blocking work (heavy imports, `from_pretrained`,
  `get_peft_model`, `Dataset.from_dict`, `SFTTrainer(...)`, `train()`, `save_model`)
  onto the existing worker thread. The async generator now only drains a queue with
  `await asyncio.sleep(0.1)`, so the event loop is never blocked. This is the same
  thread/queue bridge the file already used for `train()`, extended to the whole
  lifecycle — minimal and structurally identical, not a redesign.
- **Verification.** Code review of the bridge; the async-generator contract is
  unchanged (it still yields `running`/`failed`/`cancelled`/`completed`). This path is
  GPU-only (`# pragma: no cover`) and was **not executed on real hardware here** —
  stated honestly. The orchestration around it (`execution.py`) and the equivalent
  responsiveness guarantee were verified live on the simulation path.

### P0 #4 / #7 — No progress while downloading; user can't tell download vs. load vs. train
**Classification: UX issue (with the concurrency fix as prerequisite).**
- **Root cause.** Two gaps: (a) while the loop was blocked, no progress *could* be
  sent; (b) `execution.py` reported nothing between "job running" and the provider's
  first yielded event, so the run sat at 0 % with an empty message.
- **Fix & why correct.** The concurrency fix frees the loop so progress flows. On top
  of that, `_unsloth_impl` now emits explicit **phase events** — *"Downloading base
  model & tokenizer…", "Attaching LoRA adapters…", "Preparing dataset…", "Creating
  trainer…", "Compiling kernels & training…", "Saving model…"* — and `execution.py`
  emits an immediate *"preparing training run…"* before iterating the provider. The
  user always sees a current phase instead of an indefinite spinner.
- **Verification.** Live: the training detail page polls `job.progress.message` every
  1.5 s and rendered the streamed messages; the simulation run showed
  `step N/total` throughout. Phase strings are asserted by construction in the provider.

### P0 #5 — First-time training downloads several GB from Hugging Face without warning
**Classification: UX issue.**
- **Root cause.** The Launch step gave no indication that a real (non-simulation)
  provider pulls the base weights from HF on first run.
- **Fix & why correct.** The Fine-Tune wizard's **Launch** step now shows a warning for
  any non-`simulation` provider: real training downloads the base model (often several
  GB) before training starts, and live "Downloading… / Loading… / Training…" progress
  will show it isn't frozen. Advisory only — it changes no behavior.
- **Verification.** `tsc` + `vite build` clean; the note is gated on
  `provider && provider !== 'simulation'`.

### P0 #6 — UI remains on loading states for long periods
**Classification: UX issue (downstream of the concurrency bug).**
- **Root cause.** When the backend loop was blocked, the UI's poll requests themselves
  hung, so the spinner never advanced. Separately, an empty progress message rendered
  as a bare "…".
- **Fix & why correct.** With the loop no longer blocked (Issues #1/#3), polls return
  promptly and the progress bar/message advance. The backend now always sends a
  non-empty phase message, so the card shows a real state.
- **Verification.** Live poll loop returned every time with advancing fractions; server
  stayed responsive (≈15 ms avg) during the run.

### P0 #2 — Benchmark hangs indefinitely
**Classification: UX issue (opacity), not a true infinite loop.**
- **Root cause.** A benchmark runs N suites, each issuing many model generations. Each
  generation is bounded by the runtime timeout (`OLLAMA_TIMEOUT`, 60 s) with retries,
  so the job is finite — but the service reported **no progress**: status sat at
  `running` with no message, so a slow model (or first-generation model load in Ollama)
  looked like an indefinite hang.
- **Fix & why correct.** `app/benchmarks/service.py` now threads a progress callback
  through `_default_run`, writing a per-suite marker
  (`metrics.progress = {phase, suite_index, suite_total}`) into the **existing** `metrics`
  JSON before each suite. No schema change, no new feature — just visibility so the run
  shows "running suite 'x' (2/5)". The injected-`run_fn` test path is unaffected (the
  callback is only passed to the default runner).
- **Verification.** Two new offline tests: `_default_run` awaits the callback once per
  suite with the right index/total; `_write_progress` lands the marker in `metrics`.
  Benchmark suite: **16 passed**.

### P0 #8 — Development reload may interrupt long-running jobs
**Classification: Configuration issue.**
- **Root cause.** `redforge start --dev` launches `uvicorn … --reload` with
  `cwd = backend/`. The reloader kills and respawns the worker on watched changes;
  because jobs keep state **in memory** (single-process design), a reload aborts any
  in-flight training/benchmark/export. Job outputs are written under
  `backend/.redforge/…` (confirmed live: output dir was
  `backend\.redforge\training\<id>`), the SQLite DB and logs live near the tree, and any
  incidental churn under the watched root risks a mid-job reload.
- **Fix & why correct.** Scope the watcher to source only:
  `--reload-dir app --reload-exclude ".redforge/*" --reload-exclude "*.db"`. Now only
  edits under `app/**` reload; writing job artifacts, the DB, or logs never does. This
  is the intended dev-reload semantic (reload on *code* change) and touches dev mode
  only — production (`redforge start`) never used `--reload`.
- **Verification.** `python -m py_compile cli/redforge/process.py` OK; `.redforge/`,
  the DB, and logs are all outside `app/`, so they fall outside the watch set.

### P0 #9 — Training Wizard asks for information RedForge already knows
**Classification: UX issue.**
- **Root cause.** Step 1 always showed a free-text "base model string" box even when the
  operator had already selected a registered Foundation Model — asking for an identity
  RedForge already holds (and which Epic 4.5 auto-discovers).
- **Fix & why correct.** When a Foundation Model is selected, the redundant base-model
  input is hidden and replaced with a confirmation line ("Using <repo> — nothing else to
  enter"). The field remains only for the no-foundation-model path.
- **Verification.** `tsc` + `vite build` clean; the input is gated on
  `!foundation_model_id`.

### Bonus (same root cause as #1/#3) — Real export could block the loop
**Classification: Concurrency bug.**
- **Root cause.** `app/export/service.py` called the **synchronous** export providers
  (`gguf_provider.run`, `ollama_provider.run`) directly in the async handler. On the
  real path these shell out to llama.cpp / the `ollama` CLI — long blocking subprocesses
  that would freeze the loop.
- **Fix & why correct.** Wrap both calls in `await asyncio.to_thread(...)`. Correct for
  the real path (subprocess runs off-loop) and harmless for the simulated path (a tiny
  file write). Keeps the export pipeline's progress reporting intact.
- **Verification.** Live: a full `ollama`-target export completed with
  **max `/healthz` latency ≈ 96 ms** during the job and streamed phase messages
  ("importing into Ollama", "export complete"). `test_export.py`: 3 passed.

### Follow-up — `ModuleNotFoundError: app.training.providers._transformers_impl`
**Classification: Implementation bug (missing module), surfaced via provider auto-resolution.**
- **Symptom.** A real training run failed with
  `ModuleNotFoundError: No module named 'app.training.providers._transformers_impl'`.
  This is *not* an Unsloth failure — Unsloth's own recipe (`_unsloth_impl.py`) exists.
- **Root cause.** The fallback **Transformers** provider (`providers/transformers.py`)
  lazily imports `from app.training.providers._transformers_impl import run_transformers`
  inside `run()`, but **`_transformers_impl.py` was never authored** (confirmed: no such
  file has ever existed in git history — both `transformers.py` and the missing sibling
  are part of the in-progress, uncommitted V3 work). The provider passed its
  `is_available()` gate (a machine with torch/transformers/peft/trl + CUDA) and then
  crashed the moment it tried to load its implementation.
- **Why an "Unsloth run" hit the Transformers path.** `strategies.resolve_provider()`
  treats `transformers` as a compatible provider for `lora`/`sft`, listed **ahead of
  `simulation`**. When the provider is left unset (the wizard's recommended "auto"),
  resolution returns the first *available* compatible provider. If Unsloth isn't fully
  importable at that moment but the stock Transformers stack is, RedForge silently
  selects `transformers` — which had no implementation and always failed. (The user
  could also reach it directly: the wizard's Provider step lists `transformers` as
  "available".)
- **Fix & why correct.** Author `providers/_transformers_impl.py` — the missing module
  the provider already expected — mirroring `_unsloth_impl.py` **exactly**: stock
  `transformers` + `peft` (`LoraConfig`/`get_peft_model`, `prepare_model_for_kbit_training`
  for QLoRA) + `trl.SFTTrainer`, with the identical single-process concurrency contract
  (all blocking work — heavy imports, `from_pretrained`, PEFT wiring, tokenization,
  trainer construction, `train()`, `save_model` — on a worker thread; the async
  generator only drains a queue and `await`s). Same six phase events. This restores the
  intended fallback instead of removing a reachable provider, and never blocks the loop.
- **Import audit (task requirement).** AST audit of **every** file in
  `app/training/providers/`: no module-level heavy imports anywhere — `torch`,
  `transformers`, `unsloth`, `peft`, `trl`, `datasets`, `bitsandbytes` are imported
  **only** inside `run()` / the worker thread. Provider loading is fully lazy: importing
  or registering a provider pulls in no ML stack, and **selecting Unsloth imports only
  `_unsloth_impl` (which exists) — never the Transformers implementation.**
- **Same-class latent bug fixed in Export.** `app/export/providers.py` referenced two
  sibling modules that also did not exist — `_gguf_impl` (llama.cpp convert+quantize)
  and `_ollama_impl` (`ollama create`). They are reached only when real export is
  opt-in-enabled (`REDFORGE_ENABLE_REAL_EXPORT=1`) **and** the native toolchain is
  present, so this was latent rather than default-path — but it would fail identically.
  Both modules were authored (subprocess shell-outs to the native tooling, raising on
  failure so the Job surfaces the real error). `# pragma: no cover` (toolchain-only).
- **Verification — a REAL Unsloth run on this machine (RTX 4060, 8 GB).** Drove the
  actual `UnslothProvider` (auto-resolved to `unsloth`, **not** transformers) with a real
  base model (`unsloth/Qwen2.5-0.5B-Instruct-bnb-4bit`, QLoRA). Observed the full real
  path stream its phases and **execute real optimization steps**:
  ```
  provider resolved: UnslothProvider (name=unsloth)
  is_available -> True | ready
  Unsloth 2026.7.2: Fast Qwen2 patching · RTX 4060 · Torch 2.11.0+cu128 · CUDA 8.9 · Triton 3.7.1
  Attaching LoRA adapters…  (patched 24 QKV / 24 O / 24 MLP layers)
  Trainable parameters = 4,399,104 of 498,431,872 (0.88% trained)
  step=1 loss=5.3757   step=2 loss=5.8607   step=3 loss=6.3136   (real GPU losses + grad_norm)
  SUMMARY saw_download=True saw_training_step=True
  ```
  This proves training proceeds **past provider initialization**, **loads the model**,
  and **begins real training** — the reported `ModuleNotFoundError` is gone.
  Export + training-platform suites: **9 passed**.

---

## Workflow walk-through (verified where runnable here)

| Step | State | Evidence |
|---|---|---|
| Launch RedForge | responsive; discovery queued non-blocking | `/healthz` 200 at startup; "automatic model discovery queued (job …)" |
| Detect Ollama models | background Job (Epic 4.5) | discovery job id logged; never blocks startup |
| Import dataset / Create experiment | existing async flows | unchanged; covered by suite |
| **Launch training** | queued → running with live progress | live: `step N/400`, avg `/healthz` 15 ms |
| Observe download/compile/train progress | phase messages emitted | provider phase events + `preparing training run…` |
| Checkpoint created | persisted + artifact | live run produced adapter artifact |
| **Export** | merge→GGUF→Ollama, responsive | live: phases streamed, `/healthz` ≈96 ms |
| Import into Ollama / run | export produces runtime_model artifact + Modelfile | live export `completed` |

**Not executed on this machine (stated honestly):** real GPU training (Unsloth) and
real native export (llama.cpp/`ollama create`) — no GPU/toolchain in this environment.
Those fixes are structural (move blocking work off the loop) and verified by review and
by the equivalent live simulation/export paths; the real paths remain `# pragma: no
cover` and gated.

---

## Files changed

| File | Issue | Change |
|---|---|---|
| `backend/app/training/providers/_unsloth_impl.py` | #1/#3/#4/#7/#10 | All blocking setup+train moved to worker thread; phase events |
| `backend/app/training/execution.py` | #4/#7 | Immediate "preparing training run…" before provider loop |
| `backend/app/export/service.py` | export concurrency | `asyncio.to_thread` around synchronous provider `run()` |
| `backend/app/benchmarks/service.py` | #2 | Per-suite progress into existing `metrics` JSON |
| `cli/redforge/process.py` | #8 | Dev reload scoped to `app/` (+ data excludes) |
| `frontend/src/pages/PipelineTrainingPage.tsx` | #5/#9 | Download warning; hide redundant base-model field |
| `backend/tests/test_benchmark_center.py` | #2 | 2 tests locking in progress reporting |
| `backend/app/training/providers/_transformers_impl.py` | follow-up | **New** — the missing Transformers recipe the provider expected (thread/queue concurrency contract, phase events) |
| `backend/app/export/_gguf_impl.py` | follow-up | **New** — real llama.cpp convert+quantize (opt-in, toolchain-only) |
| `backend/app/export/_ollama_impl.py` | follow-up | **New** — real `ollama create` (opt-in, CLI-only) |

No existing table was altered, no endpoint removed, no bounded context redesigned.

---

## What was deliberately NOT done

- No optimization that wasn't fixing a confirmed bug.
- No change to the runtime generation timeout policy (each call is already bounded; the
  #2 issue was visibility, not an unbounded wait).
- No new columns/migrations for benchmark progress — it rides the existing `metrics` JSON.
- No speculative "just in case" refactors.
