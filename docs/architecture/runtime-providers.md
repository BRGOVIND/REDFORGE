# Runtime Providers — Multi-Provider Architecture (V1.2)

_Phase: extend the unified runtime from Ollama-only to a provider system that
scales to 9+ backends. Status: implemented. Tests: **293 passed** (was 260)._

RedForge routes **all** model traffic through one runtime engine. This phase
generalizes the provider layer so a new backend is a small class + one line of
registration — **no engine changes**. The shared concerns (queue, retries,
metrics, cancellation, streaming assembly) live in `RuntimeClient` and are never
duplicated in a provider.

---

## Architecture

```
                 ┌─────────────────────────────────────────────┐
  feature code   │ RuntimeClient  (app/runtime/client.py)       │  ← the "manager"
  get_runtime()  │  owns: queue · retries · metrics ·           │    (shared logic
  ────────────►  │        cancellation · model cache · logging  │     lives ONLY here)
                 │  streaming assembly → app/runtime/stream.py   │
                 └───────────────────────┬─────────────────────┘
                                         │ delegates transport only
                                         ▼
                 Provider (ABC)  app/runtime/client.py
                 generate · stream_generate · health ·
                 list_models(_raw) · show_model
                                         │
        ┌────────────────────────────────┼───────────────────────────────┐
        ▼                                 ▼                               ▼
  OllamaProvider            HttpProvider (base.py)                 (future families)
  providers/ollama.py       base URL + API key + headers +
  native /api/*             error mapping + key-gated health
                                         │
             ┌───────────────────────────┼─────────────────────────┐
             ▼                            ▼                          ▼
  OpenAICompatibleProvider      AnthropicProvider          GeminiProvider
  providers/openai_compat.py    providers/anthropic.py     providers/gemini.py
  /v1/chat/completions          /v1/messages               :generateContent
   ├─ LMStudioProvider          x-api-key + version         x-goog-api-key
   ├─ LlamaCppProvider          own SSE event protocol      own SSE (alt=sse)
   ├─ VLLMProvider
   ├─ OpenAIProvider
   ├─ GroqProvider
   └─ OpenRouterProvider
```

**Selection** is config-driven. `REDFORGE_RUNTIME_PROVIDER` names a key in the
registry (`app/runtime/providers/__init__.py::BUILTIN_PROVIDERS`), seeded into
`app/runtime/manager.py::_PROVIDERS`. `get_runtime()` builds the chosen provider
once and wraps it in `RuntimeClient`.

**Why families.** The 9 targets are only **3 wire formats plus Ollama**. Six of
them (LM Studio, llama.cpp, vLLM, OpenAI, Groq, OpenRouter) speak OpenAI Chat
Completions, so they share one base and differ only in base URL / auth — each is
~5 lines. Anthropic and Gemini get their own subclass because their request,
response, and SSE shapes genuinely differ. All three families reuse the same
`HttpProvider` plumbing (URL/key resolution, headers, error mapping, health).

**Streaming.** Every provider's `stream_generate` yields chunk dicts shaped like
Ollama's — `{"response": <delta>, "done": <bool>, "eval_count"?, "done_reason"?}`
— so `app/runtime/stream.py::run_stream` assembles tokens → completion uniformly,
with graceful fallback to non-streamed `generate` unchanged. The OpenAI, Anthropic,
and Gemini SSE dialects are each translated into this shape by the provider.

**Error handling.** No raw `httpx` exception escapes a provider. All map through
`app/runtime/transport.py::map_transport_error` (one implementation, shared by
Ollama and `HttpProvider`), so `ConnectError → ProviderUnavailable`,
`Timeout → ConnectionFailure`, `404 → ModelNotFound`, etc., are identical
regardless of backend — and retries/metrics keyed on those codes keep working.

---

## Files modified

| File | Change |
|---|---|
| `app/runtime/client.py` | Removed `OllamaProvider` (moved to package). Kept the `Provider` ABC + `RuntimeClient`; expanded the ABC docstring to state the "communication only" contract. Pruned now-unused imports. **No change to `RuntimeClient` behavior.** |
| `app/runtime/manager.py` | Registry now seeded from `BUILTIN_PROVIDERS` (`dict(BUILTIN_PROVIDERS)`); selection logic unchanged. `register_provider` / `available_providers` retained. |
| `app/config.py` | Removed the two provider-specific base-URL settings added in the prior step (providers now own their config by convention). Added provider-agnostic `RUNTIME_READ_TIMEOUT` and `RUNTIME_METADATA_TIMEOUT`. Updated `RUNTIME_PROVIDER` doc to list all built-ins. |
| `tests/test_providers.py` | Rewritten/expanded to 33 tests: OpenAI family, Anthropic, Gemini, auth-gating, error mapping, and the full 9-provider registry & selection. |

**New files**

| File | Purpose |
|---|---|
| `app/runtime/transport.py` | `map_transport_error()` — shared httpx→runtime error mapping (added the prior step; unchanged here). |
| `app/runtime/providers/__init__.py` | Package root: imports every provider, defines `BUILTIN_PROVIDERS`, re-exports classes + wire helpers. **The one registration point.** |
| `app/runtime/providers/base.py` | `HttpProvider` — shared HTTP plumbing (base-URL/API-key convention, headers, error mapping, key-gated health). |
| `app/runtime/providers/ollama.py` | `OllamaProvider` (moved verbatim; native `/api/*`). |
| `app/runtime/providers/openai_compat.py` | `OpenAICompatibleProvider` base + `LMStudio`, `LlamaCpp`, `VLLM`, `OpenAI`, `Groq`, `OpenRouter`; wire helpers `_parse_chat_completion`, `_parse_sse_line`, `_normalize_models`. |
| `app/runtime/providers/anthropic.py` | `AnthropicProvider` (Messages API + its SSE protocol). |
| `app/runtime/providers/gemini.py` | `GeminiProvider` (`generateContent` + `alt=sse`). |

---

## Architecture changes

- `providers.py` (flat module) → `app/runtime/providers/` **package**.
- `OllamaProvider` relocated from `client.py` into the package; `client.py` is now
  strictly *engine + abstraction*.
- New `HttpProvider` base carves out the HTTP concerns shared across families.
- Provider **config is owned by the provider** (env convention), so adding one
  needs **no `config.py` edit** — a prerequisite for "no runtime modifications".
- Registry seeded from a single `BUILTIN_PROVIDERS` map.

No public HTTP API contracts changed. `/api/runtime/status`, `/api/models`,
`/api/models/{m}/ping`, evaluation, and streaming all behave as before; default
provider remains `ollama`.

---

## Public APIs added

Stable, intended for use by app code / future extensions.

| Symbol | Location | Description |
|---|---|---|
| `HttpProvider` | `app.runtime.providers` | Base class for HTTP providers (subclass for a new family). |
| `OpenAICompatibleProvider` | `app.runtime.providers` | Base for any OpenAI Chat Completions backend. |
| `OllamaProvider`, `LMStudioProvider`, `LlamaCppProvider`, `VLLMProvider`, `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider`, `GroqProvider`, `OpenRouterProvider` | `app.runtime.providers` | Concrete built-in providers. |
| `BUILTIN_PROVIDERS: dict[str, type[Provider]]` | `app.runtime.providers` | The built-in name→class registry. |
| `register_provider(name, factory)` | `app.runtime.manager` | Register/override a provider at runtime (`factory` = class or any zero-arg callable returning a `Provider`). |
| `available_providers() -> list[str]` | `app.runtime.manager` | Sorted list of registered provider names. |
| `get_runtime()` / `set_runtime()` / `reset_runtime()` | `app.runtime.manager` | Unchanged; the runtime accessor (`set_runtime` used by tests). |

---

## Internal APIs added

Not part of the stable surface; may change.

| Symbol | Location | Description |
|---|---|---|
| `HttpProvider._env_base_url` / `_env_api_key` | `providers/base.py` | Convention-based config resolution. |
| `HttpProvider._auth_headers` / `_headers` / `_client` / `_ensure_ready` / `_map_error` / `_probe_health` | `providers/base.py` | Overridable plumbing hooks. |
| `_parse_chat_completion`, `_parse_sse_line`, `_normalize_models` | `providers/openai_compat.py` | OpenAI wire translation (pure functions). |
| `_parse_gemini_chunk` | `providers/gemini.py` | Gemini response/stream translation. |
| `manager._PROVIDERS`, `manager.ProviderFactory` | `manager.py` | The mutable registry + its type alias. |

---

## New environment variables

**Selection & timeouts**

| Variable | Default | Meaning |
|---|---|---|
| `REDFORGE_RUNTIME_PROVIDER` | `ollama` | Which provider to use (any registry key). |
| `REDFORGE_RUNTIME_READ_TIMEOUT` | `120.0` | Read timeout (s) for generation on non-Ollama providers. |
| `REDFORGE_RUNTIME_METADATA_TIMEOUT` | `10.0` | Timeout (s) for health / model-list on non-Ollama providers. |

**Per-provider base URL** — convention `REDFORGE_<NAME>_URL` (name = provider key, uppercased). All optional; defaults shown.

| Provider | Base-URL var | Default | API-key var |
|---|---|---|---|
| ollama | `REDFORGE_OLLAMA_URL` | `http://localhost:11434` | — |
| lmstudio | `REDFORGE_LMSTUDIO_URL` | `http://localhost:1234` | — |
| llamacpp | `REDFORGE_LLAMACPP_URL` | `http://localhost:8080` | — |
| vllm | `REDFORGE_VLLM_URL` | `http://localhost:8000` | — |
| openai | `REDFORGE_OPENAI_URL` | `https://api.openai.com` | `OPENAI_API_KEY` |
| anthropic | `REDFORGE_ANTHROPIC_URL` | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` |
| gemini | `REDFORGE_GEMINI_URL` | `https://generativelanguage.googleapis.com` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) |
| groq | `REDFORGE_GROQ_URL` | `https://api.groq.com/openai` | `GROQ_API_KEY` |
| openrouter | `REDFORGE_OPENROUTER_URL` | `https://openrouter.ai/api` | `OPENROUTER_API_KEY` |

API-key vars use each vendor's standard name (so existing shell env just works).
Extra: `REDFORGE_ANTHROPIC_MAX_TOKENS` (default `1024`) — Anthropic requires `max_tokens`.

Example:
```bash
REDFORGE_RUNTIME_PROVIDER=openai   OPENAI_API_KEY=sk-...      redforge start
REDFORGE_RUNTIME_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant- redforge start
REDFORGE_RUNTIME_PROVIDER=llamacpp  REDFORGE_LLAMACPP_URL=http://192.168.1.9:8080 redforge start
```

---

## Migration notes

- **Backwards compatible.** Default provider is still `ollama`; with no new env
  vars set, behavior is identical to v1.0. `OllamaProvider` logic is unchanged.
- **`config.settings.LMSTUDIO_BASE_URL` / `LLAMACPP_BASE_URL` were removed.** They
  were introduced earlier in this development cycle and never shipped in a
  release. The **env vars** `REDFORGE_LMSTUDIO_URL` / `REDFORGE_LLAMACPP_URL`
  still work (now via the base-URL convention), so no user-facing change.
- **Import move:** `OllamaProvider` now lives in `app.runtime.providers`
  (re-exported there) instead of `app.runtime.client`. Only `manager.py`
  imported it internally; updated. Import from `app.runtime.providers` going
  forward.
- No database, API-contract, or frontend changes. No schema migration.

---

## Future extension points

1. **Add a provider in an existing family** — subclass + register (see below).
2. **Add a new wire format** — subclass `HttpProvider` (or `Provider` directly),
   implement `generate` / `stream_generate` / `list_models_raw` / `show_model` /
   `_probe_health`, then register. The engine is untouched.
3. **Runtime registration** — `register_provider("name", Cls)` from anywhere
   (e.g. a plugin, a test) without editing built-ins.
4. **Health/status surfacing** — `runtime.provider.name` already flows to
   `/api/runtime/status`; a future step can add per-provider readiness to
   `/api/system/checks` and `redforge doctor`.
5. **Per-request provider override** — today selection is global via config; a
   future enhancement could let a session choose its provider (the abstraction
   already supports constructing any provider on demand).

### How to add a future provider

**Case A — OpenAI-compatible (Together, Fireworks, DeepSeek, a remote vLLM, …):**

```python
# app/runtime/providers/openai_compat.py
class TogetherProvider(OpenAICompatibleProvider):
    name = "together"
    label = "Together"
    default_base_url = "https://api.together.xyz"
    api_key_env = "TOGETHER_API_KEY"
```
```python
# app/runtime/providers/__init__.py  → add one line to BUILTIN_PROVIDERS
TogetherProvider.name: TogetherProvider,
```
Then `REDFORGE_RUNTIME_PROVIDER=together TOGETHER_API_KEY=... redforge start`.
That's it — no engine, manager, or config changes.

**Case B — a brand-new wire format:**

```python
# app/runtime/providers/acme.py
class AcmeProvider(HttpProvider):
    name = "acme"
    label = "Acme"
    default_base_url = "https://api.acme.ai"
    api_key_env = "ACME_API_KEY"

    def _auth_headers(self):
        return {"Authorization": f"Token {self.api_key}"}

    async def generate(self, model, prompt) -> GenerationResult: ...
    async def stream_generate(self, model, prompt):  # yield {"response","done",...}
        ...
    async def _probe_health(self) -> bool: ...
    async def list_models_raw(self) -> list[dict]: ...   # each {"name": ...}
    async def show_model(self, model): ...
```
Register in `BUILTIN_PROVIDERS`. Reuse `_normalize_models` if the model list is
OpenAI-shaped; otherwise map to `{"name": ...}` yourself.

**The rule:** implement provider-specific communication only. Never add
queue/retry/metrics/cancellation code to a provider — that lives in
`RuntimeClient` and applies to every provider for free.

---

## Known limitations

- **vLLM auth:** treated as keyless (local default). A vLLM launched with
  `--api-key` isn't supported by the built-in `VLLMProvider` yet; run a thin
  subclass with `api_key_env` set, or use `OpenAIProvider` pointed at it.
- **`show_model` is best-effort** for the OpenAI/Anthropic/Gemini families (their
  APIs expose little per-model metadata) — it returns the `list_models` entry or
  `None`, unlike Ollama's rich `/api/show`.
- **Model-name conventions differ** per provider (e.g. `gpt-4o-mini`,
  `claude-3-5-sonnet-latest`, `gemini-1.5-flash`). Gemini's `models/` prefix is
  stripped; otherwise names are passed through verbatim. No cross-provider alias
  layer exists.
- **Selection is process-global**, chosen at startup via config. No per-session
  or per-request provider switching yet (see extension point #5).
- **Cloud providers can't be integration-tested against real endpoints** in CI
  (they need keys); coverage uses mocked transports that assert the exact wire
  translation. Live smoke-testing requires real credentials.
- **Rate limits / provider-specific errors** beyond HTTP status are not
  specially handled (e.g. OpenAI 429 maps to the generic retryable path via the
  shared mapper, which is correct but not tuned per vendor).
- **Streaming token accuracy** depends on each provider emitting usage; when a
  provider omits token counts, `eval_count`/`tokens_per_sec` are `None` (metrics
  still record latency).
