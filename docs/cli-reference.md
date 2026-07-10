# CLI Reference

The `redforge` command manages the whole lifecycle: install, run, evaluate, and
maintain. It is standard-library only and talks to the local backend over HTTP.

```
redforge <command> [options]
```

Run `redforge` with no arguments for help, or `redforge <command> --help` for a
command's options.

## Lifecycle

### `redforge install`
Set up RedForge: create a dedicated virtual environment, install the backend,
detect hardware and runtime providers, create shortcuts, and run a health check.
Idempotent — re-running repairs an existing installation.

### `redforge repair`
Repair an existing installation against its current environment. Equivalent to a
re-run of `install`; use it after a partial failure or dependency drift.

### `redforge uninstall [--purge]`
Remove the virtual environment and shortcuts. Your evaluation history and
settings are preserved unless you pass `--purge`, which also deletes the
database, logs, and settings.

### `redforge update [--check]`
Update to the latest GitHub release. Verifies the download's SHA-256 before
replacing any files, preserves your history and settings, and rolls back on
failure. `--check` reports whether an update is available without installing it.

## Running

### `redforge start [--host H] [--port P] [--dev] [--no-browser] [--yes]`
Start RedForge (a single process serving the API and UI) and open the browser.

| Option | Default | Meaning |
|--------|---------|---------|
| `--host` | `127.0.0.1` | Bind address. Non-local values prompt a network-exposure warning. |
| `--port` | `8000` | Port to serve on. |
| `--dev` | off | Developer mode (backend reload + Vite dev server). |
| `--no-browser` | off | Do not open the browser. |
| `--yes` | off | Skip the network-exposure confirmation for a non-local `--host`. |

### `redforge stop [--port P]`
Stop a running RedForge instance.

### `redforge status [--port P]`
Show whether RedForge is running, plus active sessions, model count, and runtime
metrics.

## Evaluations

### `redforge evaluate <model> [profile] [--port P]`
Start an evaluation of `model` using an evaluation `profile`
(default `quick_scan`). Prints the session id and a link to watch it live.

### `redforge benchmark <model> [--port P]`
Run the benchmark suite against `model` (a thorough profile over the bundled
dataset).

## Inspection

### `redforge doctor [--copy]`
Run the System Health Engine and print a system report (OS, Python, CPU, GPU,
RAM, disk, runtime, models, database). `--copy` prints a copyable plaintext
version for bug reports. Exit code is non-zero if a blocking check fails.

### `redforge models`
List installed models and a few recommended ones.

### `redforge logs [-n N]`
Show the last `N` log lines (default 60).

### `redforge diagnose [--port P] [-o FILE]`
Write a `diagnostics.zip` support bundle: system info, configuration (with
secrets redacted), health report, provider status, installed models, package
versions, and logs. **No API keys are ever included.** Safe to share.

### `redforge version` / `redforge --version`
Print the installed version.

## Environment variables

RedForge reads configuration from the environment (all optional):

| Variable | Purpose |
|----------|---------|
| `REDFORGE_RUNTIME_PROVIDER` | Active provider (`ollama`, `lmstudio`, …). |
| `REDFORGE_OLLAMA_URL` | Ollama base URL (default `http://localhost:11434`). |
| `REDFORGE_<PROVIDER>_URL` | Base URL for another provider. |
| `REDFORGE_PORT` | Default port. |
| `REDFORGE_HOME` | Override the install/data directory. |
| `REDFORGE_DATABASE_URL` | Override the database location. |
| `REDFORGE_LOG_LEVEL` | Log verbosity (default `INFO`). |

Provider API keys are read from each provider's standard variable (e.g.
`OPENAI_API_KEY`) and are never stored or logged. See [providers.md](providers.md).
