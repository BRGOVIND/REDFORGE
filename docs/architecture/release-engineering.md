# Release Engineering

How RedForge goes from a git tag to verifiable, downloadable artifacts. This is
**process and tooling only** — it adds no user-facing features and does not
change how the app runs (still Python + Ollama, single process, no Node.js at
runtime).

---

## 1. Single source of truth for the version

The repo-root **`VERSION`** file is the *only* place a version literal lives.
Everything else derives from it:

```
VERSION  (e.g. 1.2.0)
  │
  ├─ redforge._version.read_version()         CLI, standard library only
  │     └─ redforge.__version__  ─►  cli.py, `redforge version`
  │
  ├─ app.version.read_version()               backend
  │     └─ app.__version__  ─►  FastAPI(version=…), /docs, OpenAPI
  │
  ├─ pyproject.toml            [tool.setuptools.dynamic] version = {file = "VERSION"}
  ├─ cli/pyproject.toml        version = {attr = "redforge.__version__"}
  ├─ vite.config.ts            reads ../VERSION → define __APP_VERSION__ → bundle
  ├─ installers/windows/redforge.iss   ISPP FileRead(VERSION)  (CI passes /DAppVersion)
  └─ installers/linux/build-appimage.sh   cat VERSION
```

Both resolvers walk up from their own file to find `VERSION`, so they work
**in the source tree and in a packaged release** (where `cli/` and `backend/`
sit directly under the staging root). The CLI resolver additionally honours
`REDFORGE_HOME` and falls back to installed-distribution metadata, so a
`pip install redforge` with no `VERSION` file still reports correctly.

### Guard against drift — `scripts/version.py`

```bash
python scripts/version.py           # print the version
python scripts/version.py --check   # fail if any literal crept back in
```

`--check` is the enforcement mechanism. It:

1. greps the packaging manifests, `main.py`, the CLI modules, and the `.iss`
   for a re-introduced hardcoded `X.Y.Z`;
2. asserts `frontend/package.json` has **no** `version` field (it's a private
   package; the build injects `__APP_VERSION__` instead);
3. imports the CLI and backend resolvers in subprocesses and asserts both
   resolve to exactly the `VERSION` string.

It runs as the first CI job and gates the release. `backend/tests/test_version.py`
covers the same invariants inside the test suite.

### Cutting a new version

Edit `VERSION`, run `python scripts/version.py --check`, commit, then tag:

```bash
echo 1.3.0 > VERSION
python scripts/version.py --check
git commit -am "release: 1.3.0"
git tag v1.3.0 && git push origin main v1.3.0
```

Nothing else needs editing. That is the entire point.

---

## 2. Build system (unchanged interface)

`scripts/build_release.py` is the same builder as before, now sourcing its
version from `scripts/version.py` and emitting checksums. It does not require
Node.js to *run* the result — only to *build* it.

```
npm run build (frontend)
  → copy dist into  backend/app/static
  → stage backend + cli + datasets + docs + launchers
  → archive  redforge-<version>.zip  and  .tar.gz
  → write    SHA256SUMS.txt
```

```bash
python scripts/build_release.py                 # full build
python scripts/build_release.py --skip-frontend # reuse frontend/dist
```

### Checksums — `scripts/checksums.py`

Standard `sha256sum` format (`<hex>  <name>`, basenames only) so a download
verifies with the platform-native tool:

```bash
sha256sum -c SHA256SUMS.txt          # Linux
shasum -a 256 -c SHA256SUMS.txt      # macOS
certutil -hashfile <file> SHA256     # Windows
```

The builder checksums the two archives it produces; the release workflow reruns
it across **all** artifacts (archives + installers) collected from every runner,
so the published `SHA256SUMS.txt` covers everything in the release.

---

## 3. Continuous Integration — `.github/workflows/ci.yml`

Runs on every push to `main`, every PR, and on demand. Four parallel jobs:

| Job | What it enforces |
|-----|------------------|
| **version** | `python scripts/version.py --check` — no version drift |
| **backend** | `pip install .` resolves the dynamic version == `VERSION`; then `pytest` |
| **frontend** | `npm ci` → `tsc --noEmit` → `vite build`; asserts `VERSION` is in the bundle |

The backend suite never touches a live provider — the runtime is faked through
the `generate_fn` / `judge_fn` seams (`backend/tests/conftest.py`), so CI needs
no Ollama and no network.

---

## 4. Release pipeline — `.github/workflows/release.yml`

Triggered by pushing a `v*` tag (or manually via `workflow_dispatch` for a
dry run). Stages:

```
verify ──► package ──┬──► windows-installer ──┐
                     └──► linux-appimage ──────┴──► publish
```

1. **verify** — reads `VERSION`, runs the drift guard, and asserts the pushed
   tag equals `VERSION` (`v1.2.0` ⇒ `VERSION` must be `1.2.0`). A mismatched
   tag fails the release before anything is built.
2. **package** — builds the cross-platform payload (`.zip` + `.tar.gz`) on
   Linux and uploads it as a workflow artifact.
3. **windows-installer** — restages on `windows-latest`, compiles
   `redforge.iss` with Inno Setup (`ISCC /DAppVersion=<version>`), uploads the
   `.exe`.
4. **linux-appimage** — restages on Ubuntu, runs `build-appimage.sh` with
   `appimagetool`, uploads the `.AppImage`.
5. **publish** — downloads every artifact, computes `SHA256SUMS.txt` over all
   of them, and creates a **draft** GitHub Release (tag name, `RELEASE_NOTES.md`
   body) with the archives, both installers, and the checksums attached.

The release is created as a **draft** on purpose: a human reviews the artifacts
and checksums, edits notes, then publishes. `permissions: contents: write` is
the only elevated scope, and only the `publish` job uses it.

### Runner prerequisites

- **Windows installer** assumes Inno Setup 6 at the default
  `Program Files (x86)\Inno Setup 6\ISCC.exe`. `windows-latest` ships it; if a
  future image drops it, add a `choco install innosetup` step.
- **AppImage** installs `libfuse2` and fetches `appimagetool` from AppImageKit
  continuous releases.
- macOS is **not** built here (see `installers/README.md`): the `.tar.gz` is the
  macOS distribution for now; a notarized `.dmg` is future work.

---

## 5. What is deliberately *not* done

- No version bump automation (semantic-release etc.). Editing `VERSION` is a
  conscious one-line human step; the guard makes it safe.
- No artifact signing / notarization yet — checksums only.
- No PyPI/npm publish — RedForge ships as self-contained archives + installers,
  not as language-registry packages.

---

## 6. Local pre-release checklist

```bash
python scripts/version.py --check          # version single-sourced
(cd backend && python -m pytest -q)        # backend green
(cd frontend && npx tsc --noEmit)          # types green
(cd frontend && npx vite build)            # bundle builds
python scripts/build_release.py            # archives + SHA256SUMS.txt
```

If all five pass, tagging `v$(cat VERSION)` will produce a clean release.
