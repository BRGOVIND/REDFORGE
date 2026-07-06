# RedForge Architecture

RedForge is a **local** AI-security evaluation platform: point it at an Ollama
model, run adversarial evaluations, and get a structured security report — all on
your own machine. This document is the map of the system for a new engineer.

For deep dives, see the focused docs:
[session-architecture](session-architecture.md) ·
[evaluation-engine](evaluation-engine.md) ·
[intelligent-evaluation](intelligent-evaluation.md) ·
[first-run-experience](first-run-experience.md) ·
[frontend-architecture](frontend-architecture.md).

---

## Top-level layout

```
RedForge/
├── backend/        FastAPI + SQLite (SQLAlchemy async) + Ollama
├── frontend/       The application UI (React + Vite + Tailwind)
├── website/        The marketing site (separate project)
├── datasets/       RedForge-Bench-V1 (800 static cases)
└── docs/           Architecture documentation
```

The **application** (`/frontend`) and the **marketing website** (`/website`) are
independent projects.

---

## Backend structure

```
backend/app/
├── config.py            # ⭐ single source of truth for all tunables (env-overridable)
├── logging_config.py    # ⭐ centralized structured logging (get_logger / log_op)
├── errors.py            # ⭐ standardized {success,error:{code,message,details}} responses
├── main.py              # app assembly: middleware, routers, lifespan, error handlers
│
├── db/                  # SQLAlchemy async engine + ORM models
├── api/                 # one router module per resource (thin HTTP layer)
├── sessions/            # durable evaluation sessions + event store + terminal derivation
├── evaluation_profiles/ # data-driven profiles (JSON) + registry
├── scheduler/           # deterministic execution-plan builder + scheduler
├── planner/             # intelligent plan (category order, mutation, retries) from history
├── profiler/            # model capability + history profiling
├── execution/           # adaptive attack executor (retry/escalate/heartbeat)
├── analysis/            # scoring → findings → recommendations → SecurityReport
├── pipeline/            # orchestrates profile→plan→execute→analyze→report
├── runtime/             # runtime/resource estimation
├── resources/           # cross-platform RAM/CPU/GPU/disk detection
├── evaluators/          # heuristic scorer + LLM-as-judge + hallucination
├── mutations/           # mutation strategies (reused by adaptive execution)
├── attacks/             # the built-in attack library
├── dataset/             # RedForge-Bench-V1 loader/validator/stats
├── benchmarking/        # multi-model benchmark runner
├── agents/              # autonomous red-team agent
└── scoring/             # weighted (CVSS-inspired) scoring engine
```

**Layering:** `api/` is a thin HTTP layer over domain packages; domain packages
depend downward (`pipeline` → `profiler`/`planner`/`execution`/`analysis` →
`sessions`/`evaluators`/`db`). `config` and `logging_config` are leaf modules
imported anywhere.

---

## Core subsystems

### Sessions & event store (`sessions/`)
The durable backbone. An `EvaluationSession` row tracks status and progress; an
append-only `EvaluationEvent` stream records every action with a monotonic `id`
cursor. `SessionManager` opens a short-lived DB session per unit of work, so
progress and events commit continuously — a session survives refresh and restart
and resumes from `completed_tasks`. See [session-architecture](session-architecture.md).

### Terminal (`sessions/terminal.py`)
Pure derivation: `event_to_line(event)` renders a real event into a color-coded
terminal line. `GET /api/sessions/{id}/terminal?after_id=N` streams new lines via
the same cursor. Never fabricates output.

### Evaluation engine (`evaluation_profiles/`, `scheduler/`, `runtime/`, `resources/`)
A user picks a **profile** (Quick Scan → Exhaustive); the **scheduler** expands it
into a **deterministic execution plan**; the **runtime estimator** predicts
time/RAM/GPU/LLM-calls (improving from history); the **resource monitor** checks
the plan against the host (non-blocking warnings). See [evaluation-engine](evaluation-engine.md).

### Intelligent pipeline (`profiler/`, `planner/`, `execution/`, `analysis/`, `pipeline/`)
`POST /api/evaluate` (model + profile) runs the whole loop: **profile** the model
→ **plan** intelligently from its history → **execute adaptively** (mutate +
escalate + retry, with heartbeats) → **analyze** into scores/findings → build a
**SecurityReport**. Everything is deterministic and persisted. See
[intelligent-evaluation](intelligent-evaluation.md).

---

## Event flow (one evaluation)

```
session_created → model_profiled → plan_generated
   → [ attack_started → response_received → verdict_generated
       (→ mutation_applied → attack_retried → …)  (heartbeat while waiting) ] × N
   → analysis_completed → report_generated → session_completed
```

Events power three consumers off one cursor: the **event feed**, the **terminal**,
and (future) a **WebSocket** — no consumer polls history twice.

---

## Cross-cutting concerns (Sprint 6)

- **Configuration** — `app/config.py`. Every timeout, URL, interval, and threshold
  lives here with a `REDFORGE_*` env override and identical defaults. Nothing is
  hardcoded across modules anymore.
- **Logging** — `app/logging_config.py`. `get_logger("<area>")` + `log_op(...)`
  attach standardized context (`op`, `session`, `model`, `duration`) with
  timestamp and severity from the formatter. Configured once in the app lifespan.
- **Errors** — `app/errors.py`. All errors return
  `{ "success": false, "error": { "code", "message", "details" } }`. Unexpected
  exceptions are logged with a traceback but return a safe generic message — no
  stack traces leak.

---

## Provisioning & migrations

The app provisions its schema on startup via `init_db()` → `create_all()`
(`main.py` lifespan) — this is the canonical path. Alembic migrations exist for
the tables added over time; the **baseline migration is intentionally a no-op**,
so pure-`alembic`-only provisioning (without ever booting the app) would not
create the four original tables. Not an issue for normal operation.

---

## Extension points

| To add… | Do this |
|---|---|
| An **attack** | Add to `attacks/library.py` (seeded on startup). |
| A **mutation strategy** | Add a `MutationStrategy` in `mutations/mutator.py`; adaptive execution reuses it. |
| An **evaluator/judge** | Add under `evaluators/`; wire via the profile's `evaluator`. |
| An **evaluation profile** | Drop a JSON file in `evaluation_profiles/data/` (or `REDFORGE_PROFILES_DIR`). |
| A **planning rule** | Add a pure function in `planner/planning_rules.py`. |
| A **finding/recommendation** | Extend `analysis/finding_generator.py` / `recommendation_engine.py`. |
| A **tunable** | Add to `config.py` with an env override. |
| A **terminal line** | Map the event in `sessions/terminal.py`. |
| An **API endpoint** | Add a router in `api/`, include it in `main.py`. |

---

## Frontend (application)

`frontend/src`: a thin, centralized architecture — `api/` (all HTTP), `hooks/`
(data + live streams), `lib/` (cache/toast/format), `components/` (design system),
`pages/` (routes). No business logic in components. See
[frontend-architecture](frontend-architecture.md).

---

## Quality gates

```
cd backend  && python -m pytest -q      # 233 tests
cd frontend && npm run typecheck && npm run build
cd website  && npm run typecheck && npm run build
```
