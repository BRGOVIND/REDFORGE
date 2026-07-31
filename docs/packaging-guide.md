# Packaging Guide

How RedForge becomes a downloadable desktop application, and how to build the
installers yourself.

For cutting an actual release, see the [Release Guide](release-guide.md).

---

## What ships

A RedForge installer contains everything an end user needs. **No Python, no
Node.js, no terminal, no repository clone.**

```
RedForge.app / RedForge.exe
├── Electron shell            desktop/electron/   — window, menus, updates, lifecycle
└── resources/backend/        the frozen FastAPI backend
    ├── redforge-backend(.exe)   PyInstaller onedir build
    ├── app/static/              the built React UI
    ├── datasets/                bundled attack + benchmark data
    └── VERSION                  so the app reports its real version
```

At launch the Electron main process starts `redforge-backend`, waits for
`/healthz`, and points the window at `http://127.0.0.1:8760`. The user only ever
sees an application window.

---

## Build pipeline

Three stages. `desktop/scripts/stage-backend.py` owns the first two.

| # | Stage | What happens |
|---|-------|--------------|
| 1 | **Frontend** | `npm ci && npm run build` in `frontend/`, output copied to `backend/app/static` |
| 2 | **Freeze** | PyInstaller bundles the backend into a self-contained binary |
| 3 | **Package** | `electron-builder` wraps the shell + backend into installers |

Heavy GPU dependencies (`torch`, `unsloth`, `bitsandbytes`, `transformers`, …)
are **excluded** from the freeze. They are only needed for experimental real
training, are installed separately, and would add many gigabytes to every
download.

### Build locally

```bash
# One-time
pip install pyinstaller -r backend/requirements.lock
cd desktop && npm install && cd ..

# Stage the backend (frontend build + freeze + assemble)
python desktop/scripts/stage-backend.py --require-frozen

# Package for the current platform
cd desktop
npx electron-builder --publish never          # all targets for this OS
npx electron-builder --win --publish never    # just Windows
npx electron-builder --dir                    # unpacked, fastest for testing
```

Artifacts land in `desktop/release-build/`.

**`--require-frozen` is not optional in CI.** Without it, a failed freeze still
produces an installer — one that silently falls back to a system Python the end
user does not have. The flag turns that into a build failure.

### Faster iteration

```bash
# Re-assemble only (skip the slow frontend build and freeze)
python desktop/scripts/stage-backend.py --skip-frontend --skip-freeze

# Run the shell against a local Python backend — no freeze at all
cd desktop && npm start
```

---

## Targets

Configured in `desktop/package.json` → `build`.

| Platform | Target | Artifact |
|----------|--------|----------|
| Windows | `nsis` | `RedForge-v<version>-Setup.exe` |
| Windows | `zip` | `RedForge-v<version>-Portable.zip` |
| macOS | `dmg` | `RedForge-v<version>-x64.dmg`, `-arm64.dmg` |
| macOS | `zip` | required by the updater — dmg alone cannot auto-update |
| Linux | `AppImage` | `RedForge-v<version>-x64.AppImage` |
| Linux | `deb` | `RedForge-v<version>-amd64.deb` |

Naming comes from `artifactName` patterns. The Windows platform-level pattern
serves the zip (portable) target, while `nsis.artifactName` overrides it for the
installer — that is how one platform produces two differently-named artifacts.

> Changing any `artifactName` means also updating
> `scripts/verify_release_assets.py`, `scripts/release_notes.py`, and
> `website/src/config/downloads.ts`, which all encode the same names.

---

## Icons and build resources

`desktop/build/` is electron-builder's `buildResources` directory:

- `icon.png` (512×512) — macOS `.icns` and any missing platform icon are derived
  from it automatically.
- `entitlements.mac.plist` — required by the hardened runtime. The bundled backend
  is a child process with unsigned libraries, so it needs the JIT and
  library-validation exceptions declared there.

Regenerate every branding asset from one source image:

```bash
python scripts/generate_icons.py path/to/source.png
```

PyInstaller scratch deliberately lives in `desktop/.pyinstaller/`, **not**
`desktop/build/`, so it cannot collide with build resources.

---

## Code signing

Unsigned builds work but show OS warnings (SmartScreen on Windows, Gatekeeper on
macOS). Signing is entirely driven by CI secrets — no config change needed.

| Secret | Purpose |
|--------|---------|
| `CSC_LINK` | base64 certificate (`.pfx` / `.p12`) |
| `CSC_KEY_PASSWORD` | its password |
| `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | macOS notarization |

When absent, the release workflow builds unsigned and still succeeds.

---

## Portable mode

The Windows zip is portable. RedForge stores **all** data beside the executable
when either condition holds:

- a file named `portable` sits next to the executable, or
- `PORTABLE_EXECUTABLE_DIR` is set.

Data then goes to `RedForge-Data/` beside the binary — nothing is written to the
user profile or registry, so a USB stick works. See `desktop/electron/config.js`.

---

## Troubleshooting

**`Cannot create symbolic link … winCodeSign` (Windows)**
electron-builder's signing toolchain contains macOS symlinks, and Windows needs
Developer Mode or admin rights to extract them. Either enable Developer Mode, or
extract once manually — the two failing files are macOS-only `.dylib` symlinks
that Windows builds never use:

```powershell
$c = "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign"
& desktop\node_modules\7zip-bin\win\x64\7za.exe x -y "$c\<hash>.7z" "-o$c\winCodeSign-2.6.0"
```

CI runners are unaffected.

**The packaged app reports version `0.0.0`**
`VERSION` is missing from `resources/backend/`. `stage-backend.py` copies it and
`verify()` fails the build when it is absent; the desktop shell also passes
`REDFORGE_VERSION` to the backend as a second line of defence.

**The app starts but the window is blank**
The backend did not become healthy. Help → Backend → Open logs folder, or run the
frozen binary directly:

```bash
desktop/resources/backend/redforge-backend      # then open http://127.0.0.1:8760/healthz
```

**`resources/backend` cannot be deleted while re-staging**
An antivirus scan or a stale `redforge-backend` process is holding it. Kill any
leftover process and retry.
