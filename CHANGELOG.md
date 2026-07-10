# Changelog

All notable changes to RedForge. This project adheres to
[Semantic Versioning](https://semver.org/).

## [1.2.0]

Multi-provider runtime, model management, a single source of truth for system
health, and a reproducible release pipeline. No breaking API changes — every
V1.0 endpoint keeps its path and response shape.

### Added
- **Multi-provider runtime** — a provider registry with nine built-ins: Ollama
  (default), LM Studio, llama.cpp, vLLM, OpenAI, Anthropic, Gemini, Groq, and
  OpenRouter. Select at startup (`REDFORGE_RUNTIME_PROVIDER`), from the Runtime
  page, or via `POST /api/providers/default`. See [docs/providers.md](docs/providers.md).
- **Runtime Manager** (`/api/providers`) — list, health-probe, live-test, and
  switch the default provider. API keys are read from the environment and never
  stored or logged.
- **Model Manager** (`/api/models/catalog`, `/detail`, `DELETE /instance`) — a
  provider-agnostic catalog with basic + on-demand extended metadata, and
  capability-gated deletion.
- **System Health Engine** (`/api/health`) — one registry of provider-agnostic
  checks, consumed by the API, `redforge doctor`, first-run onboarding, and
  startup logging.
- **First-run onboarding**, rebuilt on the Health Engine.
- **Network-exposure warning** — binding `redforge start` to a non-loopback host
  now prompts a clear no-authentication warning before continuing.
- **Release engineering** — a single source of truth for the version (the
  `VERSION` file), a drift guard (`scripts/version.py --check`), SHA-256
  checksums, GitHub Actions CI, and a tag-driven release workflow. See
  [docs/architecture/release-engineering.md](docs/architecture/release-engineering.md)
  (developer docs; not shipped in the release).

### Changed
- Backend dependencies are now pinned (`requirements.txt` / `requirements.lock`)
  with test tools split into `requirements-dev.txt`, for reproducible installs.
- Startup health validation runs in the background so the server becomes ready
  immediately.
- `GET /api/models` now reports a provider-agnostic offline message.

### Notes
- Default behavior is unchanged: local-only, no authentication, `127.0.0.1`.
  Cloud providers are opt-in and require you to set the relevant API key.

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
