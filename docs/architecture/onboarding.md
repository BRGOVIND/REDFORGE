# First Run Wizard (Onboarding) — V1.2

_Phase: a professional first-run onboarding experience that consumes the existing
System Health Engine, Runtime Manager, and Model Manager. Status: implemented.
Tests: **325 passed**; frontend `tsc --noEmit` + `vite build` clean._

The wizard appears the **first time** RedForge is opened and never again once
completed (unless manually reset). It re-implements **no** detection logic — every
value comes from the three existing services.

---

## Architecture

```
/onboarding  (full-screen, outside AppShell)   src/pages/OnboardingPage.tsx
  Welcome → System Scan → Runtime → Models → Ready
        │ consumes (no duplicated detection):
        ├─ useHealth()        → GET /api/health        (System Health Engine)
        ├─ useProviders()     → GET /api/providers      (Runtime Manager)
        └─ useModelCatalog()  → GET /api/models/catalog  (Model Manager)
```

- **System Scan** is driven entirely by the **Health Engine** — every row maps to
  a health check id (`os`, `cpu`, `gpu`, `ram`, `disk`, `provider_health`,
  `runtime_providers`, `installed_models`, `backend_status`). No detection happens
  in the UI.
- **Runtime detection** uses the Health Engine's live `provider_health` probe to
  decide "detected / not", and the **Runtime Manager** provider list for the
  registered count. Supported-runtime install links are static reference content.
- **Model detection** consumes the **Model Manager** catalog (`total` + per-provider
  groups), falling back to the Health Engine's `installed_models` count.
- **Ready** summarizes from the same three sources (active runtime, model count,
  overall health status).

A new `cpu` check was **added to the Health Engine** (not the UI) so "CPU" in the
scan is single-sourced like everything else — extending the single source of truth
rather than duplicating detection.

`App.tsx` renders `/onboarding` **outside** the `AppShell` (no sidebar) for a
focused, full-screen first-run experience; all other routes are unchanged.

---

## UI flow

```
┌────────────── 1 / 5  Welcome ──────────────┐
│ Shield mark · "Welcome to RedForge"        │
│ • Local red-teaming lab                    │
│ • Everything on your machine               │
│ • No cloud, no API keys                    │
│ • Open source                [ Get started ]
└────────────────────────────────────────────┘
                    ↓
┌────────────── 2 / 5  System Scan ──────────┐   ← Health Engine
│ ✓ Operating System   Windows 11            │
│ ✓ CPU                16 logical cores       │
│ ⚠ GPU                No GPU — CPU           │
│ ✓ Memory / Disk      …                      │
│ ✕ Runtime            ollama offline         │
│ ✓ Installed Providers 9 registered          │
│ ⚠ Models             none                    │
│ ✓ Backend            reachable  [ Continue ] │
└────────────────────────────────────────────┘
                    ↓
┌────────────── 3 / 5  Runtime ──────────────┐   ← Runtime Manager + Health
│ if none: "No runtime detected"             │
│ Supported: Ollama · LM Studio · llama.cpp  │
│ each → [ Install ↗ ]  (never auto-installs)│
└────────────────────────────────────────────┘
                    ↓
┌────────────── 4 / 5  Models ───────────────┐   ← Model Manager
│ if 0: "No local models were found."        │
│       $ ollama pull qwen3:8b  ⧉            │
│ else:  N models found · chips per provider │
└────────────────────────────────────────────┘
                    ↓
┌────────────── 5 / 5  Ready ────────────────┐
│ Rocket · "System ready"                    │
│ [Runtime] [Models] [Health]                │
│              [ 🚀 Launch RedForge ]         │
└────────────────────────────────────────────┘
```

Top of every step: brand mark, `n / 5` counter, and a 5-segment progress bar.
Bottom: **Back** / **Continue** (**Launch RedForge** on the final step). Minimal,
no gratuitous animation — only the progress bar's color transition.

---

## Persistence mechanism

- **Key:** `localStorage['redforge_onboarded']`.
- **Set** to `'1'` when the user clicks **Launch RedForge** (last step), then
  navigates to `/`.
- **First-run gate** (`App.tsx`): on load, if the key is not `'1'` and the path is
  `/`, redirect to `/onboarding`. Once set, the wizard never auto-appears again.
- **Manual reset:** remove the key —
  `localStorage.removeItem('redforge_onboarded')` (DevTools console) — and reload.
  The route `/onboarding` is always reachable directly to re-run it.
- Client-side only (per-browser), consistent with the app's other first-run flag.

---

## Files

**New (frontend):** `src/pages/OnboardingPage.tsx`.

**Modified (frontend):**

| File | Change |
|---|---|
| `src/App.tsx` | Lazy `/onboarding` route rendered full-screen (outside `AppShell`); first-run redirect now uses `redforge_onboarded` → `/onboarding`. |
| `src/hooks/queries.ts` | `useProviders` / `useModelCatalog` gained an `enabled` flag so the wizard fetches them lazily per step. |

**Modified (backend):**

| File | Change |
|---|---|
| `app/health/checks.py` | Added `check_cpu` (logical core count, from the shared resource snapshot). |
| `app/health/service.py` | Registered the `cpu` check (severity `info`). |
| `tests/test_health.py` | Added `cpu` to the expected core check ids. |

The existing `/setup` page (a manual, always-available system check linked from the
sidebar) is unchanged.

---

## Consumption — no duplicated logic

| Step | Consumes | Endpoint |
|---|---|---|
| System Scan | System Health Engine | `GET /api/health` |
| Runtime | Health Engine (detection) + Runtime Manager (registered list) | `GET /api/health`, `GET /api/providers` |
| Models | Model Manager (+ Health Engine fallback) | `GET /api/models/catalog` |
| Ready | all three | — |

The wizard performs zero detection itself. Adding "CPU" meant adding one check to
the engine — the single source — not inspecting hardware in the browser.

---

## Known limitations

- **Detection reflects the default/active provider** for "runtime detected" (the
  Health Engine probes the default live). Per-provider online status in the wizard
  would require a Runtime Manager refresh (intentionally avoided to keep the flow
  fast); the Runtime Manager page already does that.
- **Persistence is per-browser** (localStorage). A different browser/profile or a
  cleared store re-shows onboarding — matching the app's existing first-run flag.
- **The health probe can take ~1–2 s** on the System Scan when a local provider is
  down (localhost connect timeout); the wizard shows spinners and polls while on
  the scanning steps.
- **No server-side completion record** — onboarding state is a client concern; the
  backend has no notion of "onboarded".
- **Install steps are links/commands only** — the wizard never installs a runtime
  or pulls a model (by design).
