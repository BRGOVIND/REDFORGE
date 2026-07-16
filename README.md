<p align="center">
  <img src="assets/logo-mark.png" alt="RedForge" width="112" height="112" />
</p>

<h1 align="center">RedForge</h1>

<p align="center">
  <b>A local AI engineering platform for building, evaluating, and hardening LLMs.</b><br/>
  Manage models, chat, curate datasets, fine-tune, and red-team — all on your own machine.
</p>

<p align="center">
  <a href="https://github.com/BRGOVIND/REDFORGE/releases"><img src="https://img.shields.io/badge/version-2.0.0-red" alt="Version"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License"/></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-yellow" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/tests-400%2B%20passing-brightgreen" alt="Tests"/>
  <a href="https://redforgelabs.vercel.app"><img src="https://img.shields.io/badge/website-redforgelabs.vercel.app-orange" alt="Website"/></a>
</p>

> **v2.0.0** — RedForge grows from a red-teaming lab into a full **local AI
> engineering platform**: an **AI Studio** for projects, a **Playground** for
> chat, a **Dataset Lab** for curating training data, and a **Training Lab** for
> local LoRA/QLoRA fine-tuning — alongside the existing multi-provider runtime,
> Model Manager, and Security Center. **Local-first, localhost-only, no accounts,
> no telemetry.** End users need only **Python 3.11+** and a local runtime such as
> **Ollama**. See [Trust model](#-trust-model) below.

---

## What is this?

RedForge is a desktop-style workspace for local AI work. You manage the models you
run through a local runtime (Ollama, LM Studio, llama.cpp, vLLM — or a cloud
provider with your own key), chat with them, build and clean datasets, run
LoRA/QLoRA fine-tunes, and red-team any model against a library of adversarial
attacks to get a structured security report.

**Everything is local by default.** No cloud, no accounts, no telemetry. Nothing
leaves your device unless you explicitly configure a cloud provider.

🌐 **Website & downloads:** [redforgelabs.vercel.app](https://redforgelabs.vercel.app)

> **Screenshots:** _placeholders — add `docs/screenshots/{dashboard,playground,dataset-lab,training-lab,security-report}.png`._

---

## ✨ What's inside

**AI engineering**
- 🗂️ **AI Studio** — local projects that group models, datasets, evaluations, reports, and training runs. Create, open, rename, duplicate, delete.
- 💬 **Playground** — chat with any configured provider; tune system prompt, temperature, top-p, max tokens, seed; run a security evaluation in one click. All generation flows through the Runtime Manager.
- 📚 **Dataset Lab** — import CSV/JSON/JSONL/TXT/MD/PDF/DOCX, preview, analyze quality (duplicates, missing, length, language, prompt-leakage), clean (dedupe/trim/normalize/drop-empty), split train/val/test, and **version every save**.
- 🏋️ **Training Lab** — local **LoRA / QLoRA** fine-tuning via a swappable training backend (Unsloth when a GPU + ML stack are present; a dependency-free simulation otherwise). Wizard, live dashboard (loss chart, checkpoints, logs, ETA), and training history.

**Security (the original core)**
- ⚔️ **Adversarial attack library** across 12 categories — prompt injection, jailbreaks, roleplay, RAG, encoding, and more.
- 📊 **RedForge-Bench** — validated benchmark cases for consistent, comparable scoring.
- 🧠 **Intelligent evaluation** — profile → plan → adaptive execute (mutate/escalate/retry) → judge → analyze, with a structured security report (JSON / Markdown / PDF).
- 🏆 **Leaderboard & history** — rank models and track score changes over time.

**Platform**
- 🔌 **Multi-provider runtime** — one client for streaming, queue, cancellation, retries, metrics. Nine providers: Ollama (default), LM Studio, llama.cpp, vLLM, OpenAI, Anthropic, Gemini, Groq, OpenRouter.
- ❤️ **System Health Engine**, **⌘K command palette**, and a local **Assistant** that explains results, attacks, and training from local metadata.

---

## 🔒 Trust model

RedForge is built to be trusted with your most sensitive testing. Its security
posture is deliberate:

- **Local-first.** Models, datasets, prompts, checkpoints, and results stay on
  your machine. Nothing is uploaded.
- **Localhost only.** The server binds to `127.0.0.1` by default. Binding to a
  non-local address prints a warning first (`redforge start --host …`).
- **No accounts. No telemetry. No mandatory cloud.** RedForge works fully offline.
- **Authentication is intentionally absent.** RedForge is a single-user local
  tool, like a database GUI or a local Jupyter server. There is no login because
  the trust boundary is *your machine*. **Do not expose RedForge to an untrusted
  network** — anyone who can reach the port can use the API. Cloud providers are
  opt-in and require your own API key, which is read from the environment and
  never stored or logged.
- **Single process by design.** Live state (runtime cache, training/download
  progress) is in-memory, so RedForge must run as one process — it refuses to
  start under a multi-worker configuration.

See [SECURITY.md](SECURITY.md) for the full statement.

---

## 🚀 Quick start

You need **Python 3.11+** and one local **runtime**. Ollama is the recommended default; LM Studio, llama.cpp, and vLLM also work (see [docs/providers.md](docs/providers.md)). Node.js is only for development.

**1. Install a runtime and add a model.** [Ollama](https://ollama.com/download) is the easiest default — install it and pull a model, or choose another supported runtime (see [docs/providers.md](docs/providers.md)). RedForge can also recommend and download a model for you during onboarding.

```bash
ollama pull qwen3:8b     # example, using the recommended default runtime
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

## 🧭 User guide

Once RedForge is open, the left sidebar is the map and **⌘K / Ctrl-K** is the
fastest way anywhere. A typical workflow:

1. **Create a project** — *Projects* (AI Studio) → **New Project**. A project
   groups your models, datasets, evaluations, reports, and training runs.
2. **Pick a runtime & model** — *Runtime* selects the active provider; *Models*
   browses and manages installed models. Onboarding can download one for you.
3. **Chat** — *Playground* to talk to a model, tune parameters, and iterate on a
   system prompt. Click **Run Security Evaluation** to send it straight into the
   evaluation engine.
4. **Curate data** — *Dataset Lab* → **Import** a file, review **Quality**,
   **Clean** it, and **Split** into train/val/test. Every save is versioned.
5. **Fine-tune** — *Training Lab* → **New Training Run**, pick a base model,
   dataset, LoRA/QLoRA, and parameters. Watch loss, checkpoints, and logs live.
   (Real training needs a GPU + the Unsloth stack; otherwise a simulation runs so
   you can learn the flow.)
6. **Red-team** — *Evaluate* runs the attack library against a model; watch it
   **Live**, then read the **Report** (score, findings, recommendations, export).

The floating **Assistant** (bottom-right) explains scores, attacks, dataset
quality, and training questions from local metadata — no network required.

---

## 🛠️ Install from source (developers)

Requires Python 3.11+, Node.js, Git, and a local runtime (Ollama recommended).

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
python scripts/build_release.py   # → redforge-<version>.zip / .tar.gz, self-contained, no Node.js needed to run
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
| `redforge models` | List models from the active runtime provider |
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

One FastAPI process serves both the API and the built React SPA. SQLite
underneath. A local runtime (Ollama by default) does the model serving. Each
capability is an **isolated, swappable module** — the Runtime Manager, Training
Manager, Dataset Lab, and Security engine don't reach into each other.

| Layer | Tech |
|---|---|
| API | FastAPI (async) — single process also serves the built UI (SPA catch-all + `/healthz`) |
| Database | SQLite via SQLAlchemy 2.0 async |
| Runtime | Unified multi-provider client (Ollama, LM Studio, llama.cpp, vLLM, cloud APIs) via the **Runtime Manager** |
| Training | **Training Manager** with swappable providers (Unsloth for real LoRA/QLoRA; simulation fallback) |
| Datasets | **Dataset Lab** — isolated parse/analyze/clean/split/version logic |
| Frontend | React 18, TypeScript, Vite, Tailwind, Recharts — IDE-style shell, ⌘K palette |
| CLI | Python standard library only |

```
backend/     FastAPI app + modules: runtime/, training/, datasets_lab/,
             projects/, health/, sessions/, execution/, evaluation engine (400+ tests)
frontend/    React workspace (Vite) — Studio, Playground, Dataset Lab, Training Lab, Security
website/     Marketing site (Vite) — deployed to Vercel
cli/         redforge CLI (stdlib Python)
datasets/    attacks + RedForge-Bench
installers/  Windows (Inno Setup) + Linux (AppImage)
scripts/     build_release.py, version.py, checksums.py
docs/        installation, quickstart, providers, cli-reference, architecture/
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
cd backend && pytest    # 369 tests, in-memory SQLite
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

