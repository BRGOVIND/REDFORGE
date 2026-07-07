# Release artifacts (`/downloads/`)

The website's download buttons link to files under `/downloads/` (base configurable
via `VITE_DOWNLOAD_BASE_URL`). Place the release artifacts for the current `VERSION`
in this directory so the server serves them as real files:

| File | Produced by |
|------|-------------|
| `redforge-<version>.zip` | `python scripts/build_release.py` |
| `redforge-<version>.tar.gz` | `python scripts/build_release.py` |
| `RedForge-Setup-<version>.exe` | `installers/windows/redforge.iss` (Inno Setup) |
| `RedForge-<version>-x86_64.AppImage` | `installers/linux/build-appimage.sh` |

Filenames must match those emitted by `website/src/config/downloads.ts` (they are
derived from the repo-root `VERSION`).

**These files are intentionally NOT committed to git** (they are large build outputs).
In production, copy them into the `/downloads/` path of whatever static host serves the
site (or set `VITE_DOWNLOAD_BASE_URL` to a CDN that hosts them).

If a file is missing, an SPA host returns `index.html` (HTTP 200, `text/html`) for that
path — so the browser shows the website instead of downloading. Providing the file fixes it.
