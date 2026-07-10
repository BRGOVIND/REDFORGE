# Startup / Launcher (V1.2)

_Phase: turn `redforge start` into a polished, desktop-app-like launcher that
reuses the System Health Engine. Status: implemented (CLI). Tests: **325 passed**;
frontend `tsc --noEmit` + `vite build` clean._

`redforge start` is now the primary startup experience. It detects an existing
instance, validates the environment through the **System Health Engine** (reused,
never duplicated), starts the single backend process, waits for and **verifies**
readiness, and opens the browser — with meaningful progress and actionable failure
messages instead of stack traces.

---

## Architecture

```
redforge start  (cli/redforge/process.py::start)
  1. Detect existing instance / port conflict   is_up() · _port_open()
  2. Pre-flight validation  ─────────────────►  diagnostics.collect()
        (reuses the Health Engine in-process)      → app.health.health_service.run()
  3. Prepare interface                            _ensure_frontend_built()
  4. Start backend (uvicorn) + retry once         subprocess + _wait_healthy(/healthz)
  5. Verify backend health  ─────────────────►  GET /api/health  (Health Engine over HTTP)
  6. Ready → open browser                         SPA routes to onboarding on first run
```

**One health implementation, two touch-points.** Pre-flight runs the engine
**in-process** (via `diagnostics.collect()`, which already consumes
`app.health.health_service`) *before* the backend exists; the post-start
verification calls `GET /api/health` *after* the backend is up. Both go through
the same engine — the launcher contains **no** detection or health logic of its
own.

**Reuse map:** Health Engine (`app.health`), Runtime Manager
(`provider_manager`, consumed transitively by the engine's `provider_health` /
`installed_models` checks), `RuntimeClient` (the engine's provider probe). The
launcher only orchestrates.

`diagnostics._run_engine()` now `chdir`s to the backend directory while running
the engine so its cwd-relative checks (database / permissions) reflect where the
backend actually runs — not the user's shell directory (this also stops `doctor`
leaving a stray `redforge.db`).

---

## Startup sequence

1. **Existing-instance detection.** `is_up(port)` (a live `/healthz`) → RedForge is
   already running: open the browser and exit `0` (no duplicate launch).
   `_port_open(port)` without `/healthz` → **another** process owns the port →
   actionable error, exit `1`.
2. **Pre-flight (Health Engine).** `→ Running system checks…` runs the engine and:
   - **Blocks** only on genuinely fatal problems — a `critical`-severity failure
     (e.g. Python < 3.11) or missing backend dependencies (`redforge install`).
   - **Surfaces non-blocking hints** for Runtime / Models / Database from the
     engine's checks (offline provider, no models) — the user can still launch and
     onboarding guides them.
3. **Interface.** `→ Preparing interface…` finds the built frontend (or builds it
   once if Node is available; otherwise serves API-only with a warning).
4. **Start backend.** `→ Starting backend…` spawns `uvicorn app.main:app`, writes
   the pid, then `→ Waiting for the backend to become ready…` polls `/healthz`
   (up to 40 s). On a **transient** failure it retries **once**; deterministic
   failures (port/module/db/permission) are not retried.
5. **Verify backend health.** `GET /api/health` prints the aggregate status and
   re-surfaces any `error`-level critical/high checks (runtime/db) as warnings.
6. **Ready.** `✓ RedForge is ready at http://…`, then `→ Opening your browser…`.
   The browser opens at `/`; the SPA routes to **onboarding on first run**, else
   the **dashboard** (localStorage `redforge_onboarded`). The launcher stays in the
   foreground; Ctrl-C terminates the backend and clears the pid.

Example (no runtime running — launch still succeeds):

```
Starting RedForge

→ Running system checks…
✓ System checks passed
! Runtime: Provider 'ollama' is offline or unreachable — Ensure the 'ollama' provider is running and reachable at http://localhost:11434.
! Models: Cannot list models — active provider is offline
→ Preparing interface…
✓ Interface ready
→ Starting backend…
→ Waiting for the backend to become ready…
✓ Backend is ready
! Backend health: warning (12 ok · 3 warning · 1 error)
✓ RedForge is ready at http://127.0.0.1:8000
→ Opening your browser…
```

---

## Failure handling flow

Every failure yields a **message + fix**, never a traceback. The backend log tail
is classified by `_diagnose_startup_failure`:

| Situation | Detected by | Message → Fix | Retry? |
|---|---|---|---|
| **Duplicate launch** | `is_up(port)` | opens browser, exits 0 | — |
| **Port already in use** | `_port_open` (no `/healthz`) or log `address already in use` / `10048` | "Port is in use…" → `redforge start --port 8100` | no |
| **Missing dependencies** | pre-flight `deps` check, or log `ModuleNotFoundError` | "Backend dependencies are not installed." → `redforge install` | no |
| **Python too old / critical** | pre-flight `critical` failure | shows the failing check → resolve & retry | no (blocks) |
| **Database unavailable** | log `unable to open database` / `database is locked` | "The database could not be opened." → check write permissions | no |
| **Permission denied** | log `permission denied` / `WinError 5` | "Permission was denied…" → writable location / adjust perms | no |
| **Runtime unavailable / missing** | engine `provider_health` (non-blocking hint) | "Runtime: … offline …" → start/install the provider | launch proceeds |
| **Missing models** | engine `installed_models` (non-blocking hint) | "Models: … offline / none …" | launch proceeds |
| **Generic startup crash** | anything else in the log | "The backend failed to start." → see log | **once** |

Philosophy: **block only on the un-fixable-by-launching** (bad Python, missing
deps, port conflict). Runtime/model gaps are recoverable through onboarding, so
they warn but never abort.

---

## Modified files

| File | Change |
|---|---|
| `cli/redforge/process.py` | Rewrote `start()` into the staged launcher: existing-instance/port detection, Health-Engine pre-flight, progress steps, retry-once, graceful failure diagnosis, and post-start `/api/health` verification. Added `_step/_ok/_warn/_fail`, `_preflight`, `_diagnose_startup_failure`, `_verify_backend_health`. `_start_dev` signature simplified. Public `start(host, port, *, dev, open_browser)` unchanged (backwards compatible). |
| `cli/redforge/diagnostics.py` | `_run_engine()` now runs the engine from the backend directory (`chdir`) so DB/permission checks are accurate and no stray `redforge.db` is created. |

No backend or frontend source changed this phase. `redforge start` flags
(`--host`, `--port`, `--dev`, `--no-browser`) are unchanged.

---

## Backwards compatibility

- `process.start(...)` keeps the same signature; `cli.py::cmd_start` is untouched.
- `stop`, `status`, dev mode, pid/log handling, and the single-process production
  model are unchanged.
- The only user-visible change is richer, staged output and actionable errors.

---

## Known limitations

- **First-run routing is client-side.** The launcher opens `/`; the SPA decides
  onboarding vs dashboard from `localStorage['redforge_onboarded']` (there is no
  server-side "onboarded" state), so the launcher can't open `/onboarding`
  directly.
- **Two provider probes.** Pre-flight and post-start verification each run the
  engine, which probes the default provider; when that provider is offline the
  connect timeout adds a few seconds. When the runtime is up, both are fast.
- **Retry is conservative.** Only a single retry, and only for non-deterministic
  failures — port/module/db/permission errors are reported immediately (retrying
  wouldn't help).
- **Progress is line-based** (stdlib only; no TUI/spinner animation), matching the
  CLI's dependency-light design.
- **Dev mode** keeps its lighter flow (backend `--reload` + Vite); the full
  pre-flight/verify sequence applies to the production `start`.
