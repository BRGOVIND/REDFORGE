'use strict';
/**
 * RedForge Desktop — Electron main process.
 *
 * Owns the native app experience the way Docker Desktop / LM Studio do:
 *   • a splash window while the supervised backend boots,
 *   • the main window pointed at the local backend (its own app window, not a browser),
 *   • the backend lifecycle (auto-start/stop/restart/crash-recovery) via BackendSupervisor,
 *   • native error dialogs (backend failed, port busy, permissions, disk),
 *   • auto-update with channels + post-update recovery (UpdateManager),
 *   • a single-instance lock and a clean quit.
 *
 * The first-run flow, hardware/GPU detection, dependency checks and Model Hub already
 * live in the web app + backend — the desktop shell boots them, it does not
 * reimplement them.
 */
const { app, BrowserWindow, dialog, shell, ipcMain, Menu, clipboard } = require('electron');
const path = require('path');
const fs = require('fs');
const config = require('./config');
const store = require('./store');
const { BackendSupervisor } = require('./backend');
const { UpdateManager, CHANNELS } = require('./updater');

const isDev = !app.isPackaged;
const appRoot = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..');

let splash = null;
let win = null;
let supervisor = null;
let updates = null;
let pendingOpenFile = null;   // .redforge file the OS asked us to open
const logBuffer = [];

// Single instance — a second launch focuses the existing window.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', (_e, argv) => {
    const file = fileFromArgv(argv);
    if (file) openProjectFile(file);
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });
  app.whenReady().then(main).catch(fatal);
}

// macOS delivers file-open through an event rather than argv.
app.on('open-file', (event, filePath) => {
  event.preventDefault();
  openProjectFile(filePath);
});

function log(line) {
  const s = String(line).trimEnd();
  if (!s) return;
  logBuffer.push(s);
  if (logBuffer.length > 1000) logBuffer.shift();
  if (splash && !splash.isDestroyed()) splash.webContents.send('status', { log: s });
}

function fileFromArgv(argv) {
  const hit = (argv || []).find((a) => typeof a === 'string' && a.toLowerCase().endsWith('.redforge'));
  return hit && fs.existsSync(hit) ? hit : null;
}

/** Hand a .redforge file to the web app once it is ready to receive it. */
function openProjectFile(filePath) {
  pendingOpenFile = filePath;
  if (win && !win.isDestroyed()) {
    win.webContents.send('open-file', { path: filePath });
    pendingOpenFile = null;
    win.focus();
  }
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
  const bounds = store.get('windowBounds', null);
  win = new BrowserWindow({
    width: bounds?.width ?? 1400,
    height: bounds?.height ?? 900,
    x: bounds?.x, y: bounds?.y,
    minWidth: 1024, minHeight: 680, show: false,
    backgroundColor: '#0b0b0d',
    // Version in the window title — one of the three places it must appear
    // (window title, About, in-app Settings).
    title: `RedForge ${app.getVersion()}`,
    icon: iconPath(),
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  Menu.setApplicationMenu(buildMenu());
  win.loadURL(url);
  // The web app sets document.title per route; keep our version suffix visible.
  win.on('page-title-updated', (e, title) => {
    e.preventDefault();
    win.setTitle(`${title} — RedForge ${app.getVersion()}`);
  });
  win.once('ready-to-show', () => {
    win.show();
    if (splash && !splash.isDestroyed()) splash.destroy();
    splash = null;
    if (pendingOpenFile) openProjectFile(pendingOpenFile);
  });
  // Open external links in the system browser, never inside the app window.
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (/^https?:\/\//.test(target) && !target.startsWith(url)) { shell.openExternal(target); return { action: 'deny' }; }
    return { action: 'allow' };
  });
  // A renderer crash should be recoverable, not a dead window.
  win.webContents.on('render-process-gone', (_e, details) => {
    log(`renderer gone: ${details.reason}`);
    const choice = dialog.showMessageBoxSync({
      type: 'error', title: 'RedForge stopped responding',
      message: 'The RedForge window crashed.',
      detail: `Reason: ${details.reason}`,
      buttons: ['Reload', 'Quit'], defaultId: 0, cancelId: 1,
    });
    if (choice === 0) win.reload(); else app.quit();
  });
  const saveBounds = () => {
    if (win && !win.isDestroyed() && !win.isMinimized() && !win.isMaximized()) {
      store.set('windowBounds', win.getBounds());
    }
  };
  win.on('resize', saveBounds);
  win.on('move', saveBounds);
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

  updates = new UpdateManager({ isDev, getWindow: () => win, log });
  updates.recordLaunch();          // detect "we just updated" before anything can fail

  pendingOpenFile = fileFromArgv(process.argv);
  createSplash();

  supervisor = new BackendSupervisor({
    appRoot,
    isPackaged: app.isPackaged,
    appVersion: app.getVersion(),
  });
  supervisor.on('log', log);
  supervisor.on('status', (s) => {
    if (splash && !splash.isDestroyed()) splash.webContents.send('status', s);
    if (win && !win.isDestroyed()) win.webContents.send('backend-status', s);
    if (s.status === 'ready') {
      updates.recordHealthy();     // this version boots — clears the rollback counter
      if (!win) createMainWindow(s.url);
    }
    if (s.status === 'failed') void handleBackendFailure(s.message);
  });
  supervisor.on('health', (h) => { if (win && !win.isDestroyed()) win.webContents.send('backend-health', h); });

  registerIpc();
  await supervisor.start();
  updates.start();
}

/**
 * The backend could not be started. If this keeps happening immediately after an
 * update, offer the previous version before showing the generic failure dialog.
 */
async function handleBackendFailure(message) {
  if (updates && updates.recordBootFailure()) {
    const rolledBack = await updates.offerRollback();
    if (rolledBack) { app.quit(); return; }
  }
  showBackendFailure(message);
}

function showBackendFailure(message) {
  const detail = logBuffer.slice(-25).join('\n');
  const choice = dialog.showMessageBoxSync({
    type: 'error', title: 'RedForge could not start',
    message: 'The RedForge backend failed to start.',
    detail: `${message || 'Unknown error.'}\n\nRecent log:\n${detail}`,
    buttons: ['Retry', 'Open logs', 'Copy diagnostics', 'Quit'], defaultId: 0, cancelId: 3,
  });
  if (choice === 0) supervisor.restart();
  else if (choice === 1) shell.openPath(config.locations().logs);
  else if (choice === 2) { clipboard.writeText(diagnostics()); showBackendFailure(message); }
  else app.quit();
}

/** A support-ready snapshot: versions, paths, and the tail of the backend log. */
function diagnostics() {
  const loc = config.locations();
  return [
    `RedForge ${app.getVersion()}`,
    `Electron ${process.versions.electron} · Node ${process.versions.node} · Chrome ${process.versions.chrome}`,
    `Platform ${process.platform} ${process.arch} · ${require('os').release()}`,
    `Portable: ${config.isPortable()}`,
    `Update channel: ${updates ? updates.channel() : 'n/a'}`,
    `Backend status: ${supervisor ? supervisor.status : 'n/a'} @ ${supervisor ? supervisor.baseUrl() : 'n/a'}`,
    `Home: ${loc.home}`,
    `Logs: ${loc.logs}`,
    '',
    '--- recent backend log ---',
    logBuffer.slice(-60).join('\n'),
  ].join('\n');
}

function registerIpc() {
  ipcMain.handle('backend:status', () => ({ status: supervisor?.status, url: supervisor?.baseUrl() }));
  ipcMain.handle('backend:restart', () => supervisor?.restart());
  ipcMain.handle('app:info', () => ({
    version: app.getVersion(),
    electron: process.versions.electron,
    node: process.versions.node,
    chrome: process.versions.chrome,
    platform: process.platform,
    arch: process.arch,
    portable: config.isPortable(),
    locations: config.locations(),
    channel: updates ? updates.channel() : 'stable',
  }));
  ipcMain.handle('app:openPath', (_e, target) => shell.openPath(target));
  ipcMain.handle('app:diagnostics', () => diagnostics());
  ipcMain.handle('app:copyDiagnostics', () => { clipboard.writeText(diagnostics()); return true; });
  ipcMain.handle('app:chooseDirectory', async (_e, { title, defaultPath } = {}) => {
    const result = await dialog.showOpenDialog(win, {
      title: title || 'Choose a folder',
      defaultPath: defaultPath || config.locations().home,
      properties: ['openDirectory', 'createDirectory'],
    });
    return result.canceled ? null : result.filePaths[0];
  });
  ipcMain.handle('update:status', () => updates?.status() ?? null);
  ipcMain.handle('update:check', () => updates?.check({ notifyWhenUpToDate: true }));
  ipcMain.handle('update:install', () => updates?.install());
  ipcMain.handle('update:setChannel', (_e, channel) => updates?.setChannel(channel));
  ipcMain.handle('update:setAutoCheck', (_e, on) => updates?.setAutoCheck(on));
}

function showAbout() {
  const loc = config.locations();
  dialog.showMessageBoxSync({
    type: 'info',
    title: 'About RedForge',
    message: `RedForge ${app.getVersion()}`,
    detail: [
      'The local AI engineering platform.',
      '',
      `Electron ${process.versions.electron} · Node ${process.versions.node}`,
      `${process.platform} ${process.arch}`,
      `Update channel: ${updates ? updates.channel() : 'stable'}`,
      `Mode: ${config.isPortable() ? 'Portable' : 'Installed'}`,
      `Workspace: ${loc.home}`,
    ].join('\n'),
    buttons: ['Copy diagnostics', 'OK'],
    defaultId: 1,
    cancelId: 1,
  }) === 0 && clipboard.writeText(diagnostics());
}

function buildMenu() {
  const channelItems = CHANNELS.map((c) => ({
    label: c[0].toUpperCase() + c.slice(1),
    type: 'radio',
    checked: updates ? updates.channel() === c : c === 'stable',
    click: () => {
      updates.setChannel(c);
      Menu.setApplicationMenu(buildMenu());
    },
  }));

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
        { type: 'separator' },
        { label: 'Open logs folder', click: () => shell.openPath(config.locations().logs) },
        { label: 'Open workspace folder', click: () => shell.openPath(config.locations().home) },
        { label: 'Copy diagnostics', click: () => clipboard.writeText(diagnostics()) },
      ],
    },
    {
      label: 'Help',
      submenu: [
        { label: 'Check for updates…', click: () => updates && updates.check({ notifyWhenUpToDate: true }) },
        { label: 'Update channel', submenu: channelItems },
        { type: 'separator' },
        { label: 'Documentation', click: () => shell.openExternal('https://redforge.site/docs') },
        { label: 'Report an issue', click: () => shell.openExternal('https://github.com/BRGOVIND/REDFORGE/issues/new/choose') },
        { label: 'RedForge website', click: () => shell.openExternal('https://redforge.site') },
        { type: 'separator' },
        { label: 'About RedForge', click: showAbout },
      ],
    },
  ];
  return Menu.buildFromTemplate(template);
}

function fatal(err) {
  dialog.showErrorBox('RedForge failed to launch', String((err && err.stack) || err));
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
