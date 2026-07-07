# RedForge

**A local red-teaming laboratory for LLMs.** Point it at any model you run through
[Ollama](https://ollama.com), throw a library of adversarial prompts at it, and
get a structured security report — with a score, findings, and recommendations.

Everything runs on your own machine. Nothing is sent to a cloud API.

> **v1.0.0** — one command to launch, a single process serving the API and UI.
> End users need only **Python 3.11+** and **Ollama**. Node.js is a
> development-only dependency.

---

## Quick start

1. **Install [Ollama](https://ollama.com/download)** and pull a model:
   ```bash
   ollama pull qwen3:8b        # or llama3, gemma, mistral
   ```
2. **Get RedForge** — download the release for your OS from
   [Releases](https://github.com/BRGOVIND/REDFORGE/releases), or clone (below).
3. **Start it:**
   ```bash
   redforge start             # or start.cmd / ./start.sh from a release
   ```
   One process starts, your browser opens at `http://localhost:8000`, and the
   first-run setup guides you the rest of the way.

Check things anytime:
```bash
redforge doctor              # green/yellow/red system check
redforge status              # running state, sessions, models
```

See [docs/quickstart.md](docs/quickstart.md) and
[docs/installation.md](docs/installation.md) for details.

---

## What it does

- Ships **28 attacks** across prompt injection, jailbreaks, context manipulation,
  and data leakage — plus **RedForge-Bench-V1**, 800 validated benchmark cases.
- Picks an **evaluation profile** (Quick Scan → Exhaustive); the engine profiles
  the model, plans deterministically, executes **adaptively** (mutate + escalate +
  retry), judges each response, and analyzes the results.
- Streams progress **live**: a stage timeline, a running security score, an event
  feed, and a real terminal.
- Produces a **security report** — executive summary, overall score, category
  scores, ranked vulnerabilities, and recommendations — exportable as JSON,
  Markdown, or PDF.
- Persistent, **resumable sessions** that survive refresh and backend restart.
- A **unified runtime** for all model traffic (streaming, per-model queue,
  cancellation, retries, metrics) — provider-agnostic, Ollama today.

---

## Install from source (developers)

Requires Python 3.11+, Node.js, Git, and Ollama.

```bash
git clone https://github.com/BRGOVIND/REDFORGE.git
cd REDFORGE
pip install .                # installs the `redforge` CLI
redforge install             # backend deps, builds the frontend, inits the DB
redforge start
```

Developer mode with hot reload (backend + Vite):
```bash
redforge start --dev
```

---

## The `redforge` CLI

`install · doctor · start · stop · status · models · evaluate · benchmark · logs ·
update · version`. See [cli/README.md](cli/README.md).

```bash
redforge evaluate qwen3:8b standard
redforge benchmark llama3
```

---

## API

The backend exposes a full REST API (interactive docs at
`http://localhost:8000/docs`). Highlights:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/evaluate` | Run the full intelligent pipeline (model + profile) |
| `GET` | `/api/sessions/{id}` · `/events` · `/terminal` | Session state, event/terminal streams |
| `GET` | `/api/report/{id}` · `/findings/{id}` · `/plans/{id}` | Report, findings, plan |
| `GET` | `/api/evaluation-profiles` · `/api/runtime-estimate` | Profiles, runtime estimate |
| `GET` | `/api/leaderboard` · `/api/history/{model}` | Rankings, score history |
| `GET` | `/api/system/checks` · `/api/runtime/status` | Onboarding checks, runtime metrics |

---

## Architecture

| Layer | Tech |
|---|---|
| API | FastAPI (async), one process also serves the built UI |
| Database | SQLite via SQLAlchemy 2.0 async, Alembic migrations |
| Runtime | Unified LLM client → Ollama at `localhost:11434` |
| Frontend | React 18, TypeScript, Vite, Tailwind, Recharts |
| CLI | Python standard library only |

Deep dives in [docs/architecture.md](docs/architecture.md) and the focused docs
alongside it.

---

## Documentation
[Installation](docs/installation.md) · [Quick Start](docs/quickstart.md) ·
[Troubleshooting](docs/troubleshooting.md) · [FAQ](docs/faq.md) ·
[Common Errors](docs/common-errors.md) · [Model Installation](docs/model-installation.md) ·
[GPU Support](docs/gpu-support.md) · [Architecture](docs/architecture.md) ·
[Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md)

---

## License

[MIT](LICENSE) © BRGOVIND
