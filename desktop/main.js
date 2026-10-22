"use strict";

const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

function serverOrigin() {
  const file = path.join(__dirname, "server.json");
  const configured = process.env.INTERARCADE_SERVER_URL || JSON.parse(fs.readFileSync(file, "utf8")).serverUrl;
  const url = new URL(configured);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname))) {
    throw new Error("InterArcade requires HTTPS for remote servers");
  }
  return url.origin;
}

let origin;
try { origin = serverOrigin(); } catch (error) {
  dialog.showErrorBox("Configuration InterArcade", error.message);
  app.quit();
}
app.setName("InterArcade");
app.setPath("userData", path.join(app.getPath("appData"), "InterArcade"));
if (!app.requestSingleInstanceLock()) app.quit();

function permitted(url, broadcast = false) {
  try {
    const parsed = new URL(url);
    if (parsed.origin !== origin) return false;
    if (!broadcast) return ["/", "/launcher"].includes(parsed.pathname);
    return ["/broadcast/waiting", "/games/dark/dark.html"].includes(parsed.pathname);
  } catch { return false; }
}

function createMainWindow() {
  const main = new BrowserWindow({
    title: `InterArcade ${app.getVersion()}`, width: 1280, height: 860, minWidth: 960, minHeight: 660,
    backgroundColor: "#f1eee6", autoHideMenuBar: true,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true,
      backgroundThrottling: false,
      preload: path.join(__dirname, "preload.js") },
  });
  main.webContents.setWindowOpenHandler(({ url }) => {
    if (!permitted(url, true)) return { action: "deny" };
    return {
      action: "allow",
      overrideBrowserWindowOptions: {
        title: "Dark — InterArcade", width: 1100, height: 760, minWidth: 480, minHeight: 480,
        backgroundColor: "#0b130e", autoHideMenuBar: true, resizable: true,
        webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true },
      },
    };
  });
  main.webContents.on("did-create-window", (child) => {
    child.on("closed", () => {
      if (!main.isDestroyed()) main.webContents.send("ia:broadcast-closed");
    });
    child.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    child.webContents.on("will-navigate", (event, url) => {
      if (!permitted(url, true)) event.preventDefault();
    });
  });
  main.webContents.on("will-navigate", (event, url) => {
    if (!permitted(url)) event.preventDefault();
  });
  main.webContents.on("did-fail-load", (_event, code, _description, _url, mainFrame) => {
    if (mainFrame && code !== -3 && !main.isDestroyed()) main.loadFile(path.join(__dirname, "offline.html"));
  });
  ipcMain.on("ia:retry", (event) => {
    if (event.sender === main.webContents && !main.isDestroyed()) main.loadURL(`${origin}/launcher`);
  });
  main.loadURL(`${origin}/launcher`);
}

app.whenReady().then(() => {
  if (origin) createMainWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0 && origin) createMainWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("second-instance", () => {
  const main = BrowserWindow.getAllWindows().find((window) => !window.getParentWindow());
  if (main) { if (main.isMinimized()) main.restore(); main.focus(); }
});
