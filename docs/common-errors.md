# Common Errors

Every API error uses one shape:
`{ "success": false, "error": { "code", "message", "details" } }`.

RedForge runs models through a runtime provider — Ollama (the recommended
default), LM Studio, llama.cpp, or vLLM. The examples below use Ollama; with
another runtime, the equivalent step is start/configure that runtime.

| You see | Meaning | Fix |
|---------|---------|-----|
| `provider_unavailable` / "runtime provider is offline" | your runtime isn't running or reachable | start your runtime (Ollama: `ollama serve`); check the **Runtime** page |
| `model_not_found` | the model isn't installed in your runtime | add a model (Ollama: `ollama pull <model>`), or let onboarding download one |
| `generation_timeout` | the model took too long | use a smaller model, or raise the runtime read timeout |
| Setup shows **No models** | none installed | add a model to your runtime, or let onboarding download one |
| `redforge start` → port in use | already running / another app on :8000 | `redforge stop`, or `--port 8010` |
| `Python 3.x found — needs ≥ 3.11` | old Python | install Python 3.11+ |
| Frontend not served (only JSON at `/`) | no build present | use a release, or `npm run build` in `frontend/` |
| Evaluation status `failed` | the runtime stopped mid-run | fix the runtime, then Resume the session |

## Reading logs
```bash
redforge logs -n 200
```
Server logs are structured: `TIMESTAMP LEVEL redforge.<area> op=… session=… model=… | message`.

## Still stuck?
Run `redforge doctor --copy` and open an issue with the output at
https://github.com/BRGOVIND/REDFORGE/issues.
