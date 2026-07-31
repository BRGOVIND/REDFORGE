# Developer Guide

Getting a RedForge development environment running, and the conventions that keep
the codebase coherent.

End users need none of this — they download an installer. See the
[Packaging Guide](packaging-guide.md) and [Release Guide](release-guide.md).

---

## Requirements

| Tool | Version | Needed for |
|------|---------|-----------|
| Python | 3.11+ | backend, CLI, build scripts |
| Node.js | 20+ | frontend, website, desktop shell |
| A local runtime | — | running models (Ollama recommended) |
| CUDA GPU | optional | experimental real training only |

---

## Setup

```bash
git clone https://github.com/BRGOVIND/REDFORGE.git
cd REDFORGE

# Backend
pip install -r backend/requirements.lock -r backend/requirements-dev.txt

# Frontend
cd frontend && npm ci && cd ..
```

### Run

```bash
# Backend  → http://127.0.0.1:8000
cd backend && python -m uvicorn app.main:app --reload

# Frontend → http://127.0.0.1:5173 (proxies /api to the backend)
cd frontend && npm run dev
```

The desktop shell against that same backend:

```bash
cd desktop && npm install && npm start
```

---

## Layout

```
backend/app/         FastAPI backend, one package per bounded context
  api/               HTTP routers — thin, no business logic
  jobs/              the ONE execution engine (every long task is a Job)
  hardware/          GPU/VRAM feasibility (Hardware Compatibility Engine)
  environment/       host tool detection (Python, CUDA, Ollama, …)
  settings/          user settings schema + service
  training/          fine-tuning providers (unsloth / managed / simulation)
  training_runtime/  the optional 2–4 GB training engine: detect, plan, install
frontend/src/        React UI
  components/        shared UI, TaskManager, CommandPalette
  pages/             one file per route
  api/               the typed API surface — components never call axios directly
desktop/electron/    Electron main process (window, backend supervisor, updates)
website/src/         the marketing site
scripts/             version, release notes, icons, asset verification
docs/                these documents
```

---

## Architecture rules

From `docs/REDFORGE_V3_CONSTITUTION.md`. These are enforced by review, and
violating them is the main way this codebase would rot.

- **Bounded contexts.** A context owns its domain, service and repository. Cross-
  context communication goes through the Event Bus, never direct imports.
- **Pure domain.** No SQLAlchemy in domain or service layers. Domain modules do no
  I/O, which is what makes them trivially testable.
- **Dependency inversion.** Services depend on repository interfaces, not sessions.
- **Runtime never imports Training.** Inference must not depend on the training stack.
- **Additive migrations only.** New tables and columns; never destructively alter
  an existing one. `_reconcile_columns()` adds missing columns at startup.
- **Extend, don't replace.** New capability arrives as a new context behind a seam
  (strangler fig), leaving existing behaviour working.

### The single-process constraint

The backend is one asyncio process. **Blocking work in an async handler freezes
the entire application** — including the health endpoint the desktop shell polls.
Anything CPU-bound or blocking goes on a thread:

```python
result = await asyncio.to_thread(expensive_sync_call, arg)
```

Training providers use a `threading.Thread` + `queue.Queue` bridge for the same
reason.

---

## Tests

```bash
cd backend && python -m pytest -q          # full suite
python -m pytest tests/test_environment.py -q
cd frontend && npx tsc --noEmit            # typecheck
python -m ruff check .                     # lint
python scripts/version.py --check          # version drift
```

Tests never reach a live provider — the runtime is faked through the
`generate_fn` / `judge_fn` seams (see `backend/tests/conftest.py`). Prefer
injecting a fake over monkeypatching internals: `test_environment.py` injects its
probe, so it produces the same result on a bare CI runner and a loaded dev box.

CI (`.github/workflows/ci.yml`) runs version, lint, backend and frontend jobs on
every push and PR, and is reused as the gate for releases.

### The lint gate

`ruff` is configured narrowly on purpose (`[tool.ruff]` in `pyproject.toml`):
syntax errors and undefined names only. It is a correctness gate, not a style
gate — enabling style rules wholesale would flood CI with pre-existing findings
and train everyone to ignore it. Widen `select` deliberately, in its own change,
once the tree is clean for the new rules.

---

## Adding things

**An API endpoint** — router in `backend/app/api/`, business logic in the context's
service, typed client function in `frontend/src/api/endpoints.ts`, types in
`types.ts`. Components import from `endpoints.ts`, never axios.

**A long-running operation** — register a handler with the Job System. Do not
invent page-specific progress; the Global Task Manager renders any job
automatically, with ETA, cancel, retry and history.

**A setting** — one entry in `backend/app/settings/schema.py`. The API groups it
and the UI renders the control from its `type`. No per-setting code. Settings are
**authoritative**: if you add one, wire a consumer in the same change. Sync
callers read it via `settings_service.get_sync(key)`; a setting nothing reads is
a bug, not a placeholder.

**A training provider** — see the
[Training Runtime Guide](training-runtime-guide.md#adding-a-training-provider).

**A detected dependency** — one entry in `_SPEC` plus a remedy per platform in
`backend/app/environment/detector.py`.

---

## Conventions

- Never commit a version literal — bump `VERSION`, run `scripts/version.py --sync`.
- Comments explain *why*, not *what*.
- Errors must be actionable: what failed, why, and what to do next. No bare
  "Something went wrong."
- Experimental features are labelled in the UI. Simulated results say so.
- Local-first: no telemetry, no account, no mandatory cloud.
