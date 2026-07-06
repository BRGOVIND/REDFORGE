# Installation Guide

RedForge runs on **Windows** and **Linux** (macOS from source). It needs only
**Python 3.11+** and **Ollama** — no Node.js.

## 1. Install Ollama
Download from **https://ollama.com/download** and install it. Then pull a model:

```bash
ollama pull qwen3:8b     # recommended starter (also: llama3, gemma, mistral)
```

Make sure Ollama is running (`ollama serve`, or it starts automatically on most
systems).

## 2. Install RedForge

### Option A — Release download (recommended)
1. Download the release for your OS from the
   [Releases page](https://github.com/BRGOVIND/REDFORGE/releases):
   - **Windows:** `RedForge-Setup-<ver>.exe` (installer) or `redforge-<ver>-windows.zip`
   - **Linux:** `RedForge-<ver>-x86_64.AppImage` or `redforge-<ver>.tar.gz`
2. Unzip (if using the archive), then run `install.cmd` (Windows) or `./install.sh`
   (Linux). This installs the Python dependencies.

### Option B — From source (developers)
Requires Python, Node.js, and Git.

```bash
git clone https://github.com/BRGOVIND/REDFORGE.git
cd REDFORGE
pip install -e cli
redforge install        # installs backend deps, builds the frontend, inits the DB
```

## 3. Start RedForge

```bash
redforge start          # or: start.cmd / ./start.sh from a release
```

One process starts, your browser opens automatically at
`http://127.0.0.1:8000`, and the first-run setup appears. Follow it, then run
your first evaluation.

## Verify anytime

```bash
redforge doctor         # green/yellow/red system check
redforge status         # is it running? ports, sessions, models
```
