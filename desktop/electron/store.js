'use strict';
/**
 * Tiny JSON store for desktop-level state.
 *
 * Deliberately NOT the app's Settings system: these are values the main process
 * needs *before* the backend is up (update channel, update/rollback bookkeeping,
 * window bounds). Everything user-facing still lives in the backend Settings API.
 *
 * Portable installs keep this beside the executable, so a portable copy carries
 * its own preferences and leaves no trace on the host.
 */
const fs = require('fs');
const path = require('path');
const config = require('./config');

const FILE = 'desktop-state.json';

function file() {
  return path.join(config.redforgeHome(), FILE);
}

function readAll() {
  try {
    const raw = fs.readFileSync(file(), 'utf8');
    const data = JSON.parse(raw);
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {}; // missing or corrupt → defaults; never fatal
  }
}

function writeAll(data) {
  const target = file();
  try {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    // Write-then-rename so a crash mid-write can't leave a truncated file.
    const tmp = `${target}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
    fs.renameSync(tmp, target);
    return true;
  } catch {
    return false;
  }
}

module.exports = {
  file,
  all: readAll,
  get(key, fallback = null) {
    const value = readAll()[key];
    return value === undefined ? fallback : value;
  },
  set(key, value) {
    const data = readAll();
    data[key] = value;
    return writeAll(data);
  },
  merge(patch) {
    const data = { ...readAll(), ...patch };
    return writeAll(data);
  },
};
