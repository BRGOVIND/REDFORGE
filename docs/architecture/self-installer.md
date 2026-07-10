# Self-Installer (`install` / `uninstall` / `repair`)

`redforge install` turns a RedForge release or checkout into a working
installation on Windows, Linux, or macOS with one command. It is **idempotent**:
running it again repairs the installation rather than duplicating it, and a
failed run never leaves a half-installed system.

Implemented in `cli/redforge/installer.py` (standard library only) with
`cli/redforge/shortcuts.py` for desktop / Start-Menu entries.

## What `install` does

In order, with friendly progress and actionable errors at each step:

1. **Detect the OS** — `platform.system()/release()/machine()`.
2. **Check Python ≥ 3.11** — fails early with an install link otherwise.
3. **Verify pip** — `python -m pip --version`.
4. **Create a dedicated virtual environment** at `~/.redforge/venv` (or
   `<root>/.redforge/venv`). Skipped if one already exists (repair).
5. **Install backend requirements** into that venv from
   `backend/requirements.txt` (pinned — see the release-engineering doc).
6. **Verify frontend assets** — a bundled build (`backend/app/static`) or a
   source build (`frontend/dist`). Missing assets are a warning, not a failure.
7. **Detect providers** — Ollama, LM Studio, llama.cpp, vLLM — by
   executable-on-PATH and default-port probe (dependency-free; the Runtime
   Manager reports live health afterwards).
8. **Create shortcuts** — Desktop + Start Menu (Windows), `.desktop` entries
   (Linux), a `.command` launcher (macOS). Best-effort; never fatal.
9. **Run the System Health Engine** — executed *through the venv interpreter*,
   so it is the real backend engine, not a reimplementation.
10. **Record state** in `~/.redforge/install.json` (version, venv, timestamp).

## The dedicated virtual environment

The `redforge` CLI is standard-library only and can be installed anywhere
(`pip install redforge`). The **backend** dependencies (FastAPI, uvicorn, …)
live in a separate venv created by `install`. Everything that runs the backend
resolves its interpreter through one function, `paths.backend_python()`:

```
paths.backend_python() = <venv python>  if the install venv exists
                       = sys.executable  otherwise (source checkouts)
```

`redforge start` uses it to launch uvicorn; `doctor` and `diagnose` use it to run
the Health Engine. There is exactly one resolution point — nothing hardcodes an
interpreter.

## Idempotency & rollback

- **Fresh install that fails** → a venv created *this run* is removed, so no
  half-built environment remains.
- **Repair that fails** → the existing environment is left untouched with a
  "re-run `redforge repair`" hint; user data is never deleted.
- **Running twice** → detects the existing venv, reinstalls requirements
  (pip is itself idempotent), refreshes shortcuts and state. This *is* repair;
  `redforge repair` is an explicit alias (`install(repair=True)`).

## `uninstall`

Removes the venv, the shortcuts, and the install-state file. Evaluation history
(`backend/redforge.db`) and settings are **preserved** by default; pass
`--purge` to delete the database, logs, and pid file too. The `redforge` command
itself is a pip package and is removed with `pip uninstall redforge`.

## `repair`

`install(repair=True)` — the same staged flow against the existing environment.
Use it after a partial failure, a moved install, or a dependency drift.

## Reuse, not duplication

- System validation is the backend **Health Engine**, run via the venv.
- Provider *presence* detection at install time is intentionally dependency-free
  (deps may not exist yet); live provider *health* comes from the Runtime
  Manager once the server is up.
- Interpreter/venv/path resolution lives in `cli/redforge/paths.py` and is shared
  by `start`, `update`, and `diagnose`.

## Errors

Every fatal problem raises `InstallError(message, fix)` and prints a red line
with a concrete fix (install Python, install pip, check the network, re-run
`repair`). Non-fatal issues (no frontend build, no running provider, no
shortcuts) are yellow warnings that do not stop the install.

## Tests

`backend/tests/test_selfinstaller.py` covers OS/Python/pip detection, provider
detection shape, and install-state round-trips (no venv is created and no network
is used in tests).
