# RedForge — Global Task Manager

A single, app-wide execution surface (like Docker Desktop / VS Code) for every
long-running operation. It is **not a new engine** — RedForge already has exactly one:
the **Job System** (`app/jobs`). The Task Manager is a thin, unified *view + control*
over it, so there is **one source of truth and no duplicated state**.

## Architecture
```
Any long-running op ──submit──▶  Job System (app/jobs)   ← the ONE execution engine
                                    │  status, progress, logs, cancel, retry,
                                    │  concurrency, recovery, events, + ETA samples
                                    ▼
                         app/tasks  (facade + service)     ← projects Job → Task, no new state
                                    ▼
                         GET/POST /api/tasks                ← the one API the UI uses
                                    ▼
   TaskManagerProvider ─ TaskBarButton ("Running (N)") ─ TaskPanel (slide-over)
```

Every Task exposes: **status, progress (0–100), elapsed, ETA, current step, logs,
cancel, retry** — exactly the spec. ETA is a **moving average** of the real progress
rate (rolling samples on the Job), never a fabricated countdown.

## Backend (additive)
- `app/jobs/service.py` — records rolling `(timestamp, fraction)` progress samples for ETA.
- `app/jobs/repository.py` — `delete()` (task-history delete).
- `app/tasks/facade.py` — `Job → Task` projection, `estimate_eta_seconds` (moving average), labels, summary.
- `app/tasks/service.py` — list / summary / get / cancel / retry / delete over `job_service`.
- `app/api/tasks.py` — `GET /api/tasks`, `/summary`, `/{id}`, `POST /{id}/cancel|retry`, `DELETE /{id}`.
- Tests: `tests/test_tasks.py` (9) — projection, ETA math, control.

## Frontend (real, wired app-wide)
- `components/TaskManager.tsx` — `TaskManagerProvider` (polls `/api/tasks`, fires
  **Started/Completed/Failed/Cancelled/Waiting** toasts on real transitions),
  `TaskBarButton` (top-bar **Running (N)**), `TaskPanel` (Docker-style slide-over:
  live progress bars, %, ETA, elapsed, current step; cancel / retry / logs / delete;
  Active + History sections). Poll pauses on hidden tabs; fast while active, slow when idle.
- Wired in `main.tsx` (provider at root) and `AppShell.tsx` (button in the top bar, panel global).
- Tasks stay visible on every page; navigation never interrupts execution (work runs in the backend).

## What appears automatically
Everything already running as a Job shows up now with zero page changes: **training
(V3 platform), export (GGUF/Ollama), dataset processing, runtime & model discovery**.

## Migration (strangler-fig — the remaining work)
To reach *"every operation registers as a Task; no page-specific progress"*, the legacy
engines that still run their own background work must submit Jobs (one handler each),
then their local progress UI is removed:
- Legacy `/api/training` (`progress_store`) → `training` Job (the V3 path already is).
- Benchmarks, Evaluations, Red-team, Security scans, Model downloads, Report generation.

Each is an **additive** change (register a handler + submit a Job) verified independently;
the destination (this Task Manager) is complete and production-ready. No hacks, no
duplicated state — every migrated op flows through the one Global Task Engine.
