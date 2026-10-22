"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("interarcadeDesktop", {
  retry: () => ipcRenderer.send("ia:retry"),
  onBroadcastClosed: (callback) => {
    if (typeof callback === "function") ipcRenderer.on("ia:broadcast-closed", callback);
  },
});
