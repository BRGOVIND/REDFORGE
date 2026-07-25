'use strict';
/**
 * Preload — a small, safe bridge (contextIsolation on, nodeIntegration off).
 * Exposes ONLY what the renderer needs: app info, backend status/restart, update
 * controls, and event subscriptions. No Node/fs access leaks to the web app.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('redforge', {
  appInfo: () => ipcRenderer.invoke('app:info'),
  backend: {
    status: () => ipcRenderer.invoke('backend:status'),
    restart: () => ipcRenderer.invoke('backend:restart'),
    onStatus: (cb) => ipcRenderer.on('backend-status', (_e, d) => cb(d)),
    onHealth: (cb) => ipcRenderer.on('backend-health', (_e, d) => cb(d)),
  },
  update: {
    check: () => ipcRenderer.invoke('update:check'),
    install: () => ipcRenderer.invoke('update:install'),
    onEvent: (cb) => ipcRenderer.on('update', (_e, d) => cb(d)),
  },
  openPath: (target) => ipcRenderer.invoke('app:openPath', target),
  // splash-only channel
  onSplashStatus: (cb) => ipcRenderer.on('status', (_e, d) => cb(d)),
});
