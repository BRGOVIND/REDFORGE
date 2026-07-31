# RedForge v2.0.0 — Release Readiness Report

Generated at the end of the V2.1 productization phase.

**Rule applied throughout: an item is marked ✅ only if it was actually executed
and observed.** Anything not verified on this machine is marked ⚠️ with the exact
reason, not assumed.

---

## Summary

| Verdict | Meaning |
|---------|---------|
| ✅ 17 | Verified by execution |
| ⚠️ 5 | Implemented but not verifiable here (needs CI / another OS / a real tag) |
| ❌ 1 | Known incomplete — see *Settings* |

RedForge is **releasable** with one caveat documented under *Known gaps*.

---

## Verified

### Build & test

| Item | Status | Evidence |
|------|--------|----------|
| Backend tests | ✅ | **602 passed, 0 failed** (`pytest -q`), including 20 new training-runtime and 13 environment tests |
| Lint | ✅ | `ruff check .` — all checks passed, repo-wide |
| Version single-sourced | ✅ | `scripts/version.py --check` passes; drift injected → detected → repaired → byte-identical |
| Frontend typecheck | ✅ | `tsc --noEmit` exit 0 |
| Frontend build | ✅ | `vite build` succeeded |
| Website typecheck + build | ✅ | exit 0; required fixing a pre-existing break (see *Fixed along the way*) |
| Workflow YAML | ✅ | Both workflows parse; job graph `ci → verify → (desktop ∥ payload) → publish` |

### Desktop

| Item | Status | Evidence |
|------|--------|----------|
| Windows installer | ✅ | `RedForge-v2.0.0-Setup.exe` — 146 MB, built by electron-builder |
| Windows portable | ✅ | `RedForge-v2.0.0-Portable.zip` — 190 MB |
| Packaged app runs | ✅ | Unzipped and launched: backend healthy in **3 s**, API + bundled UI served, **no Python involved** |
| Auto-update feed | ✅ | `latest.yml` generated with correct sha512 + size, referencing the Setup.exe |
| Portable mode | ✅ | `RedForge-Data/` written beside the executable (cache, models, datasets, logs, `desktop-state.json`) |
| Version display | ✅ | Installed app reports `2.0.0` via `/healthz`; window title, About dialog and Settings → About all bound to it |
| Backend lifecycle | ✅ | Auto-start verified; clean shutdown left no processes |
| Crash recovery | ✅ | Backend killed twice during testing; BackendSupervisor restarted it both times and the app stayed usable |
| Frozen worker shipped | ✅ | `_internal/app/training_runtime/worker.py` present in the bundle; managed provider reports *Worker script ok=True* |

### Training runtime

| Item | Status | Evidence |
|------|--------|----------|
| Runtime detection | ✅ | Reports `absent` with an install plan; after install reports `ready` with all 10 packages and versions |
| Hardware-aware plan | ✅ | RTX 4060 / driver CUDA 13.0 → selects **cu126**, ~2800 MB, 5–15 min |
| **Real LoRA/QLoRA via managed runtime** | ✅ | **End-to-end run completed**: 4 steps, real decreasing losses, `adapter_model.safetensors` + `adapter_config.json` written, terminal `completed` event |
| Subprocess isolation | ✅ | Training ran in the managed interpreter; the backend never imported torch |
| No silent fallback | ✅ | Unknown backend → **HTTP 400** with `available_backends` + fix, verified in both dev and the **packaged** app |
| Packaged app honesty | ✅ | Packaged build reports `default=simulation`, `real_training_available=false`, and a full "Training Runtime Required" plan — never pretends |

---

## Not verified here

| Item | Status | Why, and what would verify it |
|------|--------|-------------------------------|
| macOS DMG | ⚠️ | No macOS machine. Targets/entitlements/icons are configured; CI builds them. **First tag push is the real test.** |
| Linux AppImage + DEB | ⚠️ | No Linux machine. Same as above. |
| GitHub Release pipeline | ⚠️ | Cannot be exercised without pushing a real tag. Gates are in place (`verify_release_assets.py` proven against synthetic missing/truncated assets). |
| Auto-update install | ⚠️ | The feed is generated and correct; an actual update requires two published releases. |
| Website download links | ⚠️ | Resolver + static fallback verified in the built bundle (all six artifact names + the GitHub API endpoint present). Live resolution needs a published release. |

**Recommended before announcing:** run *Actions → Release → Run workflow* (dry run).
It builds all three platforms and uploads artifacts without publishing.

---

## Known gaps

### ❌ Settings are only partially authoritative

The brief requires "no write-only settings". **2 of 42 settings currently have
consumers**:

- `training.default_backend` — wired and verified (set → effective default changes; reset → auto)
- `training.enabled` — wired (launch returns 403 when disabled)

The other 40 are persisted and rendered but **do not yet affect runtime
behaviour**. The mechanism now exists (`settings_service.get_sync`, warmed at
startup), so each remaining setting is a small, individually-verifiable change —
but claiming them done would be false.

Highest-value remaining wirings: `performance.max_concurrent_jobs`,
`diagnostics.log_level`, `networking.hf_token`, `networking.offline`,
`hardware.vram_override_mb`, `downloads.prefer_source`, `models.dir`,
`datasets.dir`.

---

## Fixed along the way

Defects found and fixed during this phase, each verified:

1. **Packaged app reported version `0.0.0`** — `VERSION` was never staged into the
   bundle, so the version walk failed outside the repo. Fixed in two places
   (staged file + `REDFORGE_VERSION` from the shell); re-verified as 2.0.0.
2. **Silent simulation fallback** — an unknown/misspelled backend became
   `simulation`, producing a *fake* run that reported success. Now raises
   `UnknownBackendError` → HTTP 400.
3. **Launch race** — the wizard sent the literal `'simulation'` while backend
   detection was still in flight, so a fast click ran a simulated job on a capable
   GPU. Launch is now disabled until detection resolves; no client-side fallback.
4. **`DEFAULT_BACKEND` landmine** — a module constant always equal to
   `"simulation"`, one letter from the auto-detecting `default_backend()`.
   Removed.
5. **Recent Projects ordering (real product bug)** — Windows' ~15.6 ms clock
   granularity gave identically-timestamped rows (measured 7/12 collisions), so
   ordering was arbitrary and one test failed ~30% of the time. Fixed with a
   monotonic rowid tiebreak plus strictly-increasing `opened_at` on open. **0/15
   failures** after the fix.
6. **Worker would have hidden downloaded models** — it redirected `HF_HOME` into
   the runtime directory, which would have made the Model Hub's models invisible
   and re-downloaded gigabytes. Removed the redirect.
7. **Runtime probe timed out** — importing `unsloth` takes >60 s, so a healthy
   runtime was reported broken. Presence checks now use `find_spec` +
   `importlib.metadata` without importing.
8. **`desktop/build/` was gitignored** — the root `build/` rule silently excluded
   electron-builder's buildResources, so `icon.png` and the macOS entitlements
   would never have reached CI, breaking the mac build.
9. **Website build was broken on `main`** — `@vitejs/plugin-react@6` requires
   vite ^8 while the tree pins vite ^7. Moved the plugin to ^5.
10. **Two conflicting release pipelines** (previous phase) — `release.yml` and
    `desktop.yml` both published to the same tag with different artifact names.
    Consolidated into one.

---

## Release procedure

```bash
python scripts/version.py --set 2.1.0
git commit -am "release 2.1.0"
git tag v2.1.0 && git push origin main --tags
```

The pipeline gates on tests, verifies the complete asset set, checksums
everything, generates notes from `CHANGELOG.md`, and publishes one release. See
the [Release Guide](release-guide.md).
