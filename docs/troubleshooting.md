# Troubleshooting

Start with a health check — it diagnoses most problems and suggests a fix:

```bash
redforge doctor
```

For a shareable report of your whole setup:

```bash
redforge diagnose      # writes diagnostics.zip (no secrets included)
```

## Installation

**`redforge install` fails while installing dependencies.**
Check your network connection and re-run `redforge repair`. A failed fresh
install rolls back its virtual environment automatically, so nothing is left
half-installed.

**"Python 3.11+ required."**
RedForge needs Python 3.11 or newer. Install a supported version and re-run
`redforge install`.

**"Backend requirements not found."**
You installed the CLI (via pip) but there is no backend to install against.
Download a release, or run from a checkout. See [installation.md](installation.md).

## Starting

**"Port 8000 is already in use."**
Another process (possibly a previous RedForge) is using the port. Stop it with
`redforge stop`, or start on another port: `redforge start --port 8100`.

**The browser doesn't open.**
Start with `redforge start --no-browser` and open `http://127.0.0.1:8000`
manually, or check the log path printed on startup.

**The backend fails to start.**
Run `redforge doctor`. Common causes are a missing dependency
(`redforge repair`), a locked database, or insufficient permissions in the data
directory.

## Runtime & models

**"The runtime provider is offline."**
Your runtime isn't running or isn't reachable. For Ollama, run `ollama serve`.
Confirm the base URL matches `REDFORGE_OLLAMA_URL` (default
`http://localhost:11434`). Use the **Runtime** page or `redforge doctor` to test.

**No models are found.**
Pull at least one model — `ollama pull llama3.1:8b`, or use RedForge's onboarding
to download a recommended model. Confirm with `redforge models`.

**A model download stalls or fails.**
Downloads run through your runtime (e.g. Ollama's pull). Check disk space and
that the runtime is running; retry from onboarding or `ollama pull <model>`.

**Evaluations are very slow.**
Without a GPU, inference runs on CPU and is much slower. Choose a smaller model
(onboarding recommends models that fit your hardware) or a lighter profile.
`redforge doctor` reports GPU/VRAM detection.

## Cloud providers

**"API key not set."**
Cloud providers (OpenAI, Anthropic, Gemini, Groq, OpenRouter) need their standard
API-key environment variable set before you start RedForge. See
[providers.md](providers.md).

## Still stuck?

Run `redforge diagnose` and attach `diagnostics.zip` to your report — it contains
everything needed to debug the issue and no secrets. See the
[FAQ](faq.md) for common questions.
