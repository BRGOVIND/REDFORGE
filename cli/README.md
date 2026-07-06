# RedForge CLI

The unified `redforge` command. **Standard library only** — end users need
nothing beyond Python (and Ollama). `psutil` is used opportunistically if present.

## Install

```bash
pip install -e cli        # from source
# or, in a packaged release, the launcher wraps it for you
```

Without installing, run it from source via the wrappers:

```bash
scripts/redforge doctor          # Linux/macOS
scripts\redforge.cmd doctor      # Windows
```

## Commands

| Command | What it does |
|---------|--------------|
| `redforge install` | verify prerequisites, install backend deps, build frontend (dev), init DB, verify |
| `redforge doctor [--copy]` | green/yellow/red system diagnostics (Python, Node, OS, GPU, RAM, disk, Ollama, models, DB, dataset, ports) |
| `redforge start [--dev] [--no-browser] [--port N]` | start RedForge and open the browser (one process in production) |
| `redforge stop` | stop RedForge gracefully |
| `redforge status` | running state, ports, sessions, models, runtime metrics |
| `redforge models` | list installed + recommended models with pull commands |
| `redforge evaluate <model> [profile]` | start an evaluation |
| `redforge benchmark <model>` | run a benchmark evaluation |
| `redforge logs [-n N]` | recent server logs |
| `redforge update` | update (git pull + reinstall, or points to releases) |
| `redforge version` | print version |

## Production vs development

- **Production** (`redforge start`): ONE backend process serves the API *and* the
  built frontend. No Node.js, no Vite server.
- **Development** (`redforge start --dev`): backend with reload + Vite dev server
  (hot reload) — for contributors only.
