# Runtime Providers

RedForge talks to language models through **runtime providers**. Ollama is the
default and needs no configuration. The default strict profile permits only
loopback local providers. Hosted adapters remain in the code but require an
explicit, separately configured connected deployment. See
[network profiles](network-profile.md).

## Choosing a provider

Set `REDFORGE_RUNTIME_PROVIDER` to one of the built-in provider keys:

| Key | Provider | Runs where | API key |
|-----|----------|-----------|---------|
| `ollama` | Ollama (default) | Local | none |
| `lmstudio` | LM Studio | Local | none |
| `llamacpp` | llama.cpp server | Local | none |
| `vllm` | vLLM | Loopback in strict mode | none |
| `openai` | OpenAI | Cloud | `OPENAI_API_KEY` |
| `anthropic` | Anthropic (Claude) | Cloud | `ANTHROPIC_API_KEY` |
| `gemini` | Google Gemini | Cloud | `GEMINI_API_KEY` |
| `groq` | Groq | Cloud | `GROQ_API_KEY` |
| `openrouter` | OpenRouter | Cloud | `OPENROUTER_API_KEY` |

In strict mode the five hosted adapters in the table are unavailable and local
provider URLs must resolve to loopback. You can switch between permitted
providers from the **Runtime** page or with `POST /api/providers/default`.

## Configuration conventions

Every provider follows the same two conventions, so nothing in RedForge needs to
change when you switch:

- **Base URL** — `REDFORGE_<KEY>_URL` (e.g. `REDFORGE_OLLAMA_URL`,
  `REDFORGE_LMSTUDIO_URL`). Local providers default to their standard port.
- **API key** — read from the provider's standard environment variable (the
  `API key` column above). Local providers need none.

RedForge never stores API keys. They are read from the environment at runtime and
are never written to logs, reports, or the database. The API only ever reports
whether a key is *present*, never its value.

### Examples

Local LM Studio (default port):

```bash
REDFORGE_RUNTIME_PROVIDER=lmstudio redforge start
```

OpenAI, in a separate connected deployment only:

```bash
export OPENAI_API_KEY=sk-...
export REDFORGE_NETWORK_PROFILE=connected
REDFORGE_RUNTIME_PROVIDER=openai redforge start
```

Custom Ollama host, in a connected deployment only:

```bash
export REDFORGE_OLLAMA_URL=http://192.168.1.50:11434
export REDFORGE_NETWORK_PROFILE=connected
redforge start
```

## Model management

The **Models** page lists every model across all configured providers. Provider
capabilities differ:

- **Deletion** is supported where the provider exposes it (e.g. Ollama). The UI
  only shows a delete action for providers that support it.
- **Extended metadata** (context length, quantization, license, template) is
  shown when the provider reports it; missing fields are simply omitted.

## Health and troubleshooting

- The **Runtime** page shows each provider's health, version, latency, and model
  count. Use *Test* to probe one provider live.
- `redforge doctor` runs the same System Health Engine and reports provider
  status from the command line.
- A provider marked *offline* usually means the local server isn't running
  (start Ollama / LM Studio). In connected mode it can also mean a missing
  hosted API key. See
  [troubleshooting.md](troubleshooting.md).
