'use strict';
/**
 * Backend lifecycle supervisor — the "Auto Backend".
 *
 * The user never starts FastAPI. This owns the backend process end-to-end:
 *   start → wait for /healthz → monitor → auto-restart on crash (bounded backoff) →
 *   stop on quit. It emits events the main process turns into UI (splash, status,
 *   crash dialogs). Reuses the SAME single-process backend the CLI runs (app.main:app);
 *   the desktop build prefers a bundled, Python-free binary and falls back to a local
 *   Python interpreter for development.
 */
const { spawn } = require('child_process');
const { EventEmitter } = require('events');
const http = require('http');
const path = require('path');
const fs = require('fs');
const config = require('./config');

const MAX_RESTARTS = 5;          // within the crash window before giving up
const CRASH_WINDOW_MS = 60_000;  // restarts older than this don't count against the budget
const HEALTH_TIMEOUT_MS = 60_000;
const HEALTH_POLL_MS = 5_000;

class BackendSupervisor extends EventEmitter {
  constructor({ appRoot, isPackaged, appVersion }) {
    super();
    this.appRoot = appRoot;         // repo root (dev) or resourcesPath (packaged)
    this.isPackaged = isPackaged;
    this.appVersion = appVersion || '';
    this.port = config.port();
    this.proc = null;
    this.stopping = false;
    this.restarts = [];             // timestamps of recent restarts
    this._healthTimer = null;
    this.status = 'idle';           // idle | starting | ready | crashed | stopped | failed
  }

  baseUrl() { return config.baseUrl(this.port); }

  /** Resolve how to launch the backend: bundled binary (production) or python (dev). */
  _command() {
    const exe = process.platform === 'win32' ? 'redforge-backend.exe' : 'redforge-backend';
    // Packaged: extraResources/backend/<exe>. Dev: repo backend/dist/<exe> if built.
    const candidates = [
      path.join(this.appRoot, 'backend', exe),
      path.join(this.appRoot, 'resources', 'backend', exe),
      path.join(this.appRoot, '..', 'backend', 'dist', exe),
    ];
    for (const bin of candidates) {
      if (fs.existsSync(bin)) return { cmd: bin, args: [], cwd: path.dirname(bin), bundled: true };
    }
    // Development fallback: run uvicorn via the local Python + repo backend.
    const backendDir = path.join(this.appRoot, '..', 'backend');
    const py = process.env.REDFORGE_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    return {
      cmd: py,
      args: ['-m', 'uvicorn', 'app.main:app', '--host', config.HOST, '--port', String(this.port)],
      cwd: backendDir,
      bundled: false,
    };
  }

  _env() {
    const loc = config.ensureDirs();
    const staticDir = this._staticDir();
    return {
      ...process.env,
      REDFORGE_HOME: loc.home,
      REDFORGE_PORT: String(this.port),
      // The app bundle is the authority on its own version; without this a
      // frozen backend cannot find the VERSION file and reports 0.0.0.
      REDFORGE_VERSION: this.appVersion,
      ...(staticDir ? { REDFORGE_STATIC_DIR: staticDir } : {}),
      // Keep generated ML caches out of any watched/source tree (matches app.main).
      UNSLOTH_COMPILE_LOCATION: path.join(loc.cache, 'unsloth_compiled_cache'),
      PYTHONUNBUFFERED: '1',
    };
  }

  _staticDir() {
    for (const c of [
      path.join(this.appRoot, 'backend', 'app', 'static'),
      path.join(this.appRoot, 'resources', 'backend', 'app', 'static'),
      path.join(this.appRoot, '..', 'backend', 'app', 'static'),
    ]) {
      if (fs.existsSync(path.join(c, 'index.html'))) return c;
    }
    return null;
  }

  async start() {
    if (this.proc) return;
    this.stopping = false;
    this.status = 'starting';
    this.emit('status', { status: 'starting', message: 'Starting RedForge backend…' });

    const { cmd, args, cwd, bundled } = this._command();
    this.emit('log', `launching backend (${bundled ? 'bundled' : 'python'}): ${cmd} ${args.join(' ')}`);
    this.proc = spawn(cmd, args, { cwd, env: this._env(), windowsHide: true });

    this.proc.stdout.on('data', (d) => this.emit('log', d.toString()));
    this.proc.stderr.on('data', (d) => this.emit('log', d.toString()));
    this.proc.on('error', (err) => {
      this.emit('log', `backend spawn error: ${err.message}`);
      this._onExit(-1, err.message);
    });
    this.proc.on('exit', (code) => this._onExit(code));

    try {
      await this._waitHealthy(HEALTH_TIMEOUT_MS);
      this.status = 'ready';
      this.emit('status', { status: 'ready', url: this.baseUrl() });
      this._startHealthMonitor();
    } catch (e) {
      this.status = 'failed';
      this.emit('status', { status: 'failed', message: e.message });
    }
  }

  _onExit(code, detail) {
    this._stopHealthMonitor();
    this.proc = null;
    if (this.stopping) {
      this.status = 'stopped';
      this.emit('status', { status: 'stopped' });
      return;
    }
    // Unexpected exit → crash recovery with a bounded budget.
    const now = Date.now();
    this.restarts = this.restarts.filter((t) => now - t < CRASH_WINDOW_MS);
    if (this.restarts.length >= MAX_RESTARTS) {
      this.status = 'failed';
      this.emit('status', { status: 'failed', message: `Backend crashed repeatedly (exit ${code}). ${detail || ''}`.trim() });
      return;
    }
    this.restarts.push(now);
    const backoff = Math.min(8000, 500 * 2 ** (this.restarts.length - 1));
    this.status = 'crashed';
    this.emit('status', { status: 'crashed', message: `Backend exited (code ${code}). Restarting…`, attempt: this.restarts.length });
    setTimeout(() => { if (!this.stopping) this.start(); }, backoff);
  }

  async restart() {
    await this.stop();
    this.restarts = [];
    await this.start();
  }

  stop() {
    return new Promise((resolve) => {
      this.stopping = true;
      this._stopHealthMonitor();
      if (!this.proc) return resolve();
      const p = this.proc;
      const done = () => resolve();
      p.once('exit', done);
      try {
        if (process.platform === 'win32') {
          // Kill the whole tree (uvicorn reload workers / children).
          spawn('taskkill', ['/pid', String(p.pid), '/T', '/F']);
        } else {
          p.kill('SIGTERM');
          setTimeout(() => { try { p.kill('SIGKILL'); } catch { /* */ } }, 4000);
        }
      } catch {
        resolve();
      }
      setTimeout(done, 6000); // hard cap so quit never hangs
    });
  }

  // -- health -------------------------------------------------------------
  _ping(timeout = 2000) {
    return new Promise((resolve) => {
      const req = http.get(`${this.baseUrl()}/healthz`, { timeout }, (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.on('timeout', () => { req.destroy(); resolve(false); });
    });
  }

  async _waitHealthy(timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (!this.proc) throw new Error('backend process exited before it became ready');
      if (await this._ping()) return;
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error('backend did not become healthy in time');
  }

  _startHealthMonitor() {
    this._stopHealthMonitor();
    this._healthTimer = setInterval(async () => {
      const ok = await this._ping();
      this.emit('health', { online: ok });
      if (!ok && this.status === 'ready') {
        this.emit('log', 'health check failed while running');
      }
    }, HEALTH_POLL_MS);
  }

  _stopHealthMonitor() {
    if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null; }
  }
}

module.exports = { BackendSupervisor };
