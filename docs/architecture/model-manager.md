# Model Manager (V1.2)

_Phase: a provider-agnostic Model Manager — browse and manage models across every
provider. Status: implemented. Tests: **317 passed** (was 304); frontend
`tsc --noEmit` clean; `vite build` clean._

The Model Manager is the central place to browse and manage installed models
across all supported providers. It **reuses** the existing model discovery
(`Provider.list_models_raw` / `show_model`) and the shared `RuntimeClient` — no
discovery or runtime logic is duplicated. All provider-specific translation lives
in the backend; the frontend consumes one canonical shape and never learns which
provider a model belongs to.

It does **not** download or install models (a future release).

---

## Architecture

```
Frontend  /models  (ModelManagerPage.tsx)  ← 100% provider-agnostic
  useModelCatalog · getModelDetail (lazy) · useDeleteModel
  search · provider filter (derived from catalog) · sort · cards · detail drawer
        │ axios → /api
        ▼
Backend  app/api/model_manager.py
  GET    /api/models/catalog          basic metadata, grouped by provider
  GET    /api/models/detail           extended metadata (on demand)
  DELETE /api/models/instance         capability-gated deletion
        │ delegates (no discovery/runtime logic here)
        ▼
app/runtime/model_catalog.py  ── ModelCatalog + pure mappers
  · to_basic(...)     native list entry → canonical BASIC shape
  · to_extended(...)  show_model payload → canonical EXTENDED shape
  · catalog()/detail()/delete()  orchestration
        │ reuses only the public runtime surface
        ▼
app/runtime/manager.py (build_provider, registry)   app/runtime/client.py
        │                                             Provider ABC + capabilities()
        ▼                                             RuntimeClient (unchanged)
app/runtime/providers/*   list_models_raw · show_model · delete_model? · capabilities
```

**Two metadata tiers (performance first).** Fast catalog beats complete metadata:

- **Basic** — returned by `/catalog`, from **one** `list_models_raw` call per
  provider. Cheap; no per-model requests.
- **Extended** — returned by `/detail`, from `show_model` (or a richer list
  entry). Fetched **only** when the user opens a model's details — never during a
  catalog refresh, so there are no N extra requests on load.

**Provider-agnostic translation.** Each provider's native shape is normalized by
pure mapper functions in `model_catalog.py`. Ollama's rich `/api/tags` +
`/api/show`, the OpenAI `/v1/models` minimal shape, Anthropic's `display_name`,
and Gemini's `inputTokenLimit` all collapse into the same `ModelInfo`. Absent
fields become `null` — a provider that can't expose something never fails the
request.

---

## API contracts

All additive. Existing `GET /api/models` and `POST /api/models/{model}/ping` are
**unchanged** (backwards compatible).

### `GET /api/models/catalog`
All installed models grouped by provider, with **basic** metadata + health +
capabilities. One list call per provider; providers are probed concurrently and
offline ones return `online:false, models:[]` (never an error for the whole call).

```json
{
  "default": "ollama",
  "total": 3,
  "providers": [
    {
      "provider": "ollama", "label": "Ollama",
      "online": true, "healthy": true, "can_delete": true,
      "capabilities": { "supports_delete": true, "supports_metadata": true,
                        "supports_context_length": true, "supports_streaming": true,
                        "supports_embeddings": false },
      "error": null, "model_count": 2,
      "models": [
        {
          "name": "qwen3:8b", "provider": "ollama", "provider_label": "Ollama",
          "size": 5200000000, "quantization": "Q4_K_M", "family": "qwen",
          "modified_at": "2026-07-01T…", "digest": "sha256:…",
          "status": "available",
          "capabilities": { "supports_delete": true, "…": true }
        }
      ]
    },
    { "provider": "openai", "label": "OpenAI", "online": false,
      "healthy": false, "can_delete": false, "error": null,
      "model_count": 0, "models": [], "capabilities": { "…": false } }
  ]
}
```

Basic model fields: `name, provider, provider_label, size, quantization, family,
modified_at, digest, status, capabilities`. **No extended fields.**

### `GET /api/models/detail?provider={p}&name={n}`
Full **basic + extended** metadata for one model (loaded on demand). Query params
(not path) because model names contain `:` and `/`.
`404` if the provider is unknown, or if it's reachable and has no such model.

```json
{
  "name": "qwen3:8b", "provider": "ollama", "provider_label": "Ollama",
  "size": 5200000000, "quantization": "Q4_K_M", "family": "qwen",
  "modified_at": "…", "digest": "…", "status": "available",
  "capabilities": { "…": true },

  "context_length": 40960, "parameter_count": "8.2B", "architecture": "qwen3",
  "template": "{{ … }}", "license": "Apache-2.0",
  "families": ["qwen3"], "tokenizer": "gpt2",
  "modelfile": "FROM …", "stop_tokens": ["<|im_end|>"],
  "provider_metadata": { … }
}
```

Extended fields degrade to `null`/`[]`/`{}` for providers that can't supply them.

### `DELETE /api/models/instance?provider={p}&name={n}`
Deletes an installed model **iff** the provider's `supports_delete` capability is
true. `200 {"deleted": true, …}`; `400` if the provider can't delete; `404` if the
provider is unknown; upstream failures map to `404/502/503/504`.

---

## Capabilities design

Every provider exposes a lightweight, declarative capabilities object. The
frontend reads it to decide which actions/metadata to show — **provider names are
never hardcoded in the UI**.

```json
{ "supports_delete": true, "supports_metadata": true,
  "supports_context_length": false, "supports_streaming": true,
  "supports_embeddings": false }
```

Implementation: five class attributes on the `Provider` ABC (conservative
defaults) + a `capabilities()` method. Providers override only what differs:

| Provider(s) | delete | metadata | context_length | streaming | embeddings |
|---|---|---|---|---|---|
| Ollama | ✅ | ✅ | ✅ | ✅ | ✗ |
| Gemini | ✗ | ✅ | ✅ | ✅ | ✗ |
| Anthropic | ✗ | ✅ | ✗ | ✅ | ✗ |
| LM Studio / llama.cpp / vLLM / OpenAI / Groq / OpenRouter | ✗ | ✗ | ✗ | ✅ | ✗ |

Capabilities travel with **every** model and provider group, so the UI gates the
Delete button on `supports_delete`, shows the context row only when
`supports_context_length`, and flags "limited metadata" when `!supports_metadata`
— all without knowing a provider's name.

---

## Metadata flow

```
Catalog load
  /catalog → for each provider (concurrent):
      health()  → online?
      list_models_raw()  →  to_basic()  → BASIC ModelInfo  (+capabilities)
  (no show_model, no per-model calls)

Open Details (lazy, one model)
  /detail → find the basic entry in list  +  show_model(name)
      to_extended()  → context_length, parameters, architecture, template,
                       license, families, tokenizer, modelfile, stop_tokens,
                       provider_metadata
  merged BASIC+EXTENDED returned

Delete (capability-gated)
  /instance → provider.supports_delete?  →  provider.delete_model(name)
            → invalidate the default runtime's model cache
```

Key mapper coalescing (provider-agnostic): `size` ← `size`; `modified_at` ←
`modified_at`/`created_at`/unix `created`; `quantization`/`family`/`parameter_count`
← `details.*`; `context_length` ← `model_info.*.context_length` /
`inputTokenLimit`; `stop_tokens` ← parsed from Ollama's `parameters` blob.

---

## Extension points

Adding a future provider (vLLM, OpenAI, Anthropic, Gemini, Groq, OpenRouter, …)
requires **no frontend changes and no Model Manager changes**:

1. Implement/register the provider (already done for all nine) — it inherits the
   default capabilities and the agnostic mappers pick up whatever `list_models_raw`
   / `show_model` expose.
2. Declare richer capabilities by overriding class attributes
   (`supports_metadata = True`, etc.).
3. To surface a native field the mappers don't yet read, add one key to the
   coalescing in `to_basic`/`to_extended` — still a single, provider-agnostic
   spot. The frontend automatically renders it.
4. Deletion: set `supports_deletion = True` and implement `async delete_model()`;
   the Delete affordance appears in the UI by capability alone.

The frontend derives its provider filter from the catalog response, so new
providers show up in search/filter/sort with zero UI edits.

---

## Files

**Backend — new:** `app/runtime/model_catalog.py`, `app/api/model_manager.py`,
`tests/test_model_manager.py`.
**Backend — modified:** `app/runtime/client.py` (capabilities on ABC),
`app/runtime/providers/ollama.py` (caps + `delete_model`),
`app/runtime/providers/openai_compat.py` (`_normalize_models` preserves metadata),
`app/runtime/providers/gemini.py` (caps + rich list),
`app/runtime/providers/anthropic.py` (caps), `app/main.py` (register router).

**Frontend — new:** `src/pages/ModelManagerPage.tsx`.
**Frontend — modified:** `src/api/types.ts`, `src/api/endpoints.ts`,
`src/hooks/queries.ts`, `src/App.tsx`, `src/components/AppShell.tsx`.

---

## Known limitations

- **Ollama context length is lazy.** The catalog omits it (Ollama's list API
  doesn't include it); it's filled in the Details view via `/api/show`. Chosen for
  fast catalog loading (no N requests on refresh).
- **Hosted providers need a valid API key** to appear online; without one the
  provider is offline and contributes no models (by design, not an error).
- **Extended metadata varies widely.** Ollama is rich; OpenAI-compatible servers
  expose little beyond a name. Fields degrade to `null` rather than failing.
- **Deletion is Ollama-only today.** Other providers have no delete API, so the UI
  hides the action for them (capability-gated); `DELETE` returns `400`.
- **No download/install** — out of scope for this phase.
- **Catalog probes providers live** on each refresh; with several unreachable
  local providers configured, a refresh waits on their (bounded) connect timeouts.
- **Model identity is `(provider, name)`.** The same model name under two
  providers is two catalog entries; there is no cross-provider dedup/alias layer.
- **No pagination.** The catalog returns all models; fine for local/hosted list
  sizes today, but very large hosted model lists are returned in full.
