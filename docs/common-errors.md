# Common Errors

Every API error uses one shape:
`{ "success": false, "error": { "code", "message", "details" } }`.

| You see | Meaning | Fix |
|---------|---------|-----|
| `ollama_unavailable` / "Ollama is offline" | Ollama isn't running | `ollama serve` |
| `model_not_found` | the model isn't pulled | `ollama pull <model>` |
| `generation_timeout` | the model took too long | smaller model, or raise `REDFORGE_OLLAMA_TIMEOUT` |
| `provider_unavailable` | Ollama returned an error | check `ollama serve` output |
| Setup shows **No models** | none pulled | `ollama pull qwen3:8b` |
| `redforge start` → port in use | already running / another app on :8000 | `redforge stop`, or `--port 8010` |
| `Python 3.x found — needs ≥ 3.11` | old Python | install Python 3.11+ |
| Frontend not served (only JSON at `/`) | no build present | use a release, or `npm run build` in `frontend/` |
| Evaluation status `failed` | Ollama stopped mid-run | fix Ollama, then Resume the session |

## Reading logs
```bash
redforge logs -n 200
```
Server logs are structured: `TIMESTAMP LEVEL redforge.<area> op=… session=… model=… | message`.

## Still stuck?
Run `redforge doctor --copy` and open an issue with the output at
https://github.com/BRGOVIND/REDFORGE/issues.
