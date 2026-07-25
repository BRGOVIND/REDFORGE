'use strict';
/**
 * RedForge Desktop — Electron main process.
 *
 * Owns the native app experience the way Docker Desktop / LM Studio do:
 *   • a splash window while the supervised backend boots,
 *   • the main window pointed at the local backend (its own app window, not a browser),
 *   • the backend lifecycle (auto-start/stop/restart/crash-recovery) via BackendSupervisor,
 *   • native error dialogs (backend failed, port busy, permissions, disk),
 *   • auto-update (electron-updater),
 *   • a single-instance lock and a clean quit.
 *
 * The first-run flow, hardware/GPU detection, dependency checks and Model Hub already
 * live in the web app + backend Health Engine — the desktop shell boots them, it does
 * not reimplement them.
 */
const { app, BrowserWindow, dialog, shell, ipcMain, Menu } = require('electron');
const path = require('path');
const config = require('./config');
const { BackendSupervisor } = require('./backend');

const isDev = !app.isPackaged;
const appRoot = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..');

let splash = null;
let win = null;
let supervisor = null;
let updater = null;
const logBuffer = [];

// Single instance — a second launch focuses the existing window.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });
  app.whenReady().then(main).catch(fatal);
}

function log(line) {
  const s = String(line).trimEnd();
  if (!s) return;
  logBuffer.push(s);
  if (logBuffer.length > 1000) logBuffer.shift();
  if (splash && !splash.isDestroyed()) splash.webContents.send('status', { log: s });
}

function createSplash() {
  splash = new BrowserWindow({
    width: 440, height: 300, frame: false, resizable: false, center: true, show: true,
    backgroundColor: '#0b0b0d',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  });
  splash.loadFile(path.join(__dirname, 'splash.html'));
}

function createMainWindow(url) {
  win = new BrowserWindow({
    width: 1400, height: 900, minWidth: 1024, minHeight: 680, show: false,
    backgroundColor: '#0b0b0d', title: 'RedForge',
    icon: iconPath(),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  Menu.setApplicationMenu(buildMenu());
  win.loadURL(url);
  win.once('ready-to-show', () => {
    win.show();
    if (splash && !splash.isDestroyed()) splash.destroy();
    splash = null;
  });
  // Open external links in the system browser, never inside the app window.
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (/^https?:\/\//.test(target) && !target.startsWith(url)) { shell.openExternal(target); return { action: 'deny' }; }
    return { action: 'allow' };
  });
  win.on('closed', () => { win = null; });
}

function iconPath() {
  const rel = process.platform === 'win32'
    ? path.join('installers', 'windows', 'desktop.ico')
    : path.join('installers', 'linux', 'redforge.png');
  return path.join(appRoot, isDev ? '..' : '', rel);
}

async function main() {
  config.ensureDirs();
  createSplash();

  supervisor = new BackendSupervisor({ appRoot, isPackaged: app.isPackaged });
  supervisor.on('log', log);
  supervisor.on('status', (s) => {
    if (splash && !splash.isDestroyed()) splash.webContents.send('status', s);
    if (win && !win.isDestroyed()) win.webContents.send('backend-status', s);
    if (s.status === 'ready' && !win) createMainWindow(s.url);
    if (s.status === 'failed') showBackendFailure(s.message);
  });
  supervisor.on('health', (h) => { if (win && !win.isDestroyed()) win.webContents.send('backend-health', h); });

  registerIpc();
  await supervisor.start();
  setupAutoUpdate();
}

function showBackendFailure(message) {
  const detail = logBuffer.slice(-25).join('\n');
  const choice = dialog.showMessageBoxSync({
    type: 'error', title: 'RedForge could not start',
    message: 'The RedForge backend failed to start.',
    detail: `${message || 'Unknown error.'}\n\nRecent log:\n${detail}`,
    buttons: ['Retry', 'Open logs', 'Quit'], defaultId: 0, cancelId: 2,
  });
  if (choice === 0) supervisor.restart();
  else if (choice === 1) shell.openPath(config.locations().logs);
  else app.quit();
}

function registerIpc() {
  ipcMain.handle('backend:status', () => ({ status: supervisor?.status, url: supervisor?.baseUrl() }));
  ipcMain.handle('backend:restart', () => supervisor?.restart());
  ipcMain.handle('app:info', () => ({
    version: app.getVersion(), platform: process.platform, arch: process.arch,
    portable: config.isPortable(), locations: config.locations(),
  }));
  ipcMain.handle('app:openPath', (_e, target) => shell.openPath(target));
  ipcMain.handle('update:check', () => updater && updater.checkForUpdates());
  ipcMain.handle('update:install', () => updater && updater.quitAndInstall());
}

function setupAutoUpdate() {
  if (isDev) return;
  try {
    ({ autoUpdater: updater } = require('electron-updater'));
  } catch {
    return; // electron-updater not installed in this build
  }
  updater.autoDownload = true;
  updater.autoInstallOnAppQuit = true;
  const send = (event, data) => win && !win.isDestroyed() && win.webContents.send('update', { event, ...data });
  updater.on('update-available', (i) => send('available', { version: i.version }));
  updater.on('download-progress', (p) => send('progress', { percent: Math.round(p.percent) }));
  updater.on('update-downloaded', (i) => {
    send('downloaded', { version: i.version });
    const c = dialog.showMessageBoxSync({
      type: 'info', title: 'Update ready',
      message: `RedForge ${i.version} is ready to install.`,
      buttons: ['Restart & Update', 'Later'], defaultId: 0, cancelId: 1,
    });
    if (c === 0) updater.quitAndInstall();
  });
  updater.on('error', (e) => log(`update error: ${e && e.message}`));
  updater.checkForUpdatesAndNotify().catch(() => {});
}

function buildMenu() {
  const template = [
    ...(process.platform === 'darwin' ? [{ role: 'appMenu' }] : []),
    { role: 'fileMenu' },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        { label: 'Reload', accelerator: 'CmdOrCtrl+R', click: () => win && win.reload() },
        { role: 'toggleDevTools' }, { type: 'separator' }, { role: 'resetZoom' },
        { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' }, { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Backend',
      submenu: [
        { label: 'Restart backend', click: () => supervisor && supervisor.restart() },
        { label: 'Open logs folder', click: () => shell.openPath(config.locations().logs) },
        { label: 'Open workspace folder', click: () => shell.openPath(config.locations().home) },
      ],
    },
    {
      label: 'Help',
      submenu: [
        { label: 'Check for updates…', click: () => updater && updater.checkForUpdates() },
        { label: 'RedForge website', click: () => shell.openExternal('https://redforge.dev') },
        { role: 'about' },
      ],
    },
  ];
  return Menu.buildFromTemplate(template);
}

function fatal(err) {
  dialog.showErrorBox('RedForge failed to launch', String(err && err.stack || err));
  app.quit();
}

app.on('before-quit', async (e) => {
  if (supervisor && supervisor.proc) {
    e.preventDefault();
    await supervisor.stop();
    app.exit(0);
  }
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('activate', () => { if (supervisor && supervisor.status === 'ready' && !win) createMainWindow(supervisor.baseUrl()); });
