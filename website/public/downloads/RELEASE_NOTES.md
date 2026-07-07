# RedForge v1.0.0 — Release Notes

**RedForge** is a local AI security laboratory: point it at an Ollama model, run
adversarial evaluations, and get a structured security report — entirely on your
machine. No cloud, no API keys.

## Install in three steps

1. **Get the release** for your OS (or `git clone` for developers).
2. **Install:** `install.cmd` (Windows) or `./install.sh` (Linux/macOS).
   Requires Python 3.11+ and [Ollama](https://ollama.com/download).
3. **Start:** `start.cmd` / `./start.sh` — your browser opens automatically.

Then follow the on-screen setup, pull a model if prompted (`ollama pull qwen3:8b`),
and run your first evaluation.

## What you get
- One-command launch (`redforge start`) — a single process serving everything.
- Guided first-run onboarding with live system checks.
- Evaluation profiles (Quick Scan → Exhaustive), adaptive attacks, and a live terminal.
- Security reports with findings, recommendations, and export (JSON / Markdown / PDF).

## Requirements
- **Python 3.11+** and **Ollama**. Node.js is **not** required to run.

## Known limitations
- macOS: runs from the `.tar.gz`; a signed `.dmg` is planned.
- Windows `.exe` and Linux `AppImage` are produced in CI from the release folder.
- Single-user, localhost-only (no authentication) — by design for local use.
