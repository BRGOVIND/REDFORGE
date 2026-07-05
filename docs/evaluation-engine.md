# Evaluation Engine

RedForge V3 Sprint 2 turns evaluation from "pick some attacks and run them" into
a **configurable, data-driven engine**. A user chooses an *evaluation profile*;
the engine expands it into a deterministic *execution plan*, *estimates* how long
it will take and what it will cost, and checks whether the machine can *safely*
run it — all before the first LLM call.

This layer is backend-only and read-mostly: it produces plans and estimates that
the durable session engine (Sprint 1) executes and that the future UI will
visualize.

```
Profile (JSON)  ──▶  Plan Builder  ──▶  Execution Plan (deterministic)
                                             │
              ┌──────────────────────────────┼───────────────────────────┐
              ▼                               ▼                           ▼
     Runtime Estimator              Resource Monitor              Scheduler
   (time, calls, RAM, disk)     (RAM/CPU/GPU/disk + warnings)  (create session,
                                                                pause/resume/cancel,
                                                                retry targets)
```

---

## 1. Profile architecture

Profiles are **authored as JSON** and validated into Pydantic models, so no
evaluation behavior is hardcoded per profile — the engine reads configuration
and acts on it.

- **Schema:** `app/evaluation_profiles/profile.py` (`EvaluationProfile` plus
  `MutationConfig`, `CheckpointConfig`, `RetryConfig`). `extra="forbid"` means a
  typo in a profile file fails loudly at load time.
- **Built-ins:** `app/evaluation_profiles/data/*.json`.
- **Loader:** `profile_loader.py` reads the built-in directory, then any files in
  `REDFORGE_PROFILES_DIR` (env var) — a same-named file there overrides a
  built-in. Everything is validated on load.
- **Registry:** `profile_registry.py` caches loaded profiles; `reload()` re-reads
  from disk.

### The five profiles

| Profile      | Dataset          | Attacks/cat        | Evaluator | Mutation      | Passes | Notes                         |
|--------------|------------------|--------------------|-----------|---------------|--------|-------------------------------|
| Quick Scan   | attack_library   | 5                  | heuristic | off           | 1      | sanity check, < 5 min         |
| Standard     | attack_library   | 20 (capped by avail)| llm_judge | static ×2     | 1      | normal evaluation             |
| Thorough     | benchmark_sample | 40                 | llm_judge | adaptive ×3   | 2      | retries, report               |
| Comparative  | benchmark_sample | 30                 | llm_judge | off           | 1      | multi-model, leaderboard      |
| Exhaustive   | full_benchmark   | all                | llm_judge | adaptive ×5   | 1      | adaptive agent, report        |

### Key profile fields

- `dataset` — `attack_library` (28 curated attacks, 4 categories),
  `benchmark_sample` (a per-category cap of RedForge-Bench-V1), or
  `full_benchmark` (all 800 cases).
- `categories` — `["all"]` (resolves to the dataset's categories) or an explicit
  list.
- `attacks_per_category` / `benchmark_sample_size` — per-category caps.
- `evaluator` + `judge_model` — heuristic scoring vs. LLM-as-judge.
- `mutation` — `{enabled, count, mode}`; expands one base attack into
  `1 + count` prompts.
- `checkpoint` / `retry` / `timeout_seconds` / `passes` — execution policy.
- `multi_model`, `adaptive_agent`, `generate_leaderboard`, `generate_report`.

---

## 2. Execution plan

`app/scheduler/plan_builder.py` expands a profile + a model list into an
`ExecutionPlan` (`app/scheduler/execution_plan.py`).

**Deterministic ordering** (the property resume depends on):

1. Attack steps, **model-major**, then **canonical category order**:
   - attack_library: `PROMPT_INJECTION → JAILBREAK → CONTEXT_MANIPULATION → DATA_LEAKAGE`
   - benchmark: `prompt_injection → jailbreak → data_leakage → hallucination → toxicity`
2. A per-model **agent** step (if `adaptive_agent`).
3. Global **leaderboard** step (if `generate_leaderboard`).
4. Global **report** step (if `generate_report`).

```
Model: gemma  →  PROMPT_INJECTION  →  JAILBREAK  →  DATA_LEAKAGE  →  Report
```

Every step carries `base_attacks`, `mutation_multiplier`, `passes`, and
`total_prompts = base_attacks × mutation_multiplier × passes`. The whole plan is
fingerprinted into a `deterministic_key` (SHA-256 of the ordered step signature):
identical inputs always yield the same key, so a plan is reproducible and a
resumed run matches the original.

The plan is pure data — it is returned over the API and embedded in the session
metadata by the scheduler, ready for the UI to visualize.

---

## 3. Scheduler architecture

`app/scheduler/evaluation_scheduler.py` is the seam between declarative profiles
and Sprint 1's durable execution. It intentionally does **not** re-implement the
run loop; it configures and drives it.

- `build_plan(profile, models, db)` → `ExecutionPlan`.
- `create_evaluation(profile, models, db)` → builds the plan and creates a
  persistent `EvaluationSession` whose `metadata` embeds the full plan,
  `deterministic_key`, evaluator, and judge model. `selected_tier` is the profile
  name.
- `pause` / `resume` / `cancel` → delegate to `SessionManager`, so recovery and
  durability behave exactly as in Sprint 1.
- `compute_retry_targets(session_id, retry_on)` → reads the session's recorded
  events and returns, in deterministic (event-id) order, the attacks whose
  verdict is in `retry_on` (`ERROR` maps to a `session_failed` event). This is
  how the retry policy in a profile becomes an actionable, reproducible set.

### Session/execution integration point

For `attack_library` profiles the resolved categories match the `attacks` table,
so the existing session runner executes them directly. For `benchmark_*`
profiles the plan and session are created and fully queryable, but running the
benchmark cases requires a benchmark-aware executor — that wiring is the intended
next integration step and is deliberately out of Sprint 2's scope (which builds
the planning/estimation foundation without modifying the Sprint 1 runner).

---

## 4. Runtime estimation algorithm

`app/runtime/runtime_estimator.py` produces an estimate from resolved plan
numbers. It is a **pure function** (`estimate_runtime`) fed by an async history
gatherer (`gather_latency_stats`).

**LLM calls**

```
per_model_target = base_attacks_per_model × mutation_multiplier × passes
target_calls     = per_model_target × num_models
judge_calls      = target_calls          (if evaluator = llm_judge, else 0)
agent_calls      = 8 × num_models         (if adaptive_agent, else 0)
total_calls      = target_calls + judge_calls + agent_calls
```

**Time** — data-driven and self-improving. It uses each model's *observed*
average latency from past `TestRun` rows (`gather_latency_stats`); models with no
history fall back to `DEFAULT_LATENCY_MS` (4000 ms). As evaluations accumulate,
estimates sharpen automatically.

```
time = (target + agent) × model_latency + judge_calls × judge_latency
```

**Memory / GPU** — model footprints are heuristic (`model_sizes.py`, keyed off
the parameter count in the model name, ~Q4 quantized). Ollama loads one model at
a time, so peak = largest single model + judge model (if separate) + fixed
overhead. GPU estimate = the model weights (which live in VRAM when a GPU is
used).

**Disk** — `total_calls × ~4 KB` (persisted rows/events), plus report headroom.

Every estimate includes a `breakdown` and human-readable `assumptions`.

---

## 5. Resource awareness

`app/resources/resource_monitor.py` detects the host's resources and assesses a
plan against them. It is **platform-independent** and dependency-free:

| Metric | Windows                      | Linux              | macOS                     |
|--------|------------------------------|--------------------|---------------------------|
| RAM    | `GlobalMemoryStatusEx`       | `/proc/meminfo`    | `sysctl` + `vm_stat`      |
| CPU    | `os.cpu_count()`             | + `getloadavg`     | + `getloadavg`            |
| GPU    | `nvidia-smi` (cached)        | `nvidia-smi`       | Apple Metal / `nvidia-smi`|
| Disk   | `shutil.disk_usage`          | same               | same                      |

`psutil` is used automatically **if present** for richer memory data, but is not
required. GPU probing (the one potentially slow call) is cached for the process
lifetime. Detection is best-effort and never raises — unknown values are `None`
and simply skip their check.

`assess_plan(estimate, snapshot)` returns **non-blocking warnings** (it never
prevents execution):

- estimated RAM > available RAM,
- no GPU detected (CPU inference will be slow),
- estimated VRAM > detected VRAM,
- estimated disk > free disk.

---

## 6. API

| Method | Path                              | Purpose                                        |
|--------|-----------------------------------|------------------------------------------------|
| GET    | `/api/evaluation-profiles`        | List all profiles                              |
| GET    | `/api/evaluation-profiles/{name}` | One profile (404 if unknown)                   |
| POST   | `/api/evaluation-plan`            | Build a plan + estimate + resource assessment  |
| GET    | `/api/runtime-estimate`           | Same preview via query params                  |

`/api/evaluation-plan` and `/api/runtime-estimate` return an `EnginePreview`:

```jsonc
{
  "profile": "quick_scan",
  "models": ["gemma:2b"],
  "estimated_time": { "seconds": 80.0, "minutes": 1.33 },
  "estimated_ram_mb": 2600,
  "estimated_gpu_mb": 2000,
  "estimated_llm_calls": 20,
  "execution_steps": [ /* ordered PlanStep list */ ],
  "warnings": [ /* non-blocking strings */ ],
  "plan": { /* full ExecutionPlan incl. deterministic_key */ },
  "estimate": { /* full breakdown + assumptions */ },
  "resources": { /* ResourceSnapshot */ }
}
```

These endpoints are read-only previews — they make **no LLM calls** and create
no sessions.

---

## 7. Future integration points

- **Start-from-profile endpoint / WebSocket feed.** `EvaluationScheduler.create_evaluation`
  already persists a session with the embedded plan; a thin `POST` endpoint can
  expose it, and the Sprint 1 event stream will feed the (future) live UI.
- **Benchmark-aware executor.** Extend the session runner to execute
  `benchmark_*` plans (see the integration note in §3), applying per-category
  caps, mutation, passes, and the LLM judge as declared by the profile.
- **Retry execution.** `compute_retry_targets` produces the deterministic retry
  set; a follow-up runner can consume it to re-run failed/errored attacks up to
  `retry.max_retries`.
- **Estimator feedback loop.** Every completed session enriches `TestRun`
  latency history, so `runtime-estimate` gets more accurate over time with no
  code changes.
- **Resource-adaptive profiles.** `assess_plan` warnings can later drive
  suggestions (e.g. "switch to Quick Scan" or "use a smaller model") in the UI.
```
