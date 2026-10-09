'use strict';
/**
 * Preload — the only bridge between the web UI and the Electron main process.
 * contextIsolation is ON and nodeIntegration is OFF, so the app pages cannot
 * touch Node directly; they get exactly these functions and nothing else.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('veronica', {
  getSettings: () => ipcRenderer.invoke('settings:get'),
  saveSettings: (patch) => ipcRenderer.invoke('settings:save', patch),
  getStatus: () => ipcRenderer.invoke('status:get'),
  openRuntime: () => ipcRenderer.invoke('runtime:open'),
  openLogs: () => ipcRenderer.invoke('logs:open'),
  relaunch: () => ipcRenderer.invoke('app:relaunch'),
});
