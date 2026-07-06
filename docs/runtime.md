# Runtime Architecture

The **runtime** is the single layer through which every RedForge feature talks to
a language model. Nothing else imports `httpx` or knows about Ollama — evaluation,
benchmarking, the judge, mutations, the agent, profiling, and the models/health
endpoints all go through one client.

```
app/runtime/
├── manager.py    get_runtime() — the shared client; provider chosen from config
├── client.py     Provider (ABC) + OllamaProvider + RuntimeClient
├── stream.py     token streaming engine (with graceful fallback)
├── queue.py      per-model concurrency limiter
├── cancel.py     one CancellationToken + CancelRegistry for the whole app
├── metrics.py    process-wide counters (→ GET /api/runtime/status)
├── models.py     TTL cache for /api/tags and /api/show
├── responses.py  GenerationResult + StreamEvent
└── errors.py     runtime exceptions (no raw httpx escapes)
```

---

## Flow

```
 feature ──▶ get_runtime().generate(model, prompt)
                     │
        ┌────────────┴─────────────────────────────────────────┐
        │ RuntimeClient                                         │
        │  metrics.start → queue.slot(model) → [retry loop]     │
        │     await provider.generate  ⨯ race(cancel, timeout)  │
        │  → metrics.complete/fail/cancel → log                 │
        └────────────┬─────────────────────────────────────────┘
                     ▼
              Provider (OllamaProvider today)
                     ▼
              httpx → Ollama  (only place httpx lives)
```

Every transport error from the provider is mapped to a runtime exception, so no
raw `httpx` error ever reaches a feature.

---

## Client API

`RuntimeClient` (via `get_runtime()`):

| Method | Purpose |
|--------|---------|
| `generate(model, prompt, *, timeout, cancel_token, request_id, retries)` | one-shot generation → `GenerationResult` |
| `generate_stream(model, prompt, *, cancel_token, request_id)` | async `StreamEvent` iterator |
| `health()` | provider reachable? (fresh, uncached) |
| `list_models()` / `list_models_raw(use_cache=…)` | model names / native entries (cached) |
| `show_model(model)` | model metadata (cached) |
| `cancel(request_id)` | cancel an in-flight request by id |
| `invalidate_cache(model=None)` | drop cached tags/show |

`GenerationResult`: `model`, `text`, `latency_ms`, `eval_count`, `tokens_per_sec`.

---

## Streaming

`generate_stream` yields `StreamEvent`s — `token` → … → `completion` — so
consumers never parse NDJSON or manage partial state:

```python
async for ev in runtime.generate_stream(model, prompt):
    if ev.kind == "token":       ...ev.token / ev.text (accumulated)
    elif ev.kind == "completion": ...ev.result
    elif ev.kind == "cancelled":  ...
    elif ev.kind == "error":      ...ev.error
```

**Graceful fallback:** if streaming is unavailable or fails *before any token*,
the engine falls back to a single non-streamed `generate` and emits one
`completion` — the consumer sees a normal result either way.

---

## Queue

Local models can't serve many generations at once, so the runtime serializes
work **per model** (`asyncio.Semaphore`, default concurrency **1**, via
`REDFORGE_RUNTIME_CONCURRENCY`). Different models run in parallel; each model is
protected from being hammered. `metrics.queue_length` reflects waiters.

---

## Cancellation

One primitive everywhere: `CancellationToken` (awaitable + pollable). A generation
races the token, so cancellation is immediate at the boundary. `CancelRegistry`
maps `request_id → token`, so `runtime.cancel(request_id)` stops an in-flight
request from anywhere (an endpoint, a supervisor). Evaluation, benchmark, judge,
mutation, and the agent all use this — no per-feature cancellation code.

---

## Timeouts (all in `app/config.py`)

| Setting | Meaning |
|---------|---------|
| `OLLAMA_TIMEOUT` | generation read timeout |
| `RUNTIME_CONNECT_TIMEOUT` | connection timeout |
| `OLLAMA_HEALTH_TIMEOUT` | health check timeout |
| `OLLAMA_TAGS_TIMEOUT` / `OLLAMA_SHOW_TIMEOUT` | metadata timeouts |
| `RUNTIME_RETRY_COUNT` / `RUNTIME_RETRY_BACKOFF` | retry policy (connection failures only) |
| `MODEL_CACHE_TTL` | tags/show cache lifetime |

Timeouts raise `GenerationTimeout`; transient connection failures are retried up
to `RUNTIME_RETRY_COUNT` with linear backoff; cancellations are never retried.

---

## Metrics — `GET /api/runtime/status`

```jsonc
{
  "provider": "ollama",
  "concurrency_per_model": 1,
  "metrics": {
    "active_requests", "queue_length", "total_requests",
    "completed_requests", "failed_requests", "cancelled_requests",
    "retry_count", "avg_latency_ms", "avg_tokens_per_sec"
  }
}
```

---

## Errors

All in `app/runtime/errors.py`, each with a stable `code` and `http_status`:
`ProviderUnavailable` / `OllamaUnavailable`, `ConnectionFailure`, `ModelNotFound`,
`GenerationTimeout`, `CancelledGeneration`, `StreamingFailure`. Endpoints map
these to the standard API error envelope.

---

## Model cache

`/api/tags` and `/api/show` results are cached for `MODEL_CACHE_TTL` seconds to
avoid hammering the provider on every dashboard/profiler call. Pass
`use_cache=False` for freshness (the setup wizard does this so it reacts the
instant Ollama starts or a model is pulled), or call `invalidate_cache()` after a
pull.

---

## Adding a provider (future-ready)

The rest of RedForge doesn't care which server runs the model. To add
**LM Studio / llama.cpp / vLLM / an OpenAI-compatible API**:

1. Implement a `Provider` subclass (`generate`, `stream_generate`,
   `list_models_raw`, `show_model`, `health`) that maps its transport errors to
   `app.runtime.errors`.
2. Register it in `manager._build_provider()` keyed by `REDFORGE_RUNTIME_PROVIDER`.

Everything above the provider — queue, cancellation, retries, timeouts, metrics,
cache, logging, streaming — is reused unchanged.

```
                     ┌── OllamaProvider   (today)
 RuntimeClient ──────┼── LMStudioProvider (future)
 (queue, cancel,     ├── LlamaCppProvider (future)
  retry, metrics,    ├── VLLMProvider     (future)
  cache, stream)     └── OpenAICompatible (future)
```
