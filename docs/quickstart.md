# Quick Start

Get from zero to your first security report. In the strict profile, RedForge
uses local runtimes and no hosted API key. Installer or manual runtime setup may
need connectivity unless you provide packages and models offline.

## 1. Install RedForge

```bash
python -m pip install .   # from the RedForge source checkout
redforge install
```

`redforge install` sets up a dedicated environment, installs the backend,
detects your hardware and runtime providers, and runs a health check. It is
safe to re-run at any time.

> Prefer a self-contained download? Grab a release for your OS from
> [GitHub Releases](https://github.com/BRGOVIND/REDFORGE/releases) and run
> `install.cmd` (Windows) or `./install.sh` (Linux/macOS). See
> [installation.md](installation.md).

## 2. Install a runtime and a model

RedForge evaluates models served by a local **runtime provider**. The default is
[Ollama](https://ollama.com/download):

```bash
# after installing Ollama
ollama serve
ollama pull llama3.1:8b
```

The explicit `ollama pull` command above contacts Ollama's model source. For a
strict RedForge setup, transfer an already downloaded model into your local
runtime. In-app pulls are disabled in strict mode. Other local runtimes and the
separate connected profile are covered in [providers.md](providers.md).

## 3. Start RedForge

```bash
redforge start
```

This launches a single local process and opens your browser. On first run you're
guided through onboarding: a system scan, runtime detection, and model setup.

## 4. Run your first evaluation

From the app: choose **New Evaluation**, pick a model and a profile
(Quick Scan → Exhaustive), and start. You get a live view of each attack and, at
the end, a scored security report with findings and recommendations.

From the command line:

```bash
redforge evaluate llama3.1:8b quick_scan
```

## 5. Check your setup any time

```bash
redforge doctor        # system + runtime health
redforge status        # is RedForge running?
```

## Next steps

- [Installation](installation.md) — detailed install and packaging options
- [CLI Reference](cli-reference.md) — every command and flag
- [Runtime Providers](providers.md) — use a different runtime
- [Troubleshooting](troubleshooting.md) and [FAQ](faq.md)
