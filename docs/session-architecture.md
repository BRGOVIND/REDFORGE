# Session Architecture

RedForge V3 replaces the old in-memory batch job store with **persistent,
resumable evaluation sessions**. Every piece of run state lives in the database,
so a session survives a browser refresh, a backend restart, a long-running
evaluation, and resumes cleanly after an interruption.

This document describes the session lifecycle, the database schema, the event
flow, the recovery process, and the integration points a future WebSocket live
feed will plug into.

---

## Why this exists

Previously, `POST /api/runs/batch` created a `job_id` backed by a process-local
`dict` (`JOB_STORE`). That had three failure modes:

1. **404 on poll** — a client could receive a `job_id` and get `404` when polling
   status if the lookup raced or the worker hadn't populated the store.
2. **Lost on restart** — restarting the backend wiped every in-flight job.
3. **No history** — once the process died, there was no record of what happened.

Sessions fix all three: the `job_id` is now a durable session id, status is read
straight from the database, and every significant action is recorded as an event.

---

## Components

```
backend/app/sessions/
├── constants.py          # SessionStatus, SessionType, EventType (string enums)
├── session_repository.py # CRUD + status/progress writes for evaluation_sessions
├── event_repository.py   # append-only writes/reads for evaluation_events
└── session_manager.py    # orchestration: create / run / pause / cancel / resume
```

- **`SessionRepository`** and **`EventRepository`** are thin persistence layers.
  Each takes an `AsyncSession` and owns the commits for its writes.
- **`SessionManager`** is built around a *session factory* (`async_sessionmaker`),
  not a single request-scoped session. It opens a short-lived DB session for
  each unit of work, committing progress and events continuously. This is what
  makes restart-recovery possible. Inference (`generate_fn`) is injectable so
  tests run without a live Ollama.

The HTTP layer lives in `backend/app/api/sessions.py` and exposes the manager
through the `get_session_manager` FastAPI dependency (overridable in tests).

---

## Session lifecycle

```
                 create_session()
                        │
                        ▼
                   ┌─────────┐
                   │ pending │
                   └────┬────┘
                        │ run_session()
                        ▼
                   ┌─────────┐   pause_session()   ┌────────┐
                   │ running │ ──────────────────▶ │ paused │
                   └────┬────┘ ◀────────────────── └────────┘
                        │        resume_session()
        ┌───────────────┼───────────────┐
        │ all tasks     │ inference      │ cancel_session()
        │ done          │ error          │
        ▼               ▼                ▼
   ┌───────────┐   ┌────────┐      ┌───────────┐
   │ completed │   │ failed │      │ cancelled │
   └───────────┘   └───┬────┘      └───────────┘
                       │ resume_session()
                       ▼
                   (running…)
```

| Status      | Meaning                                                        | Resumable |
|-------------|----------------------------------------------------------------|-----------|
| `pending`   | Created, not yet started                                       | yes       |
| `running`   | Executing tasks (or interrupted mid-run after a crash)         | yes       |
| `paused`    | Stopped at a task boundary on request                          | yes       |
| `completed` | All tasks finished                                             | no (noop) |
| `failed`    | An inference error aborted the run                            | yes       |
| `cancelled` | Stopped on request; not intended to continue                 | no (noop) |

`resume_session()` is a no-op for the terminal states (`completed`, `cancelled`)
and continues execution for `pending`/`running`/`paused`/`failed`.

### Deterministic task ordering

A session's work is the cross product `selected_models × attacks`, where
`attacks` are the rows matching `selected_categories` (all attacks if none
selected), ordered by `attacks.id`. Because the ordering is deterministic and
`completed_tasks` counts how many finished, resume simply **skips the first
`completed_tasks` entries** and continues. No task is ever run twice.

---

## Database schema

### `evaluation_sessions`

| Column                | Type        | Notes                                            |
|-----------------------|-------------|--------------------------------------------------|
| `id`                  | String(36)  | UUID4, primary key                               |
| `session_type`        | String(50)  | `batch` / `benchmark` / `agent` / `single`       |
| `status`              | String(20)  | see lifecycle table                              |
| `selected_models`     | JSON        | `list[str]`                                      |
| `selected_categories` | JSON        | `list[str]`                                      |
| `selected_tier`       | String(50)  | optional benchmark tier                          |
| `total_tasks`         | Integer     | computed at creation                             |
| `completed_tasks`     | Integer     | advanced as work finishes (drives resume)        |
| `created_at`          | DateTime    |                                                  |
| `started_at`          | DateTime    | set on first transition to `running`             |
| `completed_at`        | DateTime    | set on terminal transition                       |
| `estimated_seconds`   | Float       | `total_tasks × AVG_TASK_SECONDS`                 |
| `actual_seconds`      | Float       | wall-clock from `started_at`                     |
| `metadata`            | JSON        | free-form; e.g. `{"error": "..."}` on failure    |

> The ORM attribute is `session_metadata` because `metadata` is reserved by
> SQLAlchemy's Declarative API; the DB column is still named `metadata`.

### `evaluation_events`

Append-only. Never mutated after insert.

| Column             | Type        | Notes                                          |
|--------------------|-------------|------------------------------------------------|
| `id`               | Integer     | autoincrement PK, also the stream cursor       |
| `session_id`       | String(36)  | FK → `evaluation_sessions.id`, indexed         |
| `timestamp`        | DateTime    |                                                |
| `event_type`       | String(50)  | see event flow                                 |
| `model_name`       | String(200) | nullable                                       |
| `category`         | String(50)  | nullable                                       |
| `attack_name`      | String(200) | nullable                                       |
| `response_excerpt` | Text        | truncated to `RESPONSE_EXCERPT_LEN` (500)      |
| `verdict`          | String(20)  | `PASS` / `FAIL` / `UNCERTAIN`                   |
| `latency_ms`       | Integer     | nullable                                       |
| `metadata`         | JSON        | full result payload on `verdict_generated`     |

Migration: `alembic/versions/20260706_1000-a1b2c3d4e5f6_add_evaluation_session_tables.py`
(`down_revision = e3f8b1d92c45`). `init_db()` also creates the tables via
`create_all` for local/dev use.

---

## Event flow

Every significant action emits exactly one event. A full single-model,
two-attack run produces:

```
session_created
  └─ model_started            (once per model)
       ├─ attack_started
       ├─ response_received    (excerpt + latency)
       ├─ verdict_generated    (metadata = full RunResult payload)
       ├─ attack_started
       ├─ response_received
       └─ verdict_generated
session_completed
```

On an inference error the tail becomes `session_failed` instead of
`session_completed`, with the error string in the event metadata.

The `verdict_generated` event's `metadata` carries the complete per-attack
result (`attack_id`, `prompt_sent`, `model_response`, `score`, `verdict`,
`reason`, `latency_ms`, `timestamp`). This is what lets the legacy
`GET /api/runs/{job_id}/status` endpoint rebuild its `results` array purely from
persisted state — no in-memory store required.

Alongside events, each finished attack also writes a `TestRun` row, so existing
**reports, dashboards, and analytics keep working unchanged** and can be
generated from persisted session data.

---

## API

| Method | Path                              | Purpose                                  |
|--------|-----------------------------------|------------------------------------------|
| POST   | `/api/sessions`                   | Create a session (optionally auto-start) |
| GET    | `/api/sessions`                   | List sessions (`status`, `session_type`) |
| GET    | `/api/sessions/{id}`              | Fetch one session                        |
| POST   | `/api/sessions/{id}/resume`       | Resume (background)                      |
| POST   | `/api/sessions/{id}/pause`        | Pause                                    |
| POST   | `/api/sessions/{id}/cancel`       | Cancel                                   |
| GET    | `/api/sessions/{id}/events`       | Events (`after_id`, `event_type`)        |

**Guarantee:** `create_session` commits the row *before* returning, so a `GET`
immediately after a `POST` never returns `404`. Long-running execution is
scheduled as a FastAPI background task; the request returns as soon as the
session is durably recorded.

The refactored batch endpoints (`POST /api/runs/batch`,
`GET /api/runs/{job_id}/status`) are now thin wrappers over a `batch` session —
`job_id` **is** the session id.

---

## Recovery process

1. On restart, sessions left in `running` are simply interrupted rows in the DB.
2. A client (or an operator) calls `POST /api/sessions/{id}/resume`.
3. `run_session` reloads the plan, computes `already_done = completed_tasks`,
   marks the session `running` again, and continues from task index
   `already_done`.
4. Because ordering is deterministic and progress is committed per task, no work
   is duplicated and no work is skipped.

This is exercised by `test_session_survives_backend_restart`, which uses a real
on-disk SQLite file, disposes the engine to simulate a shutdown, opens a fresh
engine on the same file, and resumes to completion.

---

## Future WebSocket integration points

This sprint builds **only the backend event system**; the live UI feed comes
later. The design is deliberately WebSocket-ready:

- **Catch-up + live via one cursor.** The event `id` is a monotonic stream
  cursor. `EventRepository.list_for_session(session_id, after_id=N)` (exposed as
  `GET /api/sessions/{id}/events?after_id=N`) returns everything after cursor
  `N`. A WebSocket handler will: (1) send the backlog with `after_id` = the
  client's last-seen id, then (2) stream new events as they are written.
- **Durable replay.** Because events are persisted, a client that reconnects
  after a refresh or backend restart replays missed events by passing its last
  `after_id` — no events are lost.
- **Typed contract.** Event types are fixed in `EventType`
  (`session_created` → `session_completed`/`session_failed`). A future
  `/ws/sessions/{id}` endpoint can reuse the exact `EventResponse` schema already
  returned by the REST events endpoint, so the wire format is identical.
- **Suggested implementation.** Add a lightweight in-process pub/sub (e.g. an
  `asyncio.Queue` per session id) that the `EventRepository.add` path publishes
  to after commit; WebSocket clients subscribe, receiving the persisted event
  immediately while the DB remains the source of truth for catch-up.
```
Client ──WS connect──▶  send events after_id=last_seen (backlog from DB)
                        then stream newly-committed events (pub/sub)
```
