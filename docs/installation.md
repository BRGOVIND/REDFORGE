# Installation

RedForge is designed for **Windows, macOS, and Linux**. The source installation
needs **Python 3.11+** and a local LLM **runtime** (Ollama by default). The
desktop package bundles Python; Node.js is not required to run. Platform-specific
2.1.0 packages have not all been verified yet.

The 2.1.0 candidate defaults to [strict local mode](network-profile.md).
It does not download dependencies, model weights, or updates for you.

## Requirements

| Requirement | Details |
|-------------|---------|
| Operating system | Windows 10/11, macOS 12+, modern Linux |
| Python | 3.11 or newer |
| Runtime | Ollama, LM Studio, llama.cpp, or vLLM (see [providers.md](providers.md)) |
| Disk | ~500 MB for RedForge; models are separate |
| Memory | 8 GB RAM is comfortable for small/medium models; more for larger ones |

## Option A — CLI and source checkout

```bash
python -m pip install .   # from the RedForge source checkout
redforge install
redforge start
```

- `python -m pip install .` installs the command-line interface from this
  checkout. Do not assume a similarly named package on a package index is this
  repository's official release. The `pip` command itself may contact a package
  index unless you arrange an offline install; it is outside the running app's
  strict profile.
- `redforge install` creates a dedicated virtual environment, installs the
  backend, detects hardware and providers, creates shortcuts, and runs a health
  check. In strict mode it uses locally available packages or a wheelhouse set
  with `REDFORGE_WHEELHOUSE`; otherwise it fails without contacting an index.
  Re-running it can repair an existing install.
- `redforge start` launches RedForge and opens your browser.

## Option B — release downloads

1. Download the release for your OS from
   [GitHub Releases](https://github.com/BRGOVIND/REDFORGE/releases). Each release
   ships with a `SHA256SUMS.txt` you can use to verify the download.
2. Choose either a platform desktop package or the Python source archive.
   - **Windows desktop:** run `RedForge-Setup-*.exe`, or extract the portable ZIP
     and run `RedForge.exe`. The desktop package bundles Python and the backend.
   - **Linux desktop:** use the AppImage or `.deb` once a platform-verified build
     is available.
   - **macOS desktop:** use the platform DMG once a signed/notarized build is
     available.
   - **Python source archive:** extract the source ZIP or `.tar.gz`, then run
     `install.cmd` (Windows) or `./install.sh` (Linux/macOS). This archive is
     **not self-contained**: it needs Python 3.11+ and dependencies already
     installed or an offline wheelhouse set with `REDFORGE_WHEELHOUSE` in strict
     mode. Run `start.cmd` or `./start.sh` after installation.

The current 2.1.0 packages are test artifacts, not published consumer builds.
Unsigned packages may trigger operating-system trust warnings; do not bypass
those warnings for an unverified download.

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
3. Bring an already downloaded model. An explicit `ollama pull llama3.1:8b`
   command contacts Ollama's model source outside RedForge's strict policy.
   RedForge's in-app onboarding download is disabled in strict mode.

See [providers.md](providers.md) for LM Studio, llama.cpp, vLLM, and the
separate connected profile.

## Maintaining an installation

```bash
redforge repair        # fix a broken or partial install (idempotent)
redforge update        # connected profile only; blocked in strict mode
redforge uninstall     # remove the environment and shortcuts (keeps your data)
```

Back up the database before upgrading. Review the
[updater](architecture/updater.md) notes for details.

## Network exposure

By default RedForge binds to `127.0.0.1` and is reachable only from your machine.
It has **no management-API authentication**. Strict mode refuses a non-loopback
bind, even with `--yes`. Connected deployments warn before a non-loopback bind;
do not expose the API to an untrusted network.

## Troubleshooting

If install or start fails, run `redforge doctor` for a diagnosis, and see
[troubleshooting.md](troubleshooting.md).
