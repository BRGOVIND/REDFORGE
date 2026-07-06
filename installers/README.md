# RedForge Installers

RedForge ships as a **self-contained release folder** (built by
`scripts/build_release.py`) that runs with **Python 3.11+ and Ollama only** — no
Node.js. The archives (`.zip`, `.tar.gz`) are produced directly. The native
installers below wrap that release; they require external tooling that runs in
CI or on a maintainer's machine.

| OS | Artifact | Built by | Needs |
|----|----------|----------|-------|
| Windows | `redforge-<ver>-windows.zip` | `build_release.py` | — |
| Windows | `RedForge-Setup-<ver>.exe` | `installers/windows/redforge.iss` | [Inno Setup 6](https://jrsoftware.org/isinfo.php) |
| Linux | `redforge-<ver>.tar.gz` | `build_release.py` | — |
| Linux | `RedForge-<ver>-x86_64.AppImage` | `installers/linux/build-appimage.sh` | [`appimagetool`](https://github.com/AppImage/AppImageKit) |
| macOS | (prepared) | `.tar.gz` for now | notarized `.dmg` is future work |

## Build order

```bash
python scripts/build_release.py            # → releases/redforge-<ver>{,.zip,.tar.gz}
# Windows installer:
#   iscc installers/windows/redforge.iss
# Linux AppImage:
#   bash installers/linux/build-appimage.sh
```

## Runtime requirements (all installers)
- **Python 3.11+** (end users) — the app is a Python process.
- **Ollama** — https://ollama.com/download
- **Node.js is never required at runtime.** It is only used at *build* time to
  compile the frontend, which is then bundled into the release.
