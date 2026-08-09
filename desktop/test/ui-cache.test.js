'use strict';
/**
 * UI cache invalidation across upgrades — installed, portable and development.
 *
 * The bug these guard: a profile can hold the app shell of a PREVIOUS version.
 * Because the shell names code-split chunks by content hash, running a new build
 * against an old cached shell asks the backend for chunks that no longer exist,
 * and every route the user had not already visited fails to load.
 *
 * The subtle half is portable mode. `desktop-state.json` (which records the
 * installed version) lives under `redforgeHome()` — beside the executable for a
 * portable copy — while the Chromium profile stays in the per-user data dir. Any
 * check keyed off desktop-state therefore sees "first run" for a fresh portable
 * download and skips invalidation, even though the profile it is about to use
 * was poisoned by an older installed build. The marker must live with the cache,
 * which is what these tests pin down.
 *
 * `electron` cannot be required outside an Electron runtime, so `app` and
 * `session` are stubbed. The marker file, the cache-directory probe and the
 * failure/retry logic are all exercised for real against a temp profile.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');

let profile;              // stands in for app.getPath('userData')
let version = '2.0.4';
let clearCalls = 0;
let clearShouldFail = false;

const realLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'electron') {
    return {
      app: { getVersion: () => version, getPath: () => profile, isPackaged: true },
      session: {
        defaultSession: {
          clearCache: async () => {
            clearCalls += 1;
            if (clearShouldFail) throw new Error('disk is busy');
          },
          // Present so a test can prove we never call it.
          clearStorageData: async () => {
            throw new Error('clearStorageData must never be called');
          },
        },
      },
    };
  }
  return realLoad(request, parent, isMain);
};

const uiCache = require('../electron/ui-cache');

/** A profile that an older RedForge has already used: has a cache, has user data. */
function poisonedProfile(markerVersion) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rf-profile-'));
  fs.mkdirSync(path.join(dir, 'Cache', 'Cache_Data'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'Cache', 'Cache_Data', 'data_0'), 'cached shell');
  fs.mkdirSync(path.join(dir, 'Local Storage'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'Local Storage', 'leveldb.ldb'), 'user settings');
  fs.mkdirSync(path.join(dir, 'IndexedDB'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'IndexedDB', 'store'), 'user data');
  fs.writeFileSync(path.join(dir, 'Cookies'), 'cookies');
  if (markerVersion) {
    fs.writeFileSync(path.join(dir, uiCache.MARKER), JSON.stringify({ version: markerVersion }));
  }
  return dir;
}

function reset(dir) {
  profile = dir;
  clearCalls = 0;
  clearShouldFail = false;
}

function userDataIntact(dir) {
  return fs.existsSync(path.join(dir, 'Local Storage', 'leveldb.ldb'))
    && fs.existsSync(path.join(dir, 'IndexedDB', 'store'))
    && fs.existsSync(path.join(dir, 'Cookies'));
}

test('installed 2.0.3 -> 2.0.4 clears the poisoned cache', async () => {
  // An installed 2.0.3 profile carries a cache but no marker: the marker did not
  // exist before 2.0.4, so every real upgrading user looks exactly like this.
  reset(poisonedProfile(null));
  version = '2.0.4';
  const r = await uiCache.invalidateIfVersionChanged();
  assert.equal(r.cleared, true, 'an upgrade over an existing cache must clear it');
  assert.equal(clearCalls, 1);
  assert.equal(uiCache.readMarker(), '2.0.4', 'the profile must record what wrote it');
});

test('portable 2.0.3 -> 2.0.4 clears it too, with no desktop-state to consult', async () => {
  // The regression. A freshly downloaded portable build has NO desktop-state.json
  // (it lives beside the executable, which is new), yet it opens the same
  // Chromium profile an installed 2.0.3 poisoned. Keying off installedVersion
  // reported "first run" here and skipped the clear.
  reset(poisonedProfile(null));
  version = '2.0.4';
  const r = await uiCache.invalidateIfVersionChanged();
  assert.equal(r.cleared, true, 'portable must not inherit a poisoned cache');
  assert.equal(r.from, null, 'there is no prior marker — the cache itself is the evidence');
  assert.equal(clearCalls, 1);
});

test('a genuinely first portable run does not clear anything', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rf-profile-new-'));
  reset(dir);
  version = '2.0.4';
  const r = await uiCache.invalidateIfVersionChanged();
  assert.equal(r.cleared, false);
  assert.equal(r.reason, 'first-run');
  assert.equal(clearCalls, 0, 'nothing has been cached yet — clearing would be pointless work');
  assert.equal(uiCache.readMarker(), '2.0.4', 'but the version is recorded for next time');
});

test('same-version relaunch never clears', async () => {
  reset(poisonedProfile('2.0.4'));
  version = '2.0.4';
  for (let i = 0; i < 3; i += 1) {
    const r = await uiCache.invalidateIfVersionChanged();
    assert.equal(r.cleared, false);
    assert.equal(r.reason, 'unchanged');
  }
  assert.equal(clearCalls, 0, 'a warm cache must survive ordinary relaunches');
});

test('the upgrade clears exactly once, not on every later launch', async () => {
  reset(poisonedProfile('2.0.3'));
  version = '2.0.4';
  const first = await uiCache.invalidateIfVersionChanged();
  const second = await uiCache.invalidateIfVersionChanged();
  const third = await uiCache.invalidateIfVersionChanged();
  assert.equal(first.cleared, true);
  assert.equal(second.cleared, false);
  assert.equal(third.cleared, false);
  assert.equal(clearCalls, 1, 'exactly one clear per upgrade');
});

test('a failed clear stays eligible for retry', async () => {
  // The flag must NOT be consumed before the work succeeds, or one transient
  // failure strands the user on a poisoned cache permanently.
  reset(poisonedProfile('2.0.3'));
  version = '2.0.4';
  clearShouldFail = true;
  const failed = await uiCache.invalidateIfVersionChanged();
  assert.equal(failed.cleared, false);
  assert.equal(failed.reason, 'failed');
  assert.equal(uiCache.readMarker(), '2.0.3', 'the marker must not advance on failure');

  clearShouldFail = false;
  const retried = await uiCache.invalidateIfVersionChanged();
  assert.equal(retried.cleared, true, 'the next launch must try again');
  assert.equal(uiCache.readMarker(), '2.0.4');
  assert.equal(clearCalls, 2);
});

test('a corrupt marker is treated as unknown and errs toward clearing', async () => {
  const dir = poisonedProfile(null);
  fs.writeFileSync(path.join(dir, uiCache.MARKER), '{not json');
  reset(dir);
  version = '2.0.4';
  const r = await uiCache.invalidateIfVersionChanged();
  assert.equal(r.cleared, true);
  assert.equal(uiCache.readMarker(), '2.0.4');
});

test('user data is never touched', async () => {
  reset(poisonedProfile('2.0.3'));
  version = '2.0.4';
  await uiCache.invalidateIfVersionChanged();
  assert.ok(userDataIntact(profile),
    'cookies, localStorage and IndexedDB must survive a cache invalidation');
});

test('a downgrade also invalidates', async () => {
  // Rolling back to a previous build leaves the newer shell cached; the same
  // mismatch, so the same treatment.
  reset(poisonedProfile('2.0.4'));
  version = '2.0.3';
  const r = await uiCache.invalidateIfVersionChanged();
  assert.equal(r.cleared, true);
  assert.equal(uiCache.readMarker(), '2.0.3');
});

test.after(() => {
  Module._load = realLoad;
});
