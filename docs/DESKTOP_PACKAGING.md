# RedForge Desktop — Native Packaging

RedForge ships as a **native desktop application** (its own window, managed backend,
auto-update) — the Docker-Desktop / LM-Studio experience — via an **Electron shell**
in `desktop/`. The shell supervises the existing single-process backend and loads the
existing web app; it does **not** reimplement the product (first-run, hardware/GPU
detection, dependency checks, and the Model Hub already live in the app + Health Engine).

## Architecture
```
Electron main (desktop/electron/main.js)
  ├─ BackendSupervisor (backend.js)  ── spawns & supervises the backend
  │     start → wait /healthz → monitor → auto-restart on crash (bounded backoff) → stop on quit
  ├─ Splash window (splash.html)     ── shown while the backend boots
  ├─ Main window                     ── loads http://127.0.0.1:8760  (own app window)
  ├─ Native dialogs                  ── backend failure / retry / open-logs / quit
  └─ electron-updater                ── "update available → download → restart to update"
        ▲
  Backend = the SAME app.main:app the CLI runs, bundled as a Python-free binary.
```

- **Auto Backend** — the user never starts FastAPI. The supervisor resolves a bundled
  `redforge-backend` binary (production) or falls back to a local `python -m uvicorn`
  (development), waits for `/healthz`, monitors health, and **auto-restarts on crash**
  with exponential backoff; repeated crashes raise a professional error dialog
  (Retry / Open logs / Quit). Quit stops the backend cleanly (whole process tree).
- **Dedicated port 8760** so the desktop app never clashes with a CLI `redforge start` (8000).

## Targets (electron-builder → `desktop/package.json`)
| Platform | Target | Output |
|---|---|---|
| Windows | `nsis` | `RedForge-Setup-<ver>-x64.exe` (installer, shortcuts, uninstaller) |
| Windows | `portable` + `zip` | `RedForge-Portable-<ver>-x64.exe` / `.zip` |
| macOS | `dmg` | `RedForge-<ver>-x64.dmg`, `-arm64.dmg` |
| Linux | `AppImage` | `RedForge-<ver>-x64.AppImage` |
| Linux | `deb` | `RedForge-<ver>-x64.deb` |

Icons reuse `installers/windows/*.ico` and `installers/linux/redforge.png`; macOS needs
`desktop/build/icon.icns` (generate from the PNG — a one-time build step).

## Build & run
```bash
# Dev (uses local Python backend, no freeze):
cd desktop && npm install && REDFORGE_PYTHON=python npm start

# Full production build (what CI runs):
python desktop/scripts/stage-backend.py     # 1) build frontend  2) PyInstaller-freeze backend  3) assemble resources/backend
cd desktop && npm ci && npm run dist        # 4) electron-builder → installers in desktop/release-build/
```
`stage-backend.py` deliberately **excludes the heavy ML stack** (torch/unsloth/…) from
the frozen backend so the installer stays small; the simulation-first workflow runs out
of the box, and real GPU training (experimental) installs those deps separately.

## Auto-update, signing, CI
- **CI**: `.github/workflows/desktop.yml` — a 3-OS matrix builds installers; on a `v*`
  tag it `--publish`es to the GitHub Release (the electron-updater feed). `workflow_dispatch`
  builds artifacts without publishing.
- **Code signing** (optional, secret-gated): `CSC_LINK` / `CSC_KEY_PASSWORD` (Windows +
  mac cert), `APPLE_ID` / `APPLE_APP_SPECIFIC_PASSWORD` / `APPLE_TEAM_ID` (mac notarization).
  Builds are unsigned until those secrets are set.

## Portable mode & settings
- **Portable**: the `portable` target (or a `portable` marker beside the exe) stores ALL
  data in `RedForge-Data/` next to the executable — **no registry, no user-profile writes**.
- **Workspace locations** (home / cache / downloads / models / datasets / logs) resolve in
  `config.js` and are overridable via `REDFORGE_HOME` — the settings UI can bind to these
  through the preload bridge (`window.redforge.appInfo()` / `openPath`).

## Error handling
Native dialogs for: backend failed to start (with the log tail), repeated crashes,
and launch failure. Runtime/GPU/disk/permission problems continue to surface through the
in-app Health Engine + Hardware Compatibility Engine.

## Honest status (what is / isn't done here)
- **Implemented & syntax-verified**: the Electron shell (main/backend/config/preload/splash),
  the full electron-builder config for all five targets, the PyInstaller staging pipeline,
  and the CI workflow.
- **Not producible in this environment**: the actual signed installers — they require the
  Electron toolchain, each target OS, and signing secrets, so they are built by the CI
  workflow above (or locally on each OS). Nothing here was run/packaged locally.
- **Deferred (guided, not automated)**: one-click installation of external runtimes
  (CUDA / Ollama / LM Studio / llama.cpp) is surfaced as detected-with-links via the Health
  Engine rather than silently auto-installed — silent system-level installs are unsafe to
  automate and platform-specific. `desktop/build/icon.icns` must be generated for macOS.
```
