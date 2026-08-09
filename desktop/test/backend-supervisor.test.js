'use strict';
/**
 * Main-process guards that keep a freshly installed build from loading a
 * PREVIOUS build's UI. Both regressions here shipped in 2.0.3.
 *
 * 1. Port collision. The backend port is fixed, so "something answered
 *    /healthz" is not the same as "our backend answered". An older RedForge
 *    holding the port meant the new app happily loaded that build's shell,
 *    whose code-split chunks do not exist in the new install.
 * 2. Upgrade detection. The Electron HTTP cache lives in the user profile and
 *    survives upgrades, so a version change has to be detectable in order to
 *    drop a poisoned cache.
 *
 * `electron` cannot be required outside an Electron runtime, so it is stubbed
 * before the modules under test are loaded. Nothing else is faked: the health
 * probe talks to a real HTTP server over a real socket.
 */
const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const os = require('node:os');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');

const HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'redforge-desktop-test-'));
let stubVersion = '2.0.4';

// Stub `electron` for config.js / updater.js. Must be installed before require.
const realLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'electron') {
    return {
      app: {
        getVersion: () => stubVersion,
        getPath: () => HOME,
        isPackaged: false,
      },
      dialog: {},
      shell: {},
    };
  }
  return realLoad(request, parent, isMain);
};

process.env.REDFORGE_HOME = HOME;

const { BackendSupervisor } = require('../electron/backend');
const store = require('../electron/store');
const { UpdateManager } = require('../electron/updater');

/** A stand-in backend that answers /healthz with whatever version we choose. */
function fakeBackend(payload) {
  const server = http.createServer((req, res) => {
    if (req.url !== '/healthz') {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(payload);
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

function supervisorOn(port, appVersion) {
  process.env.REDFORGE_PORT = String(port);
  const s = new BackendSupervisor({ appRoot: __dirname, isPackaged: false, appVersion });
  s.proc = { pid: -1 };  // _waitHealthy refuses to poll without a spawned process
  return s;
}

test('rejects an older RedForge already holding the port', async () => {
  const { server, port } = await fakeBackend(JSON.stringify({ version: '2.0.3', status: 'online' }));
  try {
    const s = supervisorOn(port, '2.0.4');
    await assert.rejects(
      () => s._waitHealthy(4000),
      (err) => {
        assert.match(err.message, /already served by RedForge 2\.0\.3/);
        assert.match(err.message, /2\.0\.4/);
        return true;
      },
      'a foreign backend must be refused, not silently adopted',
    );
  } finally {
    server.close();
  }
});

test('accepts our own backend — the guard must not reject a valid one', async () => {
  const { server, port } = await fakeBackend(JSON.stringify({ version: '2.0.4', status: 'online' }));
  try {
    const s = supervisorOn(port, '2.0.4');
    await s._waitHealthy(4000);   // resolves; throwing here would fail the test
  } finally {
    server.close();
  }
});

test('accepts a backend that reports no version rather than guessing', async () => {
  // Deliberately lenient: only an explicit MISMATCH is treated as foreign, so an
  // unexpected /healthz shape can never make the app unlaunchable.
  const { server, port } = await fakeBackend('not json at all');
  try {
    const s = supervisorOn(port, '2.0.4');
    await s._waitHealthy(4000);
  } finally {
    server.close();
  }
});

test('no version check when the app version is unknown', async () => {
  const { server, port } = await fakeBackend(JSON.stringify({ version: '1.0.0' }));
  try {
    const s = supervisorOn(port, undefined);
    await s._waitHealthy(4000);
  } finally {
    server.close();
  }
});

test('recordLaunch reports an upgrade exactly once', () => {
  fs.rmSync(path.join(HOME, 'desktop-state.json'), { force: true });
  const updates = new UpdateManager({ isDev: true, getWindow: () => null, log: () => {} });

  stubVersion = '2.0.3';
  const first = updates.recordLaunch();
  assert.equal(first.changed, false, 'a first install has no cache to invalidate');
  assert.equal(store.get('installedVersion'), '2.0.3');

  const again = updates.recordLaunch();
  assert.equal(again.changed, false, 'relaunching the same version must not clear the cache');

  stubVersion = '2.0.4';
  const upgraded = updates.recordLaunch();
  assert.equal(upgraded.changed, true, '2.0.3 -> 2.0.4 must invalidate the poisoned cache');
  assert.equal(upgraded.from, '2.0.3');
  assert.equal(upgraded.to, '2.0.4');

  const settled = updates.recordLaunch();
  assert.equal(settled.changed, false, 'the cache is cleared once per upgrade, not every launch');
});

test.after(() => {
  Module._load = realLoad;
  fs.rmSync(HOME, { recursive: true, force: true });
});
