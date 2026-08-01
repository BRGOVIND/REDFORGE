# Release Guide

How to ship a RedForge version: versioning, the pipeline, channels, auto-update
and rollback.

For building installers on your own machine, see the
[Packaging Guide](packaging-guide.md).

---

## Cutting a release

```bash
python scripts/version.py --set 2.1.0     # updates EVERY version location
git commit -am "release 2.1.0"
git tag v2.1.0
git push origin main
git push origin v2.1.0                    # the tag is what triggers the release
```

That is the whole procedure. **Never edit a version by hand anywhere** — the bump
command is the only supported way to change it. The pipeline does the rest and the
website updates itself.

Optional, and worth doing: add a `## [2.1.0]` section to `CHANGELOG.md` before
tagging. `release_notes.py` publishes it as the release body; without it the
release simply has no "What's changed" section (the workflow warns, it does not
fail).

### If the tag and VERSION disagree

The release aborts on purpose:

```
tag v2.0.1 does not match VERSION 2.0.0
```

This means the tag was pushed without bumping first. Fix it by bumping properly
and re-pointing the tag — do **not** disable the check:

```bash
python scripts/version.py --set 2.0.1
git commit -am "release 2.0.1"
git tag -f v2.0.1                         # move the tag onto the bump commit
git push origin main
git push origin v2.0.1 --force
```

### Dry run

Actions → **Release** → *Run workflow*. Installers are built and uploaded as
workflow artifacts; nothing is published. Use this before any real tag.

---

## Versioning

Semantic versioning, single-sourced from the repo-root `VERSION` file.
`scripts/version.py` is the **only** version authority.

```
VERSION
  │
  ├─ derived at runtime — nothing to sync, verified by --check
  │    redforge._version            CLI
  │    app.version                  backend / FastAPI
  │    pyproject.toml               setuptools dynamic
  │    cli/pyproject.toml           setuptools dynamic
  │    frontend/vite.config.ts      __APP_VERSION__
  │    website/vite.config.ts       __APP_VERSION__
  │    installers/windows/*.iss     ISPP FileRead
  │    installers/linux/*.sh        cat VERSION
  │    desktop/electron/*           app.getVersion()
  │
  └─ sinks — a literal is unavoidable, written by --set/--sync
       desktop/package.json         electron-builder reads it directly
       desktop/package-lock.json    npm mirrors package.json
       website/package.json
       website/package-lock.json
       SECURITY.md                  "currently **X.Y.Z**"
```

`desktop/package.json` is the reason sinks exist at all: electron-builder reads
the version from it and bakes it into installer filenames, the NSIS uninstall
entry, the `.deb` control file and the update feed. It cannot read an external
file.

### Commands

| Command | Effect |
|---------|--------|
| `python scripts/version.py` | print the current version |
| `python scripts/version.py --list` | show every location and its value (audit view) |
| `python scripts/version.py --set X.Y.Z` | bump `VERSION`, then update every sink |
| `python scripts/version.py --sync` | rewrite every sink from `VERSION` (idempotent) |
| `python scripts/version.py --check` | fail if any location has drifted |
| `python scripts/version.py --check --release` | as above, plus a changelog warning |

`--check` runs in CI on every push and again in the release workflow, so drift
can never reach a release.

### Adding a new version location

Add one entry to `SINKS` in `scripts/version.py` — `PackageJsonSink`,
`PackageLockSink` or `RegexSink`. `--set`, `--sync`, `--check` and `--list` all
pick it up with no further changes. If instead the new location can *derive* the
version at runtime, prefer that and add a guard to `_FORBIDDEN` so a literal can
never creep back in.

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

- [ ] `CHANGELOG.md` has a section for the new version (optional; warning only)
- [ ] `python scripts/version.py --set X.Y.Z` — never edit a version by hand
- [ ] `python scripts/version.py --check` passes locally
- [ ] CI green on `main`
- [ ] Dry run via `workflow_dispatch` for a major release
- [ ] Tag and push
- [ ] Verify all six installers + `SHA256SUMS.txt` + `latest*.yml` are attached
- [ ] Install on one real machine per platform you support
- [ ] Confirm the previous version auto-updates to it
