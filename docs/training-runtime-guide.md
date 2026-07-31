# Training Runtime Guide

How real LoRA/QLoRA training works in RedForge, why it is an optional download,
and how to add future training providers.

---

## Why training is optional

The training engine — PyTorch with CUDA, Unsloth, Transformers, PEFT, TRL,
bitsandbytes, Accelerate — is **2–4 GB**. Bundling it would take the RedForge
installer from ~150 MB to several gigabytes, and every user would pay that cost
whether or not they ever fine-tune a model.

So RedForge ships **inference-complete and training-optional**. Everything else —
chat, benchmarking, security evaluation, datasets, reports — works immediately
after install. Training asks first, then installs on demand.

The rule that makes this honest: **RedForge never silently substitutes simulated
training for real training.** If the runtime is missing you get a clear panel
explaining what is missing, what it costs, and a one-click install. If you choose
to run simulated training anyway, every surface says *Simulation Mode*.

---

## Architecture

Three environments, deliberately isolated:

```
┌──────────────────────────┐
│ Electron shell            │  desktop/electron
└─────────────┬─────────────┘
              │ spawns
┌─────────────▼─────────────┐
│ RedForge backend          │  frozen, ~150 MB, NO torch — ever
│  app.training.manager     │  picks a provider
│  app.training_runtime     │  detects + installs the runtime
└─────────────┬─────────────┘
              │ spawns (subprocess)
┌─────────────▼─────────────┐
│ Managed training runtime  │  2–4 GB venv, torch + unsloth + …
│  app/training_runtime/    │
│      worker.py            │  the only code that imports torch
└───────────────────────────┘
```

### Why a subprocess, not an import

The backend can never import torch, for three independent reasons:

1. **The frozen backend has no torch.** It is excluded from the PyInstaller build,
   which is what keeps the installer small.
2. **Isolation.** A broken CUDA install, a segfaulting kernel or an OOM kill takes
   down the training subprocess, not the whole application.
3. **Cancellation.** You can kill a process tree. You cannot interrupt a thread
   blocked inside a CUDA kernel.

`app/training/providers/managed.py` spawns
`<runtime>/venv/bin/python app/training_runtime/worker.py <config.json>` and reads
a line protocol from its stdout:

```
@@RF@@{"status":"running","step":3,"total":40,"loss":1.83,"epoch":0.4}
```

Statuses: `starting` · `running` · `checkpoint` · `completed` · `failed`. Anything
not prefixed `@@RF@@` is library chatter and goes to the debug log. If the worker
exits without a terminal status, the provider reports **failed** — it never infers
success.

> `worker.py` is deliberately self-contained and imports nothing from `app.*`.
> The managed venv contains the training stack, not RedForge. It also ships as a
> real file via PyInstaller `--add-data`, because an external interpreter cannot
> read a script out of a PyInstaller archive.

### Where the runtime lives

| OS | Path |
|----|------|
| Windows | `%LOCALAPPDATA%\RedForge\training-runtime` |
| macOS | `~/Library/Application Support/RedForge/training-runtime` |
| Linux | `~/.local/share/redforge/training-runtime` |

Portable installs and `REDFORGE_HOME` take precedence, so a portable copy keeps
its runtime beside the executable. `REDFORGE_TRAINING_RUNTIME` overrides
everything.

**Your system Python is never modified.** Everything installs into
`<runtime>/venv`, and pip's cache lives inside the runtime directory so removing
it reclaims every byte.

---

## Installation

Installation is a **Job**, so it appears in the Global Task Manager with progress,
ETA, logs, cancel and retry — like every other long-running operation.

Four phases, each recorded on completion:

| Phase | What happens | Weight |
|-------|--------------|--------|
| `environment` | create the isolated venv, upgrade pip | 5% |
| `torch` | install PyTorch from the CUDA-matched wheel index | 55% |
| `packages` | install Unsloth, Transformers, PEFT, TRL, … | 30% |
| `verify` | import everything, confirm CUDA sees the GPU | 10% |

### Durability

| Failure | How it is survived |
|---------|--------------------|
| App restart | Completed phases are in `install-state.json`; a restart resumes at the first incomplete phase |
| Network interruption | pip retries with backoff; its cache lives in the runtime dir, so a retry reuses partial downloads |
| Power failure | The `READY.json` marker is written **last**, after verification. A half-install is reported `partial`, never `ready` |
| Corrupt state file | Treated as "no state" — the installer starts cleanly rather than wedging |

### Choosing the wheel

The CUDA variant is chosen from the **driver's** reported CUDA version
(`nvidia-smi`), never from a guess:

| Driver supports | Wheels |
|-----------------|--------|
| ≥ 12.6 | `cu126` |
| ≥ 12.4 | `cu124` |
| ≥ 12.1 | `cu121` |
| ≥ 11.8 | `cu118` |
| no GPU | `cpu` (with an honest warning that this is impractical) |

Installing cu126 wheels against a CUDA 12.1 driver produces a runtime that
imports fine and then fails at the first kernel launch, so this check matters.

---

## Backend selection

`app/training/manager.py` resolves a provider. Preference order:

1. `unsloth` — in-process; source installs that already have the ML stack
2. `managed` — subprocess against the managed runtime (the packaged app)
3. `simulation` — always available

Two rules are enforced:

- **An unknown backend raises `UnknownBackendError`**, surfaced as HTTP 400 with
  the available names and a fix. It used to fall through to simulation, which
  meant a typo produced a *fake* run that reported success.
- **A backend that exists but cannot run here is also a 400**, with the reason.

`training.default_backend` in Settings is authoritative. Its default is `auto`
(never a concrete backend — hardcoding `simulation` there would force simulated
runs on a capable GPU). If the setting names a backend that is not usable, the
API falls back to auto-detection and says so in `preference_note`.

---

## Adding a training provider

1. Implement `TrainingProvider` (`app/training/providers/base.py`):
   `name`, `label`, `is_available() -> (bool, reason)`, `diagnose()`, and an async
   `run(config, cancel)` generator yielding `ProgressEvent`s.
2. Register it in `BUILTIN_PROVIDERS` (`app/training/providers/__init__.py`) — one
   line — or call `manager.register_provider(name, factory)` at runtime.
3. Add it to `_AUTO_ORDER` in `manager.py` if it should participate in
   auto-detection. Keep `simulation` last.

Nothing else changes. The manager, the runner, the API and the UI all speak only
the provider interface.

Contract requirements:

- `run()` must **never raise** — wrap backend errors in a `failed` ProgressEvent.
- It must be cancellation-cooperative (`cancel()` returns True → stop promptly).
- It must emit a terminal event (`completed` / `failed` / `cancelled`). A provider
  that stops emitting is treated as failed.

---

## Troubleshooting

**"Training Runtime Required" even though I have PyTorch**
The panel reports the *managed* runtime, not your global Python. A source install
that already has the stack uses the in-process `unsloth` provider instead — check
Training → Backend, where it will be selected automatically.

**Install fails with "No system Python found"**
Creating a virtual environment needs a real interpreter, and the frozen backend is
not one. Install Python 3.10+ from python.org and retry. This is the only external
prerequisite, and the installer states it before doing any work.

**Installed, but "PyTorch cannot see your GPU"**
A CUDA/driver mismatch. Update your NVIDIA driver, then use **Repair Training
Runtime**, which reinstalls with the correct wheel variant.

**Training can't find a model I already downloaded**
It should — the worker deliberately does *not* redirect `HF_HOME`, so it resolves
models through the same Hugging Face cache the Model Hub writes to. If it still
misses, check that `HF_HOME` is not set globally in your shell.

**Removing the runtime**
Training → Runtime → Remove. It deletes only `<runtime>/`; models, datasets, runs
and reports live elsewhere and are untouched.
