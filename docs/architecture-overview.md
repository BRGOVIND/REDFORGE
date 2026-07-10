# Architecture Overview

A high-level tour of how RedForge fits together. This is the user-facing
overview; deeper design notes live in `docs/architecture/` (developer docs).

## One process, local by default

In production RedForge is a **single process**: a FastAPI backend that serves the
API *and* the compiled web interface. There is no separate frontend server and no
Node.js at runtime. It binds to `127.0.0.1` and keeps all data on your machine.

```
  redforge start
        │
        ▼
  FastAPI backend  ──serves──►  Web UI (compiled)
        │
        ├─ Runtime layer   → your model provider (Ollama, LM Studio, …)
        ├─ Evaluation      → profiles, planning, adaptive execution, scoring
        ├─ Analysis        → findings, recommendations, reports
        └─ SQLite          → sessions, events, history
```

## The pieces

**CLI (`redforge`).** Standard-library only. Manages the lifecycle
(`install`, `start`, `update`, `doctor`, `diagnose`, …) and talks to the backend
over HTTP. See the [CLI Reference](cli-reference.md).

**Runtime layer.** A unified client for all model traffic — streaming, queuing,
retries, cancellation, metrics, and a model cache. Each provider (Ollama, LM
Studio, llama.cpp, vLLM, and cloud APIs) implements only its wire format; the
shared client does the rest. Adding a provider does not change the engine. See
[providers.md](providers.md).

**Runtime Manager.** Lists providers, probes their health, and lets you switch
the active one — all through the runtime layer, never around it.

**Model Manager.** A provider-agnostic catalog of installed models with metadata
and capability-gated actions (e.g. deletion, download).

**System Health Engine.** One registry of checks (OS, Python, CPU, GPU, RAM,
disk, runtime, providers, models, database) that is the single source of truth
for system validation. The API (`/api/health`), `redforge doctor`, onboarding,
and startup all consume it — there is exactly one implementation of each check.

**Evaluation engine.** The intelligent path profiles the target model, builds a
deterministic plan, executes adaptively (mutating and escalating attacks), and
scores responses with heuristics and optional LLM-judge evaluation. Results are
persisted per stage as durable sessions and events.

**Analysis & reporting.** Turns raw results into findings, recommendations, and a
scored security report you can export.

## Data

RedForge uses a local SQLite database for sessions, events, and history.
Settings, logs, and the runtime environment live under `~/.redforge` (or the
install directory). Nothing leaves your machine unless you configure a cloud
provider.

## Design principles

- **Local-first.** Your models and data stay on your machine by default.
- **Provider-agnostic.** The UI and engine never special-case a provider; they
  read declarative capabilities.
- **Single source of truth.** One Health Engine, one runtime client, one version
  file — consumed everywhere rather than reimplemented.
- **Reproducible.** Pinned dependencies, checksummed releases, and a
  tag-driven build. See `docs/architecture/release-engineering.md`.
