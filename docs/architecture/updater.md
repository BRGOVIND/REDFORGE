# Updater (`redforge update`)

`redforge update` upgrades a RedForge installation to the newest GitHub release,
verifying integrity before it touches a single file and rolling back on any
failure. User data is never at risk. Implemented in `cli/redforge/updater.py`
(standard library only: `urllib`, `zipfile`, `hashlib`, `shutil`).

## Flow

1. **Git checkout?** If the install is a git clone, update via `git pull` and
   stop (releases are for packaged installs).
2. **Check GitHub Releases** — `GET /repos/<repo>/releases/latest`
   (`REDFORGE_REPO`, default `BRGOVIND/REDFORGE`).
3. **Compare versions** — `parse_version` reduces `vX.Y.Z[-pre]` to a comparable
   tuple where a final release outranks its own prerelease. If the latest is not
   newer than the local `VERSION`, stop ("already up to date"). `--check` reports
   availability without installing.
4. **Select assets** — the `redforge-*.zip` archive and `SHA256SUMS.txt`.
5. **Download** both to a temp dir.
6. **Verify SHA-256** — the archive's digest must match its line in
   `SHA256SUMS.txt`. On mismatch, abort immediately — **nothing has changed yet.**
7. **Extract** the archive to a staging dir.
8. **Apply** with rollback (below).
9. Report the new version and the backup location, and suggest
   `redforge repair` to refresh dependencies.

Integrity is checked *before* any file is replaced, so a corrupted or tampered
download can never partially overwrite an installation.

## Safe replace & rollback (`apply_release`)

The install root contains the release payload (`backend/`, `cli/`, `datasets/`,
`docs/`, `VERSION`, launchers) plus **user data** that must survive:

- `~/.redforge/` (venv, settings, logs) — outside the payload, never touched.
- `backend/redforge.db` (evaluation history) — inside a payload dir, so it is
  explicitly held aside and restored into the new tree.

The swap, per payload item:

1. Copy `backend/redforge.db` to a hold area (before anything is removed).
2. For each payload entry present in the release: **back up** the current target
   into `~/.redforge/backups/<timestamp>/`, record it as backed-up, remove it,
   then move the new version into place.
3. Restore the held DB into the new `backend/`.

If **any** step raises, `_rollback` restores every backed-up item — including the
one that was mid-replacement (it is recorded as backed-up *before* removal, which
is the subtlety that makes rollback lossless). Because a backed-up payload dir
contains the DB that was in it, restoring it also restores history. The exception
then propagates, and the previous installation is intact.

## What is preserved

| Data | Location | How |
|------|----------|-----|
| Evaluation history | `backend/redforge.db` | held aside, restored into new tree; also present in the backup |
| Settings / venv / logs | `~/.redforge/` | outside the payload — never modified |
| Previous version | `~/.redforge/backups/<ts>/` | full backup of every replaced item |

## Failure modes (all safe)

- **No network / GitHub unreachable** → error + manual-download link; no changes.
- **Checksum mismatch** → abort before replacing anything.
- **Missing archive or SHA256SUMS** → abort with a manual-download link.
- **Filesystem error mid-apply** → automatic rollback to the prior install.

## Tests

`backend/tests/test_updater.py` (offline) covers version comparison, checksum
verification, asset selection, a successful swap that preserves the DB, and a
forced mid-swap failure that must roll back losslessly.
