<p align="center">
  <img src="assets/logo-mark.png" alt="RedForge" width="112" height="112" />
</p>

<h1 align="center">RedForge</h1>

<p align="center">
  <b>A local red-teaming laboratory for LLMs.</b><br/>
  Attack your models. Score the damage. Fix what breaks. All on your own machine.
</p>

<p align="center">
  <a href="https://github.com/BRGOVIND/REDFORGE/releases"><img src="https://img.shields.io/badge/version-1.0.0-red" alt="Version"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"/></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-yellow" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/tests-260%20passing-brightgreen" alt="Tests"/>
  <a href="https://redforgelabs.vercel.app"><img src="https://img.shields.io/badge/website-redforgelabs.vercel.app-orange" alt="Website"/></a>
</p>
Everything runs on your own machine by default. Nothing is sent to a cloud API
unless you explicitly configure a cloud provider.

> **v1.2.0** — one command to launch, a single process serving the API and UI.
> A multi-provider runtime (Ollama, LM Studio, llama.cpp, vLLM, OpenAI,
> Anthropic, Gemini, Groq, OpenRouter), a cross-provider Model Manager, and a
> centralized System Health Engine. End users need only **Python 3.11+** and a
> local runtime such as **Ollama**. Node.js is a development-only dependency.
> See [docs/providers.md](docs/providers.md) to use a different provider.
(feat: release RedForge v1.2.0)

---

## What is this?

RedForge points a library of adversarial attacks at any LLM you run through [Ollama](https://ollama.com), watches how the model holds up, and hands you a structured security report — overall score, category breakdowns, ranked vulnerabilities, and recommendations.

**Everything is local.** No cloud, no API keys, nothing leaves your device. If your model folds under a prompt injection, only you will know.

🌐 **Website & downloads:** [redforgelabs.vercel.app](https://redforgelabs.vercel.app)

---

## ✨ Features

- ⚔️ **28 adversarial attacks** — prompt injection, jailbreaks, context manipulation, data leakage
- 📊 **RedForge-Bench-V1** — 800 validated benchmark cases for consistent, comparable scoring
- 🧠 **Intelligent evaluation pipeline** — profiles the model, plans deterministically, then executes *adaptively* (mutate → escalate → retry), judges every response, and analyzes the results
- 🎚️ **Five evaluation profiles** — Quick Scan → Standard → Thorough → Comparative → Exhaustive
- 📡 **Live streaming UI** — stage timeline, running security score, event feed, and a real terminal
- 📄 **Exportable reports** — executive summary, scores, findings, recommendations, as JSON / Markdown / PDF
- 💾 **Resumable sessions** — survive page refreshes *and* backend restarts; pause, resume, cancel
- 🏆 **Leaderboard & history** — rank your models and track score changes over time
- 🔌 **Unified runtime** — streaming, per-model queue, cancellation, retries, metrics. Provider-agnostic by design; Ollama today

---

## 🚀 Quick start

You need exactly two things: **Python 3.11+** and **Ollama**. (Node.js is only for development.)

**1. Install [Ollama](https://ollama.com/download) and pull a model:**

```bash
ollama pull qwen3:8b     # or llama3, gemma, mistral — anything works
```

**2. Get RedForge.** Grab the release for your OS from the [Download portal](https://redforgelabs.vercel.app) or [GitHub Releases](https://github.com/BRGOVIND/REDFORGE/releases), then unpack it.

**3. Start it:**

```bash
redforge start           # or start.cmd / ./start.sh from a release
```

One process starts, your browser opens at `http://localhost:8000`, and the first-run setup walks you through the rest.

**Sanity checks, anytime:**

```bash
redforge doctor          # green / yellow / red environment check
redforge status          # running state, sessions, models
```

More detail in [docs/quickstart.md](docs/quickstart.md) and [docs/installation.md](docs/installation.md).

---

## 🛠️ Install from source (developers)

Requires Python 3.11+, Node.js, Git, and Ollama.

```bash
git clone https://github.com/BRGOVIND/REDFORGE.git
cd REDFORGE
pip install .            # installs the `redforge` CLI
redforge install         # backend deps + frontend build + DB init
redforge start
```

Hot-reload dev mode (backend reload + Vite):

```bash
redforge start --dev
```

Building release artifacts:

```bash
python scripts/build_release.py   # → redforge-1.0.0.zip / .tar.gz, self-contained, no Node.js needed to run
```

---

## ⌨️ The `redforge` CLI

Pure Python standard library — no extra dependencies.

| Command | What it does |
|---|---|
| `redforge start` | Launch the app (single process, API + UI) |
| `redforge stop` | Stop it |
| `redforge status` | Running state, sessions, models |
| `redforge doctor` | Full environment health check |
| `redforge models` | List available Ollama models |
| `redforge evaluate <model> <profile>` | Run an evaluation from the terminal |
| `redforge benchmark <model>` | Run RedForge-Bench-V1 |
| `redforge logs` | Tail the logs |
| `redforge install` | Set everything up |
| `redforge update` | Update RedForge |
| `redforge version` | Version info (with a little ASCII logo, because why not) |

Examples:

```bash
redforge evaluate qwen3:8b standard
redforge benchmark llama3
```

Full reference: [cli/README.md](cli/README.md)

---

## 🔌 API

The backend exposes a full REST API — interactive docs live at `http://localhost:8000/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/evaluate` | Run the full intelligent pipeline (model + profile) |
| `GET` | `/api/sessions/{id}` · `/events` · `/terminal` | Session state, event & terminal streams |
| `GET` | `/api/report/{id}` · `/findings/{id}` · `/plans/{id}` | Report, findings, plan |
| `GET` | `/api/evaluation-profiles` · `/api/runtime-estimate` | Profiles, runtime estimate |
| `GET` | `/api/leaderboard` · `/api/history/{model}` | Rankings, score history |
| `GET` | `/api/system/checks` · `/api/runtime/status` | Onboarding checks, runtime metrics |

Errors come back in a structured envelope: `{success, error: {code, message, detail}}`.

---

## 🏗️ Architecture

One FastAPI process serves both the API and the built React dashboard. SQLite underneath. Ollama does the model serving.

| Layer | Tech |
|---|---|
| API | FastAPI (async) — single process also serves the built UI (SPA catch-all + `/healthz`) |
| Database | SQLite via SQLAlchemy 2.0 async, Alembic migrations |
| Runtime | Unified LLM client → Ollama at `localhost:11434` |
| Frontend | React 18, TypeScript, Vite, Tailwind, Recharts |
| CLI | Python standard library only |

```
backend/     FastAPI app, runtime, evaluation engine, tests (260 tests)
frontend/    React dashboard (Vite)
website/     Marketing site (Vite) — deployed to Vercel
cli/         redforge CLI (stdlib Python)
datasets/    attacks + RedForge-Bench-V1
installers/  Windows (Inno Setup) + Linux (AppImage)
scripts/     build_release.py, generate_icons.py
docs/        installation, quickstart, troubleshooting, faq, architecture
```

Deep dives in [docs/architecture.md](docs/architecture.md).

---

## 🔒 Security model

RedForge is **localhost-only, single-user, and unauthenticated by design** — it binds to `127.0.0.1` and never accepts outside connections. This is intentional and documented in [SECURITY.md](SECURITY.md). The codebase has been through a Bandit security pass: no secrets, no SQL injection, no XSS, no path traversal, no unsafe deserialization.

---

## 📸 Screenshots

<!-- Screenshots coming soon: dashboard, live evaluation, security report -->
*Coming soon — dashboard, live evaluation view, and a sample security report.*

---

## 📚 Documentation

[Installation](docs/installation.md) · [Quick Start](docs/quickstart.md) · [Troubleshooting](docs/troubleshooting.md) · [FAQ](docs/faq.md) · [Common Errors](docs/common-errors.md) · [Model Installation](docs/model-installation.md) · [GPU Support](docs/gpu-support.md) · [Architecture](docs/architecture.md) · [Changelog](CHANGELOG.md)

---

## 🤝 Contributing

Issues and PRs are welcome. If you're adding attacks or benchmark cases, keep them in `datasets/` and make sure the test suite stays green:

```bash
cd backend && pytest    # 260 tests, in-memory SQLite
```

---

## 🔮 What's forging next

Where RedForge is headed (see [ROADMAP.md](ROADMAP.md) for the full picture):

- **Native installers** — a real Windows `.exe` (Inno Setup) and Linux AppImage. The `.zip` / `.tar.gz` releases are the working artifacts today.
- **CI release pipeline** — automated builds and publishing on tag.
- **Broader platform testing** — physically tested on Windows so far; Linux/macOS support is via cross-platform code and needs real-hardware validation.
- **More providers** — the runtime layer is provider-agnostic; Ollama is just the first backend.

---

## 📄 License

[MIT](LICENSE) © [BRGOVIND](https://github.com/BRGOVIND)

<p align="center"><i>Forge responsibly. 🔥</i></p>

