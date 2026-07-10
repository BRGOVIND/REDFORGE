# Installation

RedForge runs on **Windows, macOS, and Linux**. It needs only **Python 3.11+**
and a local LLM **runtime** (Ollama by default). Node.js is not required to run.

## Requirements

| Requirement | Details |
|-------------|---------|
| Operating system | Windows 10/11, macOS 12+, modern Linux |
| Python | 3.11 or newer |
| Runtime | Ollama, LM Studio, llama.cpp, or vLLM (see [providers.md](providers.md)) |
| Disk | ~500 MB for RedForge; models are separate |
| Memory | 8 GB RAM is comfortable for small/medium models; more for larger ones |

## Option A — pip (recommended)

```bash
pip install redforge
redforge install
redforge start
```

- `pip install redforge` installs the command-line interface.
- `redforge install` creates a dedicated virtual environment, installs the
  backend, detects hardware and providers, creates shortcuts, and runs a health
  check. It is **idempotent** — re-running it repairs an existing install.
- `redforge start` launches RedForge and opens your browser.

## Option B — self-contained release

1. Download the release for your OS from
   [GitHub Releases](https://github.com/BRGOVIND/REDFORGE/releases). Each release
   ships with a `SHA256SUMS.txt` you can use to verify the download.
2. Install:
   - **Windows:** run `install.cmd`, or the `RedForge-Setup-*.exe` installer.
   - **Linux:** run `./install.sh`, or the `RedForge-*.AppImage`.
   - **macOS:** extract the `.tar.gz` and run `./install.sh`.
3. Start with `start.cmd` / `./start.sh`, or `redforge start`.

### Verifying a download

```bash
sha256sum -c SHA256SUMS.txt          # Linux
shasum -a 256 -c SHA256SUMS.txt      # macOS
certutil -hashfile <file> SHA256     # Windows
```

## Installing a runtime

RedForge does not install a model runtime for you. The default is Ollama:

1. Install [Ollama](https://ollama.com/download).
2. Start it: `ollama serve`.
3. Pull a model: `ollama pull llama3.1:8b` — or use RedForge's onboarding to
   download a model that fits your hardware.

See [providers.md](providers.md) for LM Studio, llama.cpp, vLLM, and cloud
providers.

## Maintaining an installation

```bash
redforge repair        # fix a broken or partial install (idempotent)
redforge update        # update to the latest release (verifies checksums)
redforge uninstall     # remove the environment and shortcuts (keeps your data)
```

`redforge update` preserves your evaluation history and settings and rolls back
automatically if anything goes wrong. See the
[updater](architecture/updater.md) notes for details.

## Network exposure

By default RedForge binds to `127.0.0.1` and is reachable only from your machine.
It has **no authentication**. If you bind it to a non-local address
(`redforge start --host 0.0.0.0`), it warns you first, because anyone on your
network would then be able to use the API. Only do this on a trusted network.

## Troubleshooting

If install or start fails, run `redforge doctor` for a diagnosis, and see
[troubleshooting.md](troubleshooting.md).
