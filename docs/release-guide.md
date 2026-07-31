# Release Guide

How to ship a RedForge version: versioning, the pipeline, channels, auto-update
and rollback.

For building installers on your own machine, see the
[Packaging Guide](packaging-guide.md).

---

## Cutting a release

```bash
python scripts/version.py --set 2.1.0     # bump VERSION + every derived literal
git commit -am "release 2.1.0"
git tag v2.1.0
git push origin main --tags               # the tag is what triggers the release
```

That is the whole procedure. The pipeline does the rest and the website updates
itself.

### Dry run

Actions → **Release** → *Run workflow*. Installers are built and uploaded as
workflow artifacts; nothing is published. Use this before any real tag.

---

## Versioning

Semantic versioning, single-sourced from the repo-root `VERSION` file. Nothing
else may contain a version literal.

```
VERSION ──┬─ redforge._version           CLI
          ├─ app.version                 backend / FastAPI
          ├─ pyproject.toml              setuptools dynamic
          ├─ vite.config.ts              __APP_VERSION__ (frontend + website)
          ├─ installers/windows/*.iss    ISPP FileRead
          └─ desktop/package.json        electron-builder (see below)
```

`desktop/package.json` is the one unavoidable exception: electron-builder reads
the version from it and bakes it into filenames, the NSIS uninstall entry, the
`.deb` control file and the update feed. It cannot read an external file, so it
is kept in lockstep instead:

```bash
python scripts/version.py --check    # fails the build on any drift
python scripts/version.py --sync     # rewrites it from VERSION
```

`--check` runs in CI on every push, so drift can never reach a release.

### Where users see the version

| Location | Source |
|----------|--------|
| Window title | `app.getVersion()` |
| Help → About RedForge | `app.getVersion()` |
| Settings → About & Updates | `GET /api/system/version` |
| Status bar | `__APP_VERSION__` |

---

## The pipeline

One workflow, `.github/workflows/release.yml`, in five stages:

```
ci ──► verify ──┬─► desktop (windows / macos / ubuntu)  ──┐
                └─► payload (source .zip / .tar.gz)     ──┴─► publish
```

| Job | Responsibility |
|-----|----------------|
| `ci` | Reuses `ci.yml` — lint, backend tests, typecheck, build. **A release cannot ship failing code.** |
| `verify` | Resolves the version/channel, enforces tag == `VERSION`, runs the drift check |
| `desktop` | Builds native installers on each OS. Publishes nothing. |
| `payload` | Source archives for CLI / headless / server users |
| `publish` | Verifies the asset set, checksums everything, generates notes, creates the Release |

Two design rules make this safe:

1. **Only `publish` touches the Release.** Build jobs run with `--publish never`.
   Three matrix jobs racing to create the same tag is how you get a half-published
   release and a corrupted update feed.
2. **`verify_release_assets.py` is a hard gate.** Every installer *and* every
   update feed must exist and exceed a floor size. A macOS job that quietly failed
   can no longer produce a release that silently omits macOS.

> This replaced two tag-triggered workflows (`release.yml` + `desktop.yml`) that
> both published to the same tag with different artifact names.

### Release notes

Generated, not hand-written — `scripts/release_notes.py` assembles the download
table, install instructions and checksums, and pulls the "what's changed" section
straight from `CHANGELOG.md`. Keep the changelog current and notes take care of
themselves.

---

## Channels

| Channel | Cut with | Who gets it |
|---------|----------|-------------|
| `stable` | `git tag v2.1.0` | everyone (default) |
| `beta` | `git tag v2.1.0-beta.1` | users who opted into Beta |
| `nightly` | Actions → Release → channel `nightly` | users who opted into Nightly |

The channel is derived from the tag's prerelease component, so a prerelease tag
can never publish to stable by accident. Nightly runs stamp
`<version>-nightly.<run_number>` so builds stay ordered.

Users switch channels in **Settings → About & Updates**, or **Help → Update
channel**. The choice persists in `desktop-state.json` and survives updates.

---

## Auto-update

electron-updater reads the `latest*.yml` feeds published alongside the installers.

```
launch ─► check (if enabled) ─► download in background ─► prompt ─► quitAndInstall
```

- Windows: `latest.yml` + the NSIS installer + `.blockmap` (delta downloads)
- macOS: `latest-mac.yml` + the zip — **dmg alone cannot auto-update**
- Linux: `latest-linux.yml` + the AppImage (`.deb` updates via the system package manager)

Auto-update is disabled in development builds.

### Rollback

Electron cannot re-install a previous version of itself in place — the running
binary is the thing being replaced. What RedForge does instead makes a bad update
recoverable rather than terminal:

1. Every launch records whether the app reached a healthy state.
2. A version that fails to boot **twice** right after an update is flagged.
3. The user is offered the previous version's installer, downloaded from its
   GitHub Release.

Workspace, models and datasets live outside the app directory, so reinstalling an
older version never touches user data. See `desktop/electron/updater.js`.

---

## Website downloads

The download buttons need no maintenance. `website/src/config/downloads.ts`:

1. renders build-time filenames immediately (works with JS disabled), then
2. queries the GitHub Releases API for the newest release and swaps in its real
   assets, matching by pattern.

Publishing a release is therefore sufficient — the site follows. If the API is
unreachable or rate-limited, the static links still resolve.

---

## Release checklist

- [ ] `CHANGELOG.md` has a section for the new version
- [ ] `python scripts/version.py --set X.Y.Z`
- [ ] CI green on `main`
- [ ] Dry run via `workflow_dispatch` for a major release
- [ ] Tag and push
- [ ] Verify all six installers + `SHA256SUMS.txt` + `latest*.yml` are attached
- [ ] Install on one real machine per platform you support
- [ ] Confirm the previous version auto-updates to it
