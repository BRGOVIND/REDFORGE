'use strict';
/**
 * Preload — a small, safe bridge (contextIsolation on, nodeIntegration off).
 *
 * Exposes ONLY what the renderer needs: app info, backend status/restart, update
 * controls, diagnostics and a native folder picker. No Node/fs access leaks to the
 * web app, and every channel is an explicit allow-list entry.
 *
 * The web app detects the desktop shell with `window.redforge != null` and shows
 * desktop-only affordances (update channel, portable mode, native paths) when it
 * is present. Running in a plain browser it simply hides them.
 */
const { contextBridge, ipcRenderer } = require('electron');

/** Subscribe helper that returns an unsubscribe function (React-friendly). */
function on(channel, cb) {
  const listener = (_e, data) => cb(data);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('redforge', {
  isDesktop: true,
  appInfo: () => ipcRenderer.invoke('app:info'),
  diagnostics: () => ipcRenderer.invoke('app:diagnostics'),
  copyDiagnostics: () => ipcRenderer.invoke('app:copyDiagnostics'),
  openPath: (target) => ipcRenderer.invoke('app:openPath', target),
  chooseDirectory: (opts) => ipcRenderer.invoke('app:chooseDirectory', opts),

  backend: {
    status: () => ipcRenderer.invoke('backend:status'),
    restart: () => ipcRenderer.invoke('backend:restart'),
    onStatus: (cb) => on('backend-status', cb),
    onHealth: (cb) => on('backend-health', cb),
  },

  update: {
    status: () => ipcRenderer.invoke('update:status'),
    check: () => ipcRenderer.invoke('update:check'),
    install: () => ipcRenderer.invoke('update:install'),
    setChannel: (channel) => ipcRenderer.invoke('update:setChannel', channel),
    setAutoCheck: (on_) => ipcRenderer.invoke('update:setAutoCheck', on_),
    onEvent: (cb) => on('update', cb),
  },

  // A .redforge file was opened from the OS (double-click / "Open with").
  onOpenFile: (cb) => on('open-file', cb),

  // splash-only channel
  onSplashStatus: (cb) => on('status', cb),
});
