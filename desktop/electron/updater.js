'use strict';
/**
 * Auto-update + post-update recovery.
 *
 * Update flow (electron-updater against the GitHub Releases feed):
 *   check → download → prompt → quitAndInstall
 *
 * Channels: stable | beta | nightly. The channel selects which `*.yml` feed the
 * updater reads, so beta/nightly users get prereleases and stable users never do.
 * The choice persists in desktop-state.json and survives updates.
 *
 * Rollback — and an honest note about its limits. Electron cannot re-install a
 * previous version of itself in place: the running binary is the thing being
 * replaced. What we CAN do, and do here, is make a bad update recoverable
 * instead of terminal:
 *
 *   • Every launch records whether the app reached a healthy state.
 *   • A version that fails to boot repeatedly *right after an update* is flagged.
 *   • The user is then offered the previous version's installer, downloaded from
 *     the GitHub Release for that exact version.
 *
 * That turns "the update bricked my install" into a two-click recovery, without
 * pretending we have transactional rollback.
 */
const { app, dialog, shell } = require('electron');
const store = require('./store');

const REPO = 'https://github.com/BRGOVIND/REDFORGE';
const CHANNELS = ['stable', 'beta', 'nightly'];
// Two consecutive failed boots on a freshly-installed version is a real problem,
// not a transient one (a single failure can be a busy port or a slow disk).
const BOOT_FAILURES_BEFORE_ROLLBACK = 2;

class UpdateManager {
  constructor({ isDev, getWindow, log }) {
    this.isDev = isDev;
    this.getWindow = getWindow;
    this.log = log || (() => {});
    this.updater = null;
    this.state = 'idle'; // idle | checking | available | downloading | ready | none | error
    this.info = null;
    this.error = null;
  }

  channel() {
    const c = store.get('updateChannel', 'stable');
    return CHANNELS.includes(c) ? c : 'stable';
  }

  setChannel(channel) {
    if (!CHANNELS.includes(channel)) throw new Error(`unknown channel: ${channel}`);
    store.set('updateChannel', channel);
    if (this.updater) this._applyChannel();
    return channel;
  }

  autoCheckEnabled() {
    return store.get('autoCheckUpdates', true) !== false;
  }

  setAutoCheck(on) {
    store.set('autoCheckUpdates', !!on);
    return !!on;
  }

  // -- boot bookkeeping -----------------------------------------------------

  /** Call at startup, before the backend is launched. Detects a fresh update. */
  recordLaunch() {
    const current = app.getVersion();
    const installed = store.get('installedVersion', null);
    if (installed && installed !== current) {
      // We just moved to a new version — remember what we came from.
      store.merge({
        installedVersion: current,
        previousVersion: installed,
        bootFailures: 0,
        updatedAt: new Date().toISOString(),
      });
      this.log(`updated: ${installed} → ${current}`);
    } else if (!installed) {
      store.merge({ installedVersion: current, bootFailures: 0 });
    }
  }

  /** Call once the app is genuinely usable. Marks this version known-good. */
  recordHealthy() {
    store.merge({ bootFailures: 0, lastGoodVersion: app.getVersion() });
  }

  /**
   * Call when the backend could not be brought up.
   * Returns true if the caller should offer a rollback.
   */
  recordBootFailure() {
    const failures = (store.get('bootFailures', 0) || 0) + 1;
    store.set('bootFailures', failures);
    const previous = store.get('previousVersion', null);
    const justUpdated = previous && previous !== app.getVersion();
    return Boolean(justUpdated && failures >= BOOT_FAILURES_BEFORE_ROLLBACK);
  }

  /** Offer to reinstall the last version that worked. */
  async offerRollback() {
    const previous = store.get('previousVersion', null);
    if (!previous) return false;
    const choice = dialog.showMessageBoxSync({
      type: 'warning',
      title: 'RedForge is not starting correctly',
      message: `RedForge ${app.getVersion()} has failed to start ${store.get('bootFailures', 0)} times.`,
      detail:
        `The previous version (${previous}) was working.\n\n` +
        'You can download and reinstall it — your workspace, models and datasets ' +
        'are stored separately and will not be affected.',
      buttons: [`Download ${previous}`, 'Open release page', 'Ignore'],
      defaultId: 0,
      cancelId: 2,
    });
    if (choice === 2) return false;
    // Reset so the prompt doesn't reappear on every subsequent launch.
    store.set('bootFailures', 0);
    const url =
      choice === 0
        ? `${REPO}/releases/download/v${previous}/${this._installerName(previous)}`
        : `${REPO}/releases/tag/v${previous}`;
    await shell.openExternal(url);
    return true;
  }

  /** Installer filename for a version — mirrors desktop/package.json artifactName. */
  _installerName(version) {
    switch (process.platform) {
      case 'win32':
        return `RedForge-v${version}-Setup.exe`;
      case 'darwin':
        return `RedForge-v${version}-${process.arch === 'arm64' ? 'arm64' : 'x64'}.dmg`;
      default:
        return `RedForge-v${version}-x64.AppImage`;
    }
  }

  // -- electron-updater -----------------------------------------------------

  start() {
    if (this.isDev) {
      this.log('auto-update disabled in development');
      return;
    }
    try {
      ({ autoUpdater: this.updater } = require('electron-updater'));
    } catch {
      this.log('electron-updater not present — updates disabled for this build');
      return;
    }

    this.updater.autoDownload = true;
    this.updater.autoInstallOnAppQuit = true;
    this.updater.logger = { info: this.log, warn: this.log, error: this.log, debug: () => {} };
    this._applyChannel();
    this._wire();

    if (this.autoCheckEnabled()) {
      this.check().catch(() => {});
    }
  }

  _applyChannel() {
    const channel = this.channel();
    // `allowPrerelease` lets the updater see GitHub prereleases at all; `channel`
    // selects which feed file it reads (latest.yml / beta.yml / nightly.yml).
    this.updater.allowPrerelease = channel !== 'stable';
    this.updater.channel = channel === 'stable' ? 'latest' : channel;
    this.log(`update channel: ${channel} (feed: ${this.updater.channel})`);
  }

  _send(event, data = {}) {
    const win = this.getWindow && this.getWindow();
    if (win && !win.isDestroyed()) {
      win.webContents.send('update', { event, channel: this.channel(), ...data });
    }
  }

  _wire() {
    const u = this.updater;
    u.on('checking-for-update', () => { this.state = 'checking'; this._send('checking'); });
    u.on('update-not-available', () => { this.state = 'none'; this._send('none'); });
    u.on('update-available', (info) => {
      this.state = 'available';
      this.info = { version: info.version, releaseDate: info.releaseDate };
      this._send('available', this.info);
    });
    u.on('download-progress', (p) => {
      this.state = 'downloading';
      this._send('progress', {
        percent: Math.round(p.percent),
        transferred: p.transferred,
        total: p.total,
        bytesPerSecond: p.bytesPerSecond,
      });
    });
    u.on('update-downloaded', (info) => {
      this.state = 'ready';
      this.info = { version: info.version };
      this._send('downloaded', this.info);
      this._promptInstall(info.version);
    });
    u.on('error', (err) => {
      this.state = 'error';
      this.error = String((err && err.message) || err);
      this.log(`update error: ${this.error}`);
      this._send('error', { message: this.error });
    });
  }

  _promptInstall(version) {
    const choice = dialog.showMessageBoxSync({
      type: 'info',
      title: 'Update ready',
      message: `RedForge ${version} is ready to install.`,
      detail: 'RedForge will close, install the update, and reopen.',
      buttons: ['Restart & update', 'Later'],
      defaultId: 0,
      cancelId: 1,
    });
    if (choice === 0) this.install();
  }

  async check({ notifyWhenUpToDate = false } = {}) {
    if (!this.updater) {
      if (notifyWhenUpToDate) {
        dialog.showMessageBoxSync({
          type: 'info',
          title: 'Updates unavailable',
          message: 'This build does not support automatic updates.',
          detail: this.isDev
            ? 'Automatic updates are disabled in development builds.'
            : `Download the latest version from ${REPO}/releases/latest`,
          buttons: ['OK'],
        });
      }
      return null;
    }
    try {
      const result = await this.updater.checkForUpdates();
      if (notifyWhenUpToDate && this.state === 'none') {
        dialog.showMessageBoxSync({
          type: 'info',
          title: 'You are up to date',
          message: `RedForge ${app.getVersion()} is the latest ${this.channel()} release.`,
          buttons: ['OK'],
        });
      }
      return result;
    } catch (err) {
      this.log(`update check failed: ${err && err.message}`);
      if (notifyWhenUpToDate) {
        dialog.showMessageBoxSync({
          type: 'error',
          title: 'Could not check for updates',
          message: 'RedForge could not reach the update server.',
          detail: `${(err && err.message) || err}\n\nCheck your connection, or download manually from ${REPO}/releases/latest`,
          buttons: ['OK'],
        });
      }
      return null;
    }
  }

  install() {
    if (this.updater && this.state === 'ready') this.updater.quitAndInstall();
  }

  status() {
    return {
      state: this.state,
      channel: this.channel(),
      autoCheck: this.autoCheckEnabled(),
      currentVersion: app.getVersion(),
      info: this.info,
      error: this.error,
      supported: Boolean(this.updater),
    };
  }
}

module.exports = { UpdateManager, CHANNELS };
