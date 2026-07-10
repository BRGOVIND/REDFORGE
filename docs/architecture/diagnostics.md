# Diagnostics (`redforge diagnose`)

`redforge diagnose` collects a shareable support bundle, `diagnostics.zip`, with
everything needed to debug an installation — and **nothing secret**. Implemented
in `cli/redforge/diagnose.py` (standard library only).

## What it collects

| File in the zip | Contents | Source |
|-----------------|----------|--------|
| `system.json` | OS, Python, machine, install root, backend interpreter | `platform`, `paths` |
| `config.json` | `REDFORGE_*` env (secrets redacted) + provider-key *presence* | environment (allowlisted) |
| `install.json` | install state, venv/frontend presence | `installer.read_state` |
| `health.json` | System Health Engine report | Health Engine |
| `providers.json` | provider status (health, version, key-present) | Runtime Manager |
| `runtime_status.json` | runtime metrics (queue, latency) | `/api/runtime/status` |
| `models.json` | installed models per provider | Model Manager catalog |
| `packages.txt` | `pip freeze` of the backend environment | venv interpreter |
| `logs.txt` | recent logs | log API or log file |
| `MANIFEST.txt` | index + "no secrets" statement | generated |

## Two sources, best available first

- **Live server** (something is listening on the port): the bundle reads
  `/api/health`, `/api/providers`, `/api/runtime/status`, `/api/models/catalog`,
  and `/api/runtime/logs`. This is the richest source and reuses the running
  **Runtime Manager** and **Health Engine** directly — no reimplementation.
- **Offline** (no server): the Health Engine is run through the backend
  interpreter, and logs are read from `~/.redforge/redforge.log`. Provider,
  runtime, and model sections note that a running server is needed for live data.

## API keys are never included

Three independent guarantees:

1. **Allowlist.** Config collection only reads `REDFORGE_*` variables — never the
   full environment.
2. **Name-based redaction.** Any value whose name matches
   `KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH|CREDENTIAL` becomes `***REDACTED***`.
   Provider API keys (`OPENAI_API_KEY`, …) are recorded as **presence booleans**
   only.
3. **Whole-bundle scrub.** `_scrub` walks the entire assembled structure before
   serialization and redacts any secret-named key from *any* source (including
   the live API), so nothing can slip through.

The API itself never returns key values (only `api_key_present`), so the live
path is safe by construction; the scrub is defense in depth.

## Usage

```bash
redforge diagnose                 # writes ./diagnostics.zip
redforge diagnose -o /tmp/rf.zip  # custom path
redforge diagnose --port 8100     # non-default server port
```

## Tests

`backend/tests/test_selfinstaller.py` verifies config redaction, the recursive
scrub of nested secret keys, and that a full generated bundle contains the
expected files and **none** of a planted API-key value.
