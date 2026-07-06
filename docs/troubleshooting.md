# Troubleshooting

Start here:

```bash
redforge doctor --copy
```

This prints a copyable green/yellow/red report of everything RedForge needs.

## The browser didn't open
- Open `http://127.0.0.1:8000` manually.
- Already running elsewhere? `redforge status`. Start on another port:
  `redforge start --port 8010`.

## "RedForge failed to start"
- Check the logs: `redforge logs` (or `redforge logs -n 200`).
- Port in use? `redforge stop`, then `redforge start`.
- Dependencies missing? `redforge install`.

## Ollama problems
- **Not installed:** https://ollama.com/download
- **Not running:** `ollama serve` (Linux may also use `systemctl start ollama`).
- **Unreachable:** confirm it's on `http://localhost:11434` (open it in a browser).

## No models
```bash
ollama pull qwen3:8b
```
Then re-run the setup — the check flips green automatically.

## Evaluation ends as "failed"
Usually Ollama stopped or the model isn't pulled. Check `redforge doctor`, pull
the model, and resume from the session (Live page → Resume) or start again.

## Slow evaluations
- No GPU → inference runs on CPU (much slower). See [GPU support](gpu-support.md).
- Use a smaller model or the **Quick Scan** profile.
- The runtime serializes calls per model by default; that's intentional.

## Reset
- Stop everything: `redforge stop`.
- The database is `backend/redforge.db`; deleting it resets history (it's recreated
  on next start).
