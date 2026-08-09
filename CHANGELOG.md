# Changelog

All notable changes to RedForge. This project adheres to
[Semantic Versioning](https://semver.org/).

## [2.0.4]

A fix-only release. Upgrading from 2.0.3 could leave the app unable to open
pages; this release fixes that and prevents the whole class of failure.

### Fixed
- **Navigation failed after an upgrade** — pages failed to open with
  `TypeError: Failed to fetch dynamically imported module`. The backend served
  `index.html` with no `Cache-Control`, so browsers applied heuristic freshness
  and reused the *previous* version's app shell from a cache that survives
  upgrades. That stale shell asked for code-split chunks by their old content
  hashes, which the new build no longer contains. The shell (and every unhashed
  file) is now served `no-cache, must-revalidate`, so an upgraded install can
  never boot the old one's UI. No assets were missing from any release.
- **Existing 2.0.3 installs are repaired on upgrade** — the desktop app clears
  its HTTP cache when the application version changes. This affects the cache
  only; settings, projects and other local data are untouched.
- **A missing frontend asset returned the app shell** — a request for a
  `.js`/`.css`/image/font path that does not exist now returns a 404 instead of
  `index.html`, so a packaging fault is diagnosable rather than surfacing as an
  unrelated error inside the app.
- **The desktop app could attach to an older RedForge on the same port** — the
  backend port is fixed, and any process answering `/healthz` was accepted. If a
  previously installed RedForge held the port, the new app loaded *that* build's
  UI. The supervisor now verifies the responding backend reports the expected
  application version and reports a clear error instead.

### Changed
- Content-hashed build output under `/assets/` is now explicitly cached as
  `immutable` for a year. Only the shell revalidates, so start-up stays fast.

### Added
- `scripts/verify_frontend_assets.py` — validates the complete frontend chunk
  reference graph (missing chunks, mixed builds, empty asset directories) and
  can compare two copies of a build byte-for-byte. Runs in CI after every
  frontend build and at each stage of desktop packaging.
- `scripts/smoke_packaged_app.py` — starts the packaged backend and fetches
  every lazily loaded chunk over HTTP, checking status, MIME type and cache
  policy. Runs in the release pipeline before installers are built.
- Regression coverage for the upgrade scenario, the cache and 404 contract, the
  port/version guard, and upgrade detection.

## [2.0.0]

RedForge becomes a **local AI engineering platform**. All v1.2 functionality is
preserved; the release is additive. Still local-first, localhost-only, no
accounts, no telemetry.

### Added
- **AI Studio** — local projects that group models, datasets, evaluations,
  reports, and training runs. Create / open / rename / duplicate / delete;
  recent projects on the dashboard.
- **Playground** — chat with any configured provider (system prompt, temperature,
  top-p, max tokens, seed), copy/export/clear, and a one-click **Run Security
  Evaluation** that reuses the existing engine. All generation flows through the
  Runtime Manager.
- **Dataset Lab** — import CSV / JSON / JSONL / TXT / MD / PDF / DOCX; preview
  with pagination + search; quality analysis (duplicates, missing, length,
  language, prompt-leakage, unsafe, malformed) with a score; cleaning
  (dedupe / trim / normalize / drop-empty) previewed before saving; train/val/test
  split; and **versioning** — every save is a new version, restore never
  overwrites.
- **Training Lab** — local **LoRA / QLoRA** fine-tuning through a swappable
  **Training Manager** provider (real Unsloth when a GPU + ML stack are present; a
  dependency-free simulation otherwise). Wizard, live dashboard (loss chart,
  checkpoints, logs, ETA), training history, and checkpoints.
- **RedForge Assistant** — a local, offline helper that explains evaluation
  results, attacks, dataset quality, and training questions from local metadata.
- **IDE-style shell** — top bar with breadcrumb + provider status, grouped
  collapsible sidebar, bottom status bar, and a **⌘K command palette** launcher.

### Changed
- Multi-provider wording made consistent across the app, CLI, docs, and website
  (Ollama is the recommended default, not a requirement).
- Website downloads now come directly from GitHub Releases.

### Hardening (release readiness)
- **Global React error boundary** — a single component error can no longer
  white-screen the app.
- **Dataset upload limits** — streamed, size-capped imports (default 50 MB,
  `REDFORGE_MAX_UPLOAD_BYTES`) that never buffer an arbitrarily large file.
- **Startup recovery** — orphaned evaluations / training / benchmark / agent runs
  left "running" by a crash are reconciled to `interrupted` on startup.
- **Single-process enforcement** — RedForge refuses to start under a multi-worker
  configuration (its live state is in-memory); override with
  `REDFORGE_ALLOW_MULTIWORKER=1`.

### Notes
- **Authentication remains intentionally absent** — RedForge is a single-user
  local tool; the trust boundary is your machine. Do not expose it to an
  untrusted network. See SECURITY.md.
- Real GPU training requires the Unsloth stack (`unsloth`, `peft`, `transformers`,
  `bitsandbytes`, `trl`) + a CUDA GPU; otherwise the simulation backend runs.

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

[2.0.0]: https://github.com/BRGOVIND/REDFORGE/releases/tag/v2.0.0
[1.2.0]: https://github.com/BRGOVIND/REDFORGE/releases/tag/v1.2.0
