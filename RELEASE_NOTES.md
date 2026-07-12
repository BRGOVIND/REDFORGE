# RedForge v1.2.0 — Release Notes

**RedForge** is a local AI security laboratory: point it at a model, run
adversarial evaluations, and get a structured security report — on your own
machine by default. No cloud and no API keys unless you opt into a cloud provider.

## New in v1.2.0
- **Nine runtime providers** — Ollama (default), LM Studio, llama.cpp, vLLM,
  OpenAI, Anthropic, Gemini, Groq, OpenRouter. Switch from the Runtime page or
  with `REDFORGE_RUNTIME_PROVIDER`. See [docs/providers.md](docs/providers.md).
- **Model Manager** — browse every model across providers, view metadata, and
  delete (where supported), all from one page.
- **System Health Engine** — one source of truth behind `/api/health`,
  `redforge doctor`, onboarding, and startup.
- **Safer by default** — binding to a non-local address now warns that the API
  is unauthenticated before it starts.
- **Reproducible releases** — pinned dependencies, a single VERSION source,
  checksums, and CI. Full details in [CHANGELOG.md](CHANGELOG.md).

## Install in three steps

1. **Get the release** for your OS (or `git clone` for developers).
2. **Install:** `install.cmd` (Windows) or `./install.sh` (Linux/macOS).
   Requires Python 3.11+ and a local runtime — [Ollama](https://ollama.com/download)
   is the recommended default (LM Studio, llama.cpp, and vLLM also work).
3. **Start:** `start.cmd` / `./start.sh` — your browser opens automatically.

Then follow the on-screen setup, pull a model if prompted (`ollama pull qwen3:8b`),
and run your first evaluation.

## What you get
- One-command launch (`redforge start`) — a single process serving everything.
- Guided first-run onboarding with live system checks.
- Evaluation profiles (Quick Scan → Exhaustive), adaptive attacks, and a live terminal.
- Security reports with findings, recommendations, and export (JSON / Markdown / PDF).

## Requirements
- **Python 3.11+** and one local **runtime** — Ollama (recommended), LM Studio,
  llama.cpp, or vLLM. Node.js is **not** required to run.

## Known limitations
- macOS: runs from the `.tar.gz`; a signed `.dmg` is planned.
- Windows `.exe` and Linux `AppImage` are produced in CI from the release folder.
- Single-user, localhost-only (no authentication) — by design for local use.
