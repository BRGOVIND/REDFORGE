'use strict';
/**
 * Invalidate Chromium's HTTP cache when the UI it holds is from another version.
 *
 * Why this exists
 * ---------------
 * The desktop app always loads its UI from the same origin
 * (http://127.0.0.1:<port>), and Chromium's cache lives in the Electron profile,
 * which outlives upgrades. RedForge 2.0.3 served `index.html` with no
 * `Cache-Control`, so browsers applied heuristic freshness and reused the
 * previous version's app shell. That stale shell asks for code-split chunks by
 * their old content hashes, the new build does not have them, and every route it
 * had not already cached fails with "Failed to fetch dynamically imported
 * module". The backend now sends `no-cache` on the shell, which stops this
 * happening again — but it CANNOT repair a profile that is already poisoned,
 * because the browser never contacts the server to discover the new header. Only
 * dropping the cache does that.
 *
 * Where the marker lives, and why it matters
 * ------------------------------------------
 * The first version of this check keyed off `installedVersion` in
 * desktop-state.json, which lives under `config.redforgeHome()`. For an INSTALLED
 * build that happens to sit inside the Electron profile, so it worked. For a
 * PORTABLE build `redforgeHome()` is `<portableDir>/RedForge-Data` — beside the
 * executable — while the Chromium profile stays in the per-user data directory.
 * A freshly downloaded portable 2.0.4 therefore read `installedVersion = null`,
 * concluded "first run, nothing to invalidate", and inherited the poisoned cache
 * an installed 2.0.3 had left behind.
 *
 * The fix is not a portable special case. It is to put the marker where the thing
 * it describes lives: this file records the version that last populated THIS
 * Chromium profile, inside that profile. Installed, portable and development
 * builds all then answer the same question the same way, because the marker and
 * the cache can never be separated.
 *
 * Scope: `clearCache()` touches the HTTP cache only. Cookies, localStorage,
 * IndexedDB, and everything under the RedForge workspace are untouched.
 */
const { app, session } = require('electron');
const fs = require('fs');
const path = require('path');

const MARKER = 'ui-cache-version.json';

// Chromium's on-disk HTTP caches. Their presence is what distinguishes "a
// genuinely new profile" (nothing to clear) from "a profile an older RedForge
// already used" (must clear, even though it carries no marker).
const CACHE_DIRS = ['Cache', 'Code Cache'];

function profileDir() {
  return app.getPath('userData');
}

function markerFile() {
  return path.join(profileDir(), MARKER);
}

/** The version that last populated this profile, or null if unknown. */
function readMarker() {
  try {
    const data = JSON.parse(fs.readFileSync(markerFile(), 'utf8'));
    return data && typeof data.version === 'string' ? data.version : null;
  } catch {
    return null; // missing or corrupt — treat as unknown, which errs toward clearing
  }
}

function writeMarker(version) {
  const target = markerFile();
  try {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    // Write-then-rename: a crash mid-write must not leave a marker that claims
    // a version whose cache was never actually installed.
    const tmp = `${target}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ version, updatedAt: new Date().toISOString() }, null, 2), 'utf8');
    fs.renameSync(tmp, target);
    return true;
  } catch {
    return false;
  }
}

/** Has any RedForge already cached anything into this profile? */
function profileHasCache() {
  return CACHE_DIRS.some((dir) => {
    try {
      return fs.readdirSync(path.join(profileDir(), dir)).length > 0;
    } catch {
      return false;
    }
  });
}

/**
 * Clear the HTTP cache if this profile was last written by a different version.
 *
 * Runs before any window loads a URL. Never throws: a warm cache is a
 * performance detail and must not be able to stop the app booting.
 *
 * The marker is written ONLY after the cache has actually been dropped. If the
 * clear fails, the profile keeps its old marker and the next launch tries again,
 * so a transient failure cannot permanently strand a user on a poisoned cache.
 *
 * @returns {Promise<{cleared: boolean, reason: string, from: string|null, to: string}>}
 */
async function invalidateIfVersionChanged({ log = () => {} } = {}) {
  const current = app.getVersion();
  let seen = null;
  try {
    seen = readMarker();
  } catch {
    seen = null;
  }

  if (seen === current) {
    return { cleared: false, reason: 'unchanged', from: seen, to: current };
  }

  // A profile with no marker AND no cache is genuinely new — there is nothing to
  // invalidate, so record the version and skip the work.
  if (seen === null && !profileHasCache()) {
    writeMarker(current);
    return { cleared: false, reason: 'first-run', from: null, to: current };
  }

  try {
    await session.defaultSession.clearCache();
  } catch (err) {
    log(`could not clear the UI cache (will retry next launch): ${err.message}`);
    return { cleared: false, reason: 'failed', from: seen, to: current };
  }

  if (!writeMarker(current)) {
    // The cache IS clear, so this launch is correct; we just could not remember
    // it. Next launch clears again — wasteful, never wrong.
    log('cleared the UI cache but could not record the version');
    return { cleared: true, reason: 'cleared-unrecorded', from: seen, to: current };
  }
  log(`cleared the UI cache: profile was last written by ${seen ?? 'an unknown version'}, now ${current}`);
  return { cleared: true, reason: 'cleared', from: seen, to: current };
}

module.exports = { invalidateIfVersionChanged, markerFile, readMarker, MARKER };
