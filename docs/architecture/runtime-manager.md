# Runtime Manager (V1.2)

_Phase: build the management layer over the multi-provider runtime — API + UI to
inspect, test, and select providers. Status: implemented. Tests: **304 passed**
(was 293); frontend `tsc --noEmit` clean, `vite build` clean._

The Runtime Manager is a **read/refresh/select** layer on top of the existing
runtime. It does **not** run generations, install providers, or touch transport,
queue, retries, metrics, or cancellation — all model traffic still flows through
`RuntimeClient`, the single source of truth. The management layer only *reports*
status (via the `Provider` interface) and lets the operator pick the default
provider.

---

## Architecture

```
Frontend  /runtime  (RuntimeManagerPage.tsx)
  hooks: useProviders · useRuntimeStatus · useRuntimeLogs
         useRefreshProviders · useTestProvider · useSetDefaultProvider
        │  axios → /api
        ▼
Backend  app/api/providers.py         app/api/runtime_status.py
  GET  /api/providers                 GET /api/runtime/status   (existing)
  POST /api/providers/refresh         GET /api/runtime/logs     (new)
  POST /api/providers/default
  GET  /api/providers/{name}
  POST /api/providers/{name}/test
        │  delegates (no runtime logic here)
        ▼
app/runtime/management.py  ── ProviderManager (singleton)
  · list_infos()/info()   static registry data (no network)
  · check()/refresh_all() live probe: health · version · models
  · set_default()         → manager.set_default_provider()
  · in-memory cache: name → last health snapshot ("last check")
        │ uses only the public runtime surface
        ▼
app/runtime/manager.py            app/runtime/client.py
  registry (_PROVIDERS)            RuntimeClient  ← ALL shared logic (unchanged)
  available_providers()           Provider (ABC)
  build_provider(name)            get_runtime()  ← default provider path
  set_default_provider(name)
        ▼
app/runtime/providers/*  (unchanged provider classes)
```

**Single source of truth.** The default provider is always queried through
`get_runtime()` (the shared `RuntimeClient` — its model cache, logging). Non-default
providers are built on demand *only to report status* via `Provider.health()` /
`list_models()` / the optional `version()` — never to run traffic. No queue, retry,
metric, or cancellation code exists in the management layer.

**Health snapshots & "last check".** `ProviderManager` keeps an in-memory dict of
the last probe per provider (online/healthy/version/model_count/models/latency/
`checked_at`/error). `GET /api/providers` returns cached snapshots instantly;
`refresh` / `test` perform live probes and update the cache. Cloud providers with
a missing API key report `online=false` immediately (gated in `HttpProvider`) —
no hang.

**Provider version.** Exposed via an **optional, duck-typed** `version()` method
(implemented on `OllamaProvider` today). The `Provider` ABC is unchanged; the
manager calls `getattr(provider, "version", None)`. Providers without it report
`null` ("if available").

**Runtime logs.** `configure_logging()` attaches a bounded ring-buffer handler
(`deque(maxlen=1000)`) to the `redforge` logger. `GET /api/runtime/logs` returns
recent captured lines read-only. No disk access, independent of the CLI log file.

**Set default.** `set_default_provider()` updates `settings.RUNTIME_PROVIDER` and
calls `reset_runtime()` so the next `get_runtime()` rebuilds against the new
provider. **Process-local** — not persisted across restart (see limitations).

---

## Modified / new files

**Backend — new**

| File | Purpose |
|---|---|
| `app/runtime/management.py` | `ProviderManager` service + `provider_manager` singleton (list/info/check/refresh/set_default + health cache). |
| `app/api/providers.py` | Runtime Manager REST router (`/api/providers*`). |
| `tests/test_runtime_manager.py` | 11 tests (management service + all endpoints, fake-provider injected). |

**Backend — modified**

| File | Change |
|---|---|
| `app/runtime/manager.py` | Added `build_provider(name)` and `set_default_provider(name)`; `_build_provider()` now delegates to `build_provider`. Selection logic otherwise unchanged. |
| `app/runtime/providers/ollama.py` | Added optional `version()` (Ollama `/api/version`). |
| `app/logging_config.py` | Added ring-buffer log handler + `get_recent_logs()`; attached in `configure_logging`. |
| `app/api/runtime_status.py` | Added `GET /api/runtime/logs`. `GET /api/runtime/status` unchanged. |
| `app/main.py` | Registered the `providers` router. |

**Frontend — new**

| File | Purpose |
|---|---|
| `src/pages/RuntimeManagerPage.tsx` | The Runtime Manager page (status strip, provider table, details panel, read-only logs). |

**Frontend — modified**

| File | Change |
|---|---|
| `src/api/types.ts` | Added `ProviderHealth`, `ProviderInfo`, `ProvidersResponse`, `RuntimeStatusResponse`, `RuntimeLogLine`, `RuntimeLogsResponse`. |
| `src/api/endpoints.ts` | Added `getProviders`, `refreshProviders`, `getProvider`, `testProvider`, `setDefaultProvider`, `getRuntimeStatus`, `getRuntimeLogs`. |
| `src/hooks/queries.ts` | Added `useProviders`, `useRuntimeStatus`, `useRuntimeLogs`, `useRefreshProviders`, `useTestProvider`, `useSetDefaultProvider`. |
| `src/App.tsx` | Lazy route `/runtime` + tab title. |
| `src/components/AppShell.tsx` | Nav item **Runtime** (Server icon). |

---

## New API endpoints

All responses use the standard error envelope on failure. No existing endpoint
changed shape (API compatibility preserved).

### `GET /api/providers`
Installed providers + current default (fast; uses cached health, may be `null`
until a refresh/test). `health` is a snapshot or `null`.

```json
{
  "default": "ollama",
  "providers": [
    {
      "name": "ollama", "label": "Ollama", "is_default": true,
      "base_url": "http://localhost:11434",
      "requires_api_key": false, "api_key_env": null, "api_key_present": false,
      "health": {
        "name": "ollama", "online": true, "healthy": true,
        "version": "0.5.1", "model_count": 3, "models": ["qwen3:8b", "llama3", "gemma"],
        "base_url": "http://localhost:11434", "latency_ms": 4.2,
        "checked_at": "2026-07-09T10:12:04+00:00", "error": null
      }
    }
  ]
}
```

### `POST /api/providers/refresh`
Live-probes **every** provider concurrently (health/version/models), updates the
cache, and returns the same shape as `GET /api/providers` with fresh `health`.

### `POST /api/providers/default`
Body `{ "name": "openai" }`. Sets the process default provider. Returns
`{ "default": "openai" }`. **400** if the name is not registered.

### `GET /api/providers/{name}`
One provider: static info + last cached `health`. **404** if unknown.

### `POST /api/providers/{name}/test`
Live-tests a single provider connection; returns the fresh `HealthSnapshot` and
updates the cache. **404** if unknown.

```json
{ "name": "openai", "online": false, "healthy": false, "version": null,
  "model_count": null, "models": [], "base_url": "https://api.openai.com",
  "latency_ms": 1.1, "checked_at": "2026-07-09T10:15:00+00:00",
  "error": "OpenAI API key not set (set $OPENAI_API_KEY)" }
```

### `GET /api/runtime/logs?limit=200`
Read-only recent log lines (oldest → newest), `limit` 1–1000.

```json
{ "lines": [ { "ts": "…", "level": "INFO", "logger": "redforge.runtime",
              "message": "op=generate model=llama3 | generation completed" } ] }
```

### `GET /api/runtime/status` *(existing, unchanged)*
`{ "provider": "ollama", "concurrency_per_model": 1, "metrics": { … } }`.

---

## Frontend page

`/runtime` → **Runtime Manager**:

- **Status strip** — active provider, concurrency/model, active requests, avg
  latency (polls `/api/runtime/status` every 5s).
- **Provider table** — one row per installed provider: label + name, online/offline
  status dot + health badge, installed-model count, version, runtime URL, last
  health check, and per-row actions.
- **Actions** — *Test* (live-tests one provider, toasts the result), *Set default*
  (switches the active provider; disabled on the current default), header *Refresh*
  (probes all). On mount the page kicks one refresh so statuses populate.
- **Details panel** — click a row: runtime URL, health latency, model count,
  version, API-key requirement/status, last check, available-models chips, and any
  error. Shows an env-var hint when a required key is missing.
- **Runtime logs** — read-only, recent lines with level coloring; manual refresh +
  an auto-refresh (5s) toggle.

Per the constraints, the page has **no provider-installation** affordance.

---

## Constraints — how they're met

- **No provider installation** — the UI/API only inspect, test, and select.
- **No duplicated runtime logic** — management calls the `Provider` interface and
  `get_runtime()`; queue/retry/metrics/cancellation live solely in `RuntimeClient`.
- **RuntimeClient is the single source of truth** — the default provider is always
  reached through `get_runtime()`.
- **API compatibility** — only additive endpoints; existing shapes unchanged.
- **Existing tests preserved** — full suite **304 passed** (293 prior + 11 new).

---

## Known limitations

- **Default selection is process-local**, not persisted; a restart reverts to
  `REDFORGE_RUNTIME_PROVIDER`. (A future step could persist it to config/DB.)
- **Switching the default mid-run** affects only new generations; in-flight work on
  the previous provider continues. No per-session provider override yet.
- **`version()` is Ollama-only today** — other providers report `null` until an
  optional `version()` is added to them.
- **`model_count` for hosted providers requires a valid API key**; without one,
  health is `offline` and models are empty (by design).
- **Health cache is in-memory** and per-process; it resets on restart and isn't
  shared across processes.
- **Logs are an in-memory ring buffer** (last 1000 lines) — not the full history;
  the CLI still writes the complete log file to `.redforge/redforge.log`.
- **`set_default` mutates global settings**; concurrent multi-client use could race
  on the active provider (acceptable for the local single-operator tool).
