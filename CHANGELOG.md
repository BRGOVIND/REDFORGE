# Changelog

All notable changes to RedForge. This project adheres to
[Semantic Versioning](https://semver.org/).

## [1.0.0] — First public release

The first installable, self-contained release. Runs with **Python + Ollama only**
(no Node.js at runtime); one backend process serves the API and the built UI.

### Added
- **Unified `redforge` CLI** — `install`, `doctor`, `start`, `stop`, `status`,
  `models`, `evaluate`, `benchmark`, `logs`, `update`, `version`.
- **Single-process production mode** — the backend serves the compiled frontend,
  reports, and docs. `redforge start` launches one process and opens the browser.
- **First-run onboarding** with live system checks (Ollama, models, GPU, DB,
  dataset, runtime) and guided fixes.
- **Installers & packaging** — self-contained `.zip`/`.tar.gz` release builder,
  Windows Inno Setup script, and Linux AppImage recipe.
- Persistent evaluation sessions, durable event store, and a live terminal.
- Data-driven evaluation profiles, deterministic planner, and adaptive execution.
- Security analysis with findings, recommendations, and structured reports.
- **Unified LLM runtime** — one client for all model traffic (streaming, queue,
  cancellation, retries, metrics, model cache), provider-agnostic.
- Cross-platform resource detection (Windows / Linux / macOS).

### Notes
- End users need **Python 3.11+** and **Ollama**. Node.js is a development-only
  dependency.
- macOS is supported at the architecture level; a notarized `.dmg` is future work.

[1.0.0]: https://github.com/BRGOVIND/REDFORGE/releases/tag/v1.0.0
