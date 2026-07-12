# First-Run Experience & Live Terminal

Sprint 5 is purely about **usability** — no landing-page or dashboard redesign.
It answers two questions for a new user:

1. *"I just downloaded RedForge — what do I need to do?"* → a first-run **setup
   wizard** with live system checks.
2. *"Is it actually doing anything right now?"* → a real, streaming **terminal**
   on the evaluation page. No silent waiting.

---

## Part 1 — First-run setup

### Endpoint

`GET /api/system/checks` (`app/api/system.py`) returns, cross-platform and fast
(short Ollama timeout so it can be polled):

The checks report the **active runtime provider** (via the Runtime Manager), so
switching providers switches what is reported and how to fix it — nothing here
assumes Ollama.

```jsonc
{
  "ready": false,
  "platform": "Windows",
  "provider": {
    "name": "ollama", "label": "Ollama", "base_url": "http://localhost:11434",
    "reachable": false, "requires_api_key": false, "api_key_present": false,
    "supports_pull": true, "docs_url": "https://ollama.com/download",
    "setup_hint": "Start Ollama with: ollama serve"
  },
  "checks": [
    { "key": "runtime_running", "label": "Runtime Provider", "status": "failed",  "detail": "Ollama not reachable…", "hint": "Start Ollama with: ollama serve" },
    { "key": "gpu",             "label": "GPU Detected",     "status": "ok",      "detail": "NVIDIA RTX 4060" },
    { "key": "database",        "label": "Database Ready",   "status": "ok" },
    { "key": "dataset",         "label": "Dataset Loaded",   "status": "ok",      "detail": "28 attacks · 800 benchmark cases" },
    { "key": "models",          "label": "Models Available", "status": "failed",  "detail": "no models available yet" }
  ],
  "installed_models": [],
  "recommended_models": ["llama3.2:3b", "llama3.1:8b", "mistral:7b", "qwen2.5:7b"]
}
```

- **Runtime Provider** — the active provider's `health()` (via `get_runtime()`);
  the fix (`setup_hint`) and links (`docs_url`) come from the provider class, so
  they are correct whether the provider is Ollama, LM Studio, llama.cpp, or vLLM.
  Cloud providers report "API key not set" when their key is missing.
- **Models Available** — `runtime.list_models()` on the active provider;
  `warning` if none while reachable, `failed` if the provider is unreachable.
- **GPU** — `resource_monitor.detect_gpu()` (NVIDIA / Apple Metal); advisory only.
- **Database** — a live `COUNT` against the attack table.
- **Dataset** — attack library seeded **and** RedForge-Bench-V1 loads.

`recommended_models` is populated only for providers that can download models
(`supports_pull`). `ready` is `true` only when the blocking checks
(`runtime_running`, `database`, `dataset`, `models`) are all `ok`; GPU is advisory.

### The wizard (`frontend/src/pages/SetupPage.tsx`, route `/setup`)

- Polls `useSystemChecks()` every 2.5s, so each row animates **○ waiting →
  ✓ success / ⚠ warning / ✕ failed** as the user fixes things (start the runtime,
  add a model) — no refresh needed.
- Renders context-sensitive guidance driven by the **active provider** (its
  `setup_hint` / `docs_url` come from the provider class, never hardcoded):
  - Runtime not reachable → **Set up `<provider>`** with the provider's start
    hint (e.g. `ollama serve`) and a docs/download link. Cloud providers instead
    prompt to set their API key.
  - No models, provider supports downloads → recommended models with a copy
    button; providers without a pull API show import guidance instead.
- When everything is green → **System Ready · Launch RedForge**.

**First launch** is detected with a `redforge_launched` localStorage flag: the app
redirects to `/setup` on the very first visit, and the sidebar status pill always
links back to it ("Setup required" when the backend is offline).

---

## Part 2/3 — Backend terminal events (no fake logs)

The terminal is **derived from real events** — nothing is fabricated.
`app/sessions/terminal.py` is the single source of truth: `event_to_line(event)`
renders each persisted `EvaluationEvent` into a `{ id, ts, level, text }` line.

| Event | Terminal line | Level → color |
|-------|---------------|---------------|
| `session_created` | `Loading profile "…"` | system → blue |
| `model_profiled` | `Detected model — …` | system |
| `plan_generated` | `Planning evaluation… ready (N attacks)` | system |
| `attack_started` | `Running Prompt Injection — attack 7/150` | info → gray |
| `response_received` | `Response received · 4200 ms` | info |
| `verdict_generated` (PASS) | `Verdict PASS — …` | success → green |
| `verdict_generated` (FAIL) | `Verdict FAIL — unsafe · …` | failure → red |
| `mutation_applied` / `attack_retried` | `Retrying with mutation (…)` | warning → yellow |
| `heartbeat` | `still running…` | info |
| `report_generated` | `Report generated — security score 72` | system |
| `session_completed` / `session_failed` | terminal status | success / failure |

### Heartbeats (Part 5 — never frozen)

`AdaptiveExecutor._generate_with_heartbeat` runs a background task that emits a
`heartbeat` event every `HEARTBEAT_INTERVAL` (4s) **only while a real attack is
waiting on a slow model** (`Waiting for model response…` → `still running…` →
`token generation…`). Fast responses cancel the beat before it fires, so nothing
noisy appears — and the existing tests (fast fake generators) are unaffected.

---

## Part 4 — Terminal API

`GET /api/sessions/{id}/terminal?after_id=N` reuses the **event cursor**:

```jsonc
{ "session_id": "…", "status": "running", "cursor": 142, "lines": [ { "id", "ts", "level", "text" } ] }
```

Pass the returned `cursor` back as `after_id` to receive only new lines — history
is never re-fetched. `frontend/src/hooks/useTerminalStream.ts` polls this and is
WebSocket-ready: swap the poll for a socket and the `Terminal` panel is unchanged.

### The panel (`frontend/src/components/Terminal.tsx`)

Black background, monospace, timestamped, color-coded, auto-scrolling — added
**below the existing Event Feed** on the Live page (the feed is untouched;
heartbeats are filtered out of it and shown only in the terminal). Controls:
**pause auto-scroll**, **copy logs**, **download logs** (`.log`), **clear view**.
Windowed to the last 500 lines so long runs never bloat the DOM.

---

## Guarantees

- **No backend regressions** — all 233 backend tests pass (16 new).
- **Frontend build clean** — typecheck + build green.
- **Cross-platform** — `shutil.which`, platform-specific start hints, and GPU
  detection all branch on `platform.system()`.
- **No landing page or dashboard redesign.**
