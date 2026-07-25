'use strict';
/**
 * Desktop configuration & path resolution.
 *
 * Resolves the backend port, the RedForge workspace/home, and portable-mode — the
 * single source of truth the rest of the main process reads. Portable mode keeps ALL
 * user data beside the executable (no registry, no writes to the user profile), so a
 * RedForge folder on a USB stick "just works".
 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const { app } = require('electron');

const DEFAULT_PORT = 8760; // desktop uses a dedicated port so it never clashes with `redforge start` (8000)
const HOST = '127.0.0.1';

/** Portable when a `portable` marker sits next to the app, or PORTABLE_EXECUTABLE_DIR is set
 *  (electron-builder's portable target exports it). */
function portableDir() {
  if (process.env.PORTABLE_EXECUTABLE_DIR) return process.env.PORTABLE_EXECUTABLE_DIR;
  try {
    const beside = path.dirname(app.getPath('exe'));
    if (fs.existsSync(path.join(beside, 'portable')) || fs.existsSync(path.join(beside, 'RedForge.portable'))) {
      return beside;
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** The RedForge home (workspace root): portable → beside exe; else a per-user data dir.
 *  Honors an explicit REDFORGE_HOME override (settings / advanced users). */
function redforgeHome() {
  if (process.env.REDFORGE_HOME) return process.env.REDFORGE_HOME;
  const portable = portableDir();
  if (portable) return path.join(portable, 'RedForge-Data');
  // per-user app data (respects OS conventions: %APPDATA%, ~/Library/Application Support, ~/.config)
  try {
    return path.join(app.getPath('userData'), 'workspace');
  } catch {
    return path.join(os.homedir(), '.redforge');
  }
}

/** User-configurable subdirectories (Settings → locations). Defaults live under home. */
function locations(home = redforgeHome()) {
  return {
    home,
    cache: path.join(home, 'cache'),
    downloads: path.join(home, 'downloads'),
    models: path.join(home, 'models'),
    datasets: path.join(home, 'datasets'),
    logs: path.join(home, 'logs'),
  };
}

function ensureDirs(loc = locations()) {
  for (const dir of Object.values(loc)) {
    try {
      fs.mkdirSync(dir, { recursive: true });
    } catch {
      /* non-fatal; surfaced by health checks */
    }
  }
  return loc;
}

module.exports = {
  HOST,
  DEFAULT_PORT,
  port() {
    const p = parseInt(process.env.REDFORGE_PORT || '', 10);
    return Number.isFinite(p) && p > 0 ? p : DEFAULT_PORT;
  },
  isPortable: () => portableDir() !== null,
  portableDir,
  redforgeHome,
  locations,
  ensureDirs,
  baseUrl(port) {
    return `http://${HOST}:${port}`;
  },
};
