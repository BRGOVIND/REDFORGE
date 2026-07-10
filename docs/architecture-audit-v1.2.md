# RedForge — Codebase Audit (pre‑V1.2)

_Analysis only. No functionality was modified. Baseline: `pytest` → **260 passed** (backend), on branch `main` @ `97d4016`._

RedForge is a **local LLM red‑teaming lab**: point it at an Ollama model, run a
library of adversarial prompts + an 800‑case benchmark, and get a scored security
report. Production is a **single process** (FastAPI serves the API *and* the built
React SPA); the only end‑user runtime dependencies are **Python 3.11+** and **Ollama**.

---

## 1. Architecture Summary

### Layers

| Layer | Tech | Notes |
|---|---|---|
| CLI | Python **stdlib only** (`cli/redforge`) | `install/doctor/start/stop/status/models/evaluate/benchmark/logs/update/version`; talks to backend over HTTP; manages the process (pid/log in `.redforge/`). |
| API | FastAPI async, 19 routers (`app/main.py`) | Security headers + CORS middleware, standardized error envelope, `/healthz`, OpenAPI at `/docs`. |
| SPA serving | `static_serving.py` | Same process serves `backend/app/static` (bundled) or `frontend/dist`; SPA catch‑all mounted **last** so it never shadows `/api`. |
| Orchestration | `pipeline/`, `sessions/`, `scheduler/`, `execution/` | The intelligent pipeline: profile → plan → adaptive execute → analyze → report, all persisted per stage. |
| Intelligence | `profiler/`, `planner/`, `mutations/`, `evaluators/`, `analysis/`, `scoring/` | Deterministic planning (`deterministic_key` hash), adaptive escalation, heuristic + LLM‑judge evaluation, findings/recommendations. |
| Runtime | `runtime/` | Unified LLM client: `Provider` ABC + `OllamaProvider`; owns queue, cancellation, timeouts, retries, metrics, model cache. **No raw httpx error escapes.** |
| Data | SQLite via SQLAlchemy 2.0 async + aiosqlite; Alembic present | `db/models.py` (11 tables); `init_db()` uses `create_all` at startup. |
| Frontend | React 18 + TS + Vite + Tailwind + Recharts | Route‑lazy pages, axios client, TanStack‑style query hooks, poll‑based live streaming. |
| Packaging | `scripts/build_release.py`, `installers/` | Builds FE → bundles into backend static → stages backend/cli/datasets/docs → `.zip`/`.tar.gz` + launchers; Inno Setup (Win) + AppImage (Linux). |

### Startup flow (production)
`redforge start` → `process.start()` ensures a FE build exists → spawns
`uvicorn app.main:app` (single process) → writes pid → polls `/healthz` (≤40s) →
opens browser. FastAPI **lifespan**: `configure_logging` → set scoring engine →
`init_db()` (`create_all`) → `seed_attacks()`. Routers registered, then
`mount_frontend()` **last**.

### The two request→execution paths (important)
- **Intelligent path** — `POST /api/evaluate` → `EvaluationPipeline` → `AdaptiveExecutor`.
  Profile‑driven, judge‑capable, mutate/escalate/retry, heartbeats, deterministic plan.
- **Legacy batch path** — `POST /api/runs/batch` and `POST /api/sessions` (auto_start)
  → `SessionManager.run_session`. Flat `attack → score → next`, heuristic scorer only,
  no adaptivity.

Both write the **same** `TestRun` rows and `EvaluationEvent`s. This overlap is the
single biggest source of structural debt (see §3).

---

## 2. Dependency Graph (module‑level)

```
 cli/redforge (stdlib)  ──HTTP──►  FastAPI backend
      cli.py → process.py, paths.py, diagnostics.py, colors.py

 app/main.py
   ├─ middleware: SecurityHeaders, CORS
   ├─ errors.register_error_handlers
   ├─ static_serving.mount_frontend   (LAST)
   └─ routers (api/*) ─────────────────────────────────────────────┐
                                                                    │
 api/evaluate*  (pipeline)   → pipeline.EvaluationPipeline          │
 api/runs, api/sessions      → sessions.SessionManager              │
 api/evaluation_engine       → scheduler.plan_builder, runtime est. │
 api/{benchmarks,dataset,…}  → benchmarking/, dataset/              │
                                                                    │
 pipeline.EvaluationPipeline                                        │
   ├─ profiler.ModelProfiler ─► runtime (show_model)               │
   ├─ planner.EvaluationPlanner ─► planning_rules, scheduler        │
   ├─ execution.AdaptiveExecutor                                    │
   │     ├─ mutations.mutator                                       │
   │     ├─ evaluators.scoring / evaluators.judge ─► runtime        │
   │     └─ sessions.{event,session}_repository                     │
   └─ analysis.{security_analyzer,finding_generator,                │
                recommendation_engine,report_builder}               │
                                                                    │
 sessions.SessionManager                                            │
   ├─ evaluators.scoring                                            │
   ├─ api.runs.call_ollama  ◄─ LAZY import (breaks a cycle)         │
   └─ sessions.{event,session}_repository                           │
                                                                    │
 runtime.manager.get_runtime → runtime.client.RuntimeClient        │
   → Provider(ABC) → OllamaProvider → httpx → localhost:11434       │
   (+ queue, cancel, metrics, models cache, stream)                 │
                                                                    │
 Cross‑cutting (imported almost everywhere):                        │
   config.settings · logging_config · errors · db.database/db.models◄┘

 Frontend:
   main.tsx → App → pages/* → hooks/{queries,useSessionStream,
   useTerminalStream} → api/endpoints → api/client(axios) → /api
```

**Notable coupling / cycles**
- `sessions.session_manager` → `api.runs.call_ollama` (lazy import to dodge a
  cycle). A session‑layer module depending on an API‑layer module is inverted;
  it should call `runtime` directly.
- `runtime/__init__.py` deliberately exports **estimation only**, keeping the
  transport stack (`client`, httpx) out of estimation‑only imports. Good.
- `config`, `logging_config`, `db` are leaf/utility modules — clean.

---

## 3. Technical Debt

**Structural**
1. **Two overlapping execution engines** (`SessionManager.run_session` vs
   `AdaptiveExecutor`) duplicate the persist‑TestRun + emit‑events logic and can
   drift. Legacy path is non‑adaptive and heuristic‑only.
2. **Layer inversion:** `sessions` imports `api.runs.call_ollama` via a lazy
   import instead of depending on `runtime` directly.
3. **`DATABASE_URL` is hardcoded** in `db/database.py` (`sqlite+aiosqlite:///./redforge.db`),
   bypassing `config.settings` (which claims to be the single source of truth for
   tunables). It's **CWD‑relative**, so the DB location depends on where uvicorn
   starts (backend vs repo root → two different `redforge.db` files are possible).
4. **Alembic vs `create_all` coexist.** Startup builds the schema with
   `Base.metadata.create_all`; migrations in `alembic/versions/` are never run by
   the app. New columns added only via migrations won't exist on a
   `create_all`‑built DB unless also on the model — real drift risk, and no
   documented upgrade path for existing user DBs.

**Correctness / robustness**
5. **No auto‑resume on startup.** Sessions are durable and resumable, but nothing
   in `lifespan` re‑drives sessions left `running` after a crash/restart; they sit
   "running" forever unless a client calls `/resume`.
6. **Long evaluations run as FastAPI `BackgroundTasks`** — in‑process, no
   concurrency cap, no crash recovery, tied to the request lifecycle. Fine for
   local single‑user, weak for reliability/scale.
7. **Cancellation is coarse.** `pause/cancel` are only observed at attack
   boundaries; the in‑flight generation is not cancelled (the runtime *has* a
   `CancellationToken`, but session execution doesn't thread it through). Called
   out in ROADMAP.
8. **Heuristic scorer is brittle** (`evaluators/scoring.py`): English‑only regex
   compliance/refusal lists; the >0.5 prompt‑echo → `FAIL` rule can misfire on
   legitimate quoting. It's the default evaluator for non‑judge profiles.
9. **Judge JSON parsing is best‑effort** (`find('{')`/`rfind('}')`) and silently
   falls back to heuristics on any error — failures are invisible except via
   `used_fallback`.

**Hygiene**
10. **Version string duplicated in 8 places** (`VERSION`, root & `cli/pyproject.toml`,
    `cli/redforge/{__init__,cli}.py`, `app/main.py`, `frontend/package.json`,
    `installers/windows/redforge.iss`) — only `VERSION` is read at runtime; the
    rest are manual. Guaranteed to skew.
11. **`datetime.utcnow()` used throughout** `db/models.py` and managers →
    `DeprecationWarning` on 3.12; produces naive UTC datetimes (mixed with the
    timezone‑aware `datetime.now(timezone.utc)` used elsewhere).
12. **No CI** (`.github/workflows/` absent) despite ROADMAP promising tag‑based
    release builds; installer `.exe` isn't produced, so the site currently ships a
    ZIP as the Windows "primary download" (per recent commits).
13. **Backend deps unpinned** (`requirements.txt` uses `>=`, no lockfile/hashes);
    test deps mixed into runtime `requirements.txt`.
14. **No frontend tests** and no typecheck/lint in CI; **pytest collects the
    `TestRun` ORM model** as a test class (harmless warning ×3).
15. **`CORSMiddleware(allow_credentials=True)`** with a fixed localhost origin list
    — acceptable for a localhost tool, but there's **no auth** on any endpoint, so
    any local process/site permitted by CORS can drive evaluations.

---

## 4. Missing Features for V1.2 (gap list)

Derived from ROADMAP "near/mid term" + audit gaps. None implemented yet:

- **Live token streaming (SSE/WebSocket).** The runtime already streams
  (`generate_stream`/`run_stream`), but sessions persist discrete events and the
  UI **polls** (`after_id` cursor). V1.2 should surface real token streaming.
- **True cancellation.** Thread a `CancellationToken` from session pause/cancel
  into the in‑flight generation (debt #7) so stop is instant.
- **Crash/restart auto‑resume.** A lifespan hook (or the existing
  `evaluation_scheduler`) that finds `running` sessions and resumes them.
- **CI release pipeline.** Tag → build Windows `.exe` (Inno) + Linux AppImage →
  attach to GitHub Releases (debt #12). Prereq for a real installer download.
- **Second runtime provider.** An OpenAI‑compatible `Provider` (LM Studio / vLLM /
  llama.cpp). The abstraction is ready (`Provider` ABC + `manager._build_provider`
  switch); needs an implementation + config wiring + tests.
- **Config‑driven DB path** and a **user‑DB migration/upgrade path** (debt #3, #4).
- **Report PDF export** hardening / server‑side generation (README lists JSON/MD/PDF;
  verify PDF path robustness — likely client‑side today via `lib/export`).
- Nice‑to‑have from ROADMAP mid‑term (bundled Python runtime, macOS `.dmg`) — flag
  as beyond V1.2 unless scoped in.

---

## 5. Refactoring Recommendations (backwards‑compatible, no API changes)

Ordered by leverage. All preserve public HTTP contracts and keep the 260 tests green.

1. **Unify execution on `AdaptiveExecutor`.** Make `SessionManager.run_session`
   delegate to the adaptive executor with a `max_retries=0`, heuristic‑evaluator
   plan (i.e. legacy behavior expressed as a degenerate adaptive plan). Removes the
   duplicated persistence logic (debt #1) while `/api/runs/batch` responses stay
   byte‑for‑byte identical. Do it behind the existing injectable `generate_fn`/
   `judge_fn` seams so tests don't change.
2. **Route DB URL through `config.settings`.** Add `REDFORGE_DATABASE_URL`
   (default = current literal) and make the path repo‑root‑absolute so CWD no
   longer decides the DB file (debt #3). Pure default‑preserving change.
3. **Invert the sessions→api dependency** (debt #2): have `SessionManager._generate`
   call `runtime.get_runtime()` directly; keep `api.runs.call_ollama` as a thin
   wrapper for its own endpoints. Deletes a lazy import and a cycle.
4. **Single‑source the version.** Read `VERSION` (or `importlib.metadata`)
   everywhere; drop the hardcoded copies except the packaging manifests that must
   be literal, and generate those in `build_release.py` (debt #10).
5. **Migrate `datetime.utcnow()` → `datetime.now(timezone.utc)`** via a shared
   `_utcnow()` helper (already exists in some modules) applied consistently
   (debt #11). Behavior‑preserving, silences deprecations, fixes naive/aware mix.
6. **Decide Alembic vs `create_all`** (debt #4): either run migrations at startup
   (and make baseline == `create_all` output) or document `create_all` as the
   source of truth and repurpose Alembic for explicit upgrades only. Add a note +
   a schema‑parity test.
7. **Extract a shared "record attack result" writer** used by both execution
   paths (falls out naturally from #1) so `TestRun` + `VERDICT_GENERATED` metadata
   is emitted in exactly one place.
8. **Split test deps** into `requirements-dev.txt`; pin runtime deps or add a lock
   (debt #13). No runtime effect.
9. **Silence the pytest `TestRun` collection warning** with `__test__ = False` on
   the ORM class or a `collect_ignore`/naming tweak (debt #14).
10. **Add minimal CI** (lint + `pytest` + `tsc --noEmit` + `npm run build`) before
    touching release automation — gives V1.2 work a safety net.

### Guardrails for the V1.2 work
- Preserve every HTTP contract (paths, request/response shapes, status codes) —
  the frontend `api/endpoints.ts` and CLI depend on them.
- Keep the injectable `generate_fn`/`judge_fn`/`metadata_fetcher` seams; they are
  what make the suite deterministic without Ollama.
- Land each refactor behind unchanged defaults and re‑run `pytest` (must stay 260+).
```
```
