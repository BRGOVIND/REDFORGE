# RedForge v2.0.0 — Release Notes

**RedForge is now a local AI engineering platform.** Manage models, chat, curate
datasets, fine-tune with LoRA/QLoRA, and red-team any model — all on your own
machine. Local-first, localhost-only, no accounts, no telemetry.

Everything from v1.2 keeps working; this release is additive.

## New in v2.0.0
- **AI Studio** — local projects that group models, datasets, evaluations,
  reports, and training runs.
- **Playground** — chat with any provider, tune parameters, and run a security
  evaluation in one click. All generation flows through the Runtime Manager.
- **Dataset Lab** — import CSV/JSON/JSONL/TXT/MD/PDF/DOCX, preview, analyze
  quality, clean, split train/val/test, and version every save.
- **Training Lab** — local **LoRA/QLoRA** fine-tuning via a swappable backend
  (Unsloth when a GPU + ML stack are present; a simulation otherwise), with a live
  dashboard (loss chart, checkpoints, logs, ETA) and history.
- **Assistant + ⌘K command palette** and an IDE-style workspace shell.

## Install in three steps
1. **Get the release** for your OS (or `git clone` for developers).
2. **Install:** `install.cmd` (Windows) or `./install.sh` (Linux/macOS).
   Requires Python 3.11+ and a local runtime — [Ollama](https://ollama.com/download)
   is the recommended default (LM Studio, llama.cpp, and vLLM also work).
3. **Start:** `start.cmd` / `./start.sh` — your browser opens automatically.

Follow the on-screen setup; install or download a model with your runtime, or let
onboarding recommend one. Then explore the sidebar (or press **⌘K / Ctrl-K**).

## Requirements
- **Python 3.11+** and one local **runtime** (Ollama recommended; LM Studio,
  llama.cpp, vLLM also work). Node.js is **not** required to run.
- **Real GPU training** additionally needs a CUDA GPU and the Unsloth stack
  (`unsloth`, `peft`, `transformers`, `bitsandbytes`, `trl`). Without it, the
  Training Lab runs a dependency-free **simulation** so you can learn the flow.

## Trust model
RedForge is **local-first, localhost-only, single-user, and unauthenticated by
design** — like a local database GUI or Jupyter server. No accounts, no telemetry,
no mandatory cloud; nothing is uploaded. Cloud providers are opt-in and use your
own API key (read from the environment, never stored). **Do not expose RedForge to
an untrusted network.** It runs as a single process and refuses to start under a
multi-worker configuration. Full statement in [SECURITY.md](SECURITY.md).

## Known limitations
- macOS runs from the `.tar.gz`; a signed `.dmg` is future work.
- Windows `.exe` and Linux `AppImage` are produced in CI from the release folder.
- Live training progress and background jobs do not survive a backend restart;
  interrupted jobs are marked `interrupted` on the next start.
