# System Health Engine (V1.2)

_Phase: a centralized System Health Engine — the single source of truth for every
system validation in RedForge. Status: implemented (backend only; API exposed, no
dedicated UI). Tests: **325 passed** (was 317); frontend `tsc --noEmit` + `vite build` clean._

Every system check now lives in one place: `app/health`. The CLI `doctor`, the
onboarding endpoint, startup validation, and (future) UI all **consume** this one
service — no check logic is duplicated. The engine is **provider-agnostic**: it
never branches on a provider's name; runtime/model checks delegate to the Runtime
Manager (`provider_manager`), which is itself provider-agnostic.

---

## Architecture

```
                         app/health/  (the engine — single source of truth)
                         ├─ models.py    HealthCheck · HealthReport · Status · Severity · aggregate()
                         ├─ checks.py    provider-agnostic check functions (Outcome)
                         ├─ service.py   HealthService: registry + run()/get_check()
                         └─ __init__.py  exports health_service
                              │ reuses (never reimplements):
                              ├─ resources.resource_monitor   RAM · disk · GPU · CUDA
                              ├─ runtime.management            provider health (agnostic)
                              ├─ runtime.manager               registered providers
                              ├─ static_serving                frontend build present
                              ├─ db.database                   database connectivity
                              └─ socket / platform / sys / tempfile
                              ▲
        consumers ───────────┤
        ├─ GET /api/health            (app/api/health.py)         → new API
        ├─ GET /api/health/{id}       (app/api/health.py)
        ├─ redforge doctor            (cli/redforge/diagnostics.py) → runs engine in-process
        ├─ GET /api/system/checks     (app/api/system.py)          → embeds report (opt-in)
        └─ startup lifespan           (app/main.py)                → logs a health summary
```

**One check, one implementation.** Each check is a small async function in
`checks.py` returning an `Outcome` (status + message + fix + metadata). The
service wraps it with a fixed **id, name, and severity** from the registry. Broken
checks are caught and reported — a single failing check never breaks the report.

**Severity is a property of the check, not the result.** `python_version` is
always `critical`; its *status* is `healthy` today and would be `error` on Python
3.10. Consumers compute readiness from severity: `ready = no error at
critical/high severity`.

**Provider-agnostic.** The `runtime_providers`, `provider_health`, and
`installed_models` checks iterate `manager.available_providers()` and delegate to
`provider_manager.check(default)`. There is no `if provider == "ollama"` anywhere
in the engine. (Ollama-specific onboarding lives only in the onboarding adapter.)

**Performance.** A run builds one shared context (one resource snapshot, one
provider probe) and runs all checks concurrently. The provider probe can stall to
its connect timeout when a local provider is down, so the **polled** onboarding
endpoint does **not** embed the engine by default (opt-in via `?include_health`);
`GET /api/health` is the on-demand path.

---

## Check schema

Every check returns exactly this shape — **never a plain string**:

```json
{
  "id": "python_version",
  "name": "Python",
  "status": "healthy",            // healthy | warning | error
  "severity": "critical",         // critical | high | medium | low | info
  "message": "3.12.1",
  "suggested_fix": null,
  "metadata": { "version": "3.12.1", "required": ">=3.11" }
}
```

**Checks (id · severity · reuses):** `os`·info, `architecture`·low,
`python_version`·critical, `runtime_providers`·high, `provider_health`·high,
`installed_models`·medium, `cpu`·info, `ram`·medium, `disk`·medium, `gpu`·low, `cuda`·low,
`ports`·low, `backend_status`·medium, `frontend_status`·medium, `database`·high,
`permissions`·medium, and `network`·low (**optional**, `?include_network=true`).

---

## New APIs

### `GET /api/health`
Full structured report. `?include_network=true` also runs the optional internet
check.

```json
{
  "status": "warning",
  "ready": true,
  "generated_at": "2026-07-09T10:00:00+00:00",
  "summary": { "total": 15, "healthy": 11, "warning": 4, "error": 0 },
  "checks": [
    { "id": "os", "name": "Operating System", "status": "healthy",
      "severity": "info", "message": "Windows 11", "suggested_fix": null,
      "metadata": { "system": "Windows", "release": "11" } },
    { "id": "python_version", "name": "Python", "status": "healthy",
      "severity": "critical", "message": "3.12.1", "suggested_fix": null,
      "metadata": { "version": "3.12.1", "required": ">=3.11" } },
    { "id": "provider_health", "name": "Provider Health", "status": "error",
      "severity": "high", "message": "Provider 'ollama' is offline or unreachable",
      "suggested_fix": "Ensure the 'ollama' provider is running and reachable at http://localhost:11434.",
      "metadata": { "provider": "ollama", "online": false,
                    "base_url": "http://localhost:11434", "version": null } },
    { "id": "gpu", "name": "GPU", "status": "healthy", "severity": "low",
      "message": "NVIDIA GeForce RTX 4070", "suggested_fix": null,
      "metadata": { "available": true, "name": "NVIDIA GeForce RTX 4070",
                    "total_mb": 8188, "free_mb": 7000, "backend": "cuda" } },
    { "id": "cuda", "name": "CUDA", "status": "healthy", "severity": "low",
      "message": "CUDA acceleration available (NVIDIA GeForce RTX 4070)",
      "suggested_fix": null, "metadata": { "backend": "cuda", "vram_total_mb": 8188 } }
    /* … ram, disk, ports, backend_status, frontend_status, database, permissions,
          runtime_providers, installed_models, architecture … */
  ]
}
```

> Note: the example shows `provider_health` in `error` (Ollama not running). With
> a reachable provider it is `healthy` and `ready` reflects only blocking errors.

### `GET /api/health/{id}`
A single check by id (e.g. `/api/health/gpu`). `404` for an unknown id (the error
lists the known ids).

```json
{ "id": "disk", "name": "Disk Space", "status": "healthy", "severity": "medium",
  "message": "412000 MB free", "suggested_fix": null,
  "metadata": { "free_mb": 412000, "total_mb": 1000000 } }
```

### `GET /api/system/checks?include_health=true` *(existing endpoint, extended)*
Onboarding contract is **unchanged** (`ready`, `checks[]`, `installed_models`, …);
now accepts `include_health=true` to embed the full engine report under `health`
(default off, so the wizard's 2.5 s poll stays cheap).

### `GET /healthz` *(unchanged)*
Liveness probe — separate from the health engine.

---

## Modified / new files

**New (backend):**
`app/health/__init__.py`, `app/health/models.py`, `app/health/checks.py`,
`app/health/service.py`, `app/api/health.py`, `tests/test_health.py`.

**Modified (backend):**

| File | Change |
|---|---|
| `app/main.py` | Registered `health` router; added non-blocking `_log_startup_health()` in the lifespan. |
| `app/api/system.py` | Onboarding now consumes the engine via `?include_health` (contract preserved). |
| `app/api/runtime_status.py` | *(unchanged this phase — logs endpoint from the prior phase)* |
| `tests/test_cli.py` | Updated to the engine's provider-agnostic labels. |

**Modified (CLI):**

| File | Change |
|---|---|
| `cli/redforge/diagnostics.py` | Rewritten as a thin consumer: runs the engine in-process and maps the report to the CLI's `Check` rows; minimal stdlib bootstrap fallback pre-install. Public surface (`collect`/`is_ready`/`as_plaintext`/`RECOMMENDED_MODELS`) preserved. |

**Modified (frontend — API surface only, no UI):**
`src/api/types.ts` (`HealthCheck`/`HealthSummary`/`HealthReport`, `health?` on
`SystemChecksResponse`), `src/api/endpoints.ts` (`getHealth`, `getHealthCheck`),
`src/hooks/queries.ts` (`useHealth`).

---

## Consumers — how each reuses the one engine

- **`redforge doctor`** runs `health_service.run()` in-process and renders the
  report; no check is reimplemented. Pre-`install` (backend deps absent) it prints
  a tiny stdlib bootstrap (Python + Ollama-on-PATH + "run redforge install").
- **`/api/system/checks`** (onboarding / First Run Wizard) keeps its Ollama-specific
  keys and embeds the full engine report on demand.
- **Runtime Manager** remains the provider source; the engine *consumes* it
  (`provider_health`/`installed_models`) — no circular dependency
  (`app/health → runtime.management`, never the reverse).
- **Startup validation** logs a health summary at boot (non-blocking).
- **Installer verification** is covered transitively — the installer calls
  `redforge doctor`, which now uses the engine.

---

## Future extension points

1. **Add a check** — write one async function in `checks.py` returning an
   `Outcome`, add one line (id, name, severity, fn) to `_REGISTRY` in `service.py`.
   It appears in `/api/health`, `redforge doctor`, and the embedded onboarding
   report automatically. No consumer changes.
2. **Categories/grouping** — the registry order is stable; a `category` field
   could be added to group checks (environment / runtime / resources / io) without
   changing the schema.
3. **Per-provider health matrix** — `provider_health` currently reports the
   default; it can be widened to probe all registered providers (metadata already
   provider-keyed) for a Runtime Manager health view.
4. **Remediation actions** — `suggested_fix` is a string today; a structured
   `action` (command/link) could drive one-click fixes in a future wizard UI.
5. **First Run Wizard UI** — consume `GET /api/health` directly (types + `useHealth`
   hook already shipped) to render a live, provider-agnostic readiness screen.
6. **Dataset / migration checks** — add engine checks for benchmark-dataset
   presence and Alembic head, replacing the last onboarding-specific bits.

---

## Known limitations

- **`provider_health` probes only the default provider** live (others would add
  latency). Widening is an extension point.
- **The provider probe can stall to its connect timeout** when a local provider is
  down (e.g. `localhost` resolving to IPv6 first). Hence the onboarding embed is
  opt-in and `/api/health` is on-demand, not polled.
- **`backend_status`/`ports` are context-relative** — from inside the running API
  the app port is "in use" (that's us); from the CLI pre-start it reads "not
  running". The raw facts are in `metadata`; consumers interpret.
- **`network` is optional and off by default** (it makes a real outbound request).
- **`permissions` checks the data directory** (DB parent) writability; it does not
  audit every path RedForge may touch.
- **No dedicated Health UI yet** — only the API + types/hook are shipped this phase.
