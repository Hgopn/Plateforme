"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { EventEmitter } = require("node:events");

const desktop = path.join(__dirname, "..", "desktop");
const source = fs.readFileSync(path.join(desktop, "main.js"), "utf8");

async function boot(serverUrl) {
  const windows = [];
  const ipc = new EventEmitter();
  const app = new EventEmitter();
  const permissions = {};
  const errors = [];
  app.setName = () => {};
  app.setPath = () => {};
  app.getPath = () => "/tmp";
  app.getVersion = () => "0.1.0";
  app.requestSingleInstanceLock = () => true;
  app.whenReady = () => Promise.resolve();
  app.quit = () => { app.quitCalled = true; };
  class Window extends EventEmitter {
    constructor(options) {
      super();
      this.options = options;
      this.webContents = new EventEmitter();
      this.webContents.setWindowOpenHandler = (handler) => { this.openHandler = handler; };
      this.webContents.send = () => {};
      windows.push(this);
    }
    loadURL(url) { this.url = url; }
    isDestroyed() { return false; }
  }
  Window.getAllWindows = () => windows;
  const electron = {
    app, BrowserWindow: Window, ipcMain: ipc,
    dialog: { showErrorBox: (...args) => errors.push(args) },
    session: { defaultSession: {
      setPermissionRequestHandler(handler) { permissions.request = handler; },
      setPermissionCheckHandler(handler) { permissions.check = handler; },
    } },
  };
  vm.runInNewContext(source, {
    require(name) { return name === "electron" ? electron : require(name); },
    process: { env: { INTERARCADE_SERVER_URL: serverUrl }, platform: "win32" },
    __dirname: desktop, URL,
  }, { filename: "desktop/main.js" });
  await Promise.resolve();
  return { app, windows, permissions, errors, ipc };
}

function rejectedNavigation(contents, eventName, url) {
  let prevented = false;
  contents.emit(eventName, { preventDefault() { prevented = true; } }, url);
  return prevented;
}

(async () => {
  const run = await boot("https://interarcade.example.com");
  assert.equal(run.errors.length, 0);
  assert.equal(run.windows.length, 1);
  const main = run.windows[0];
  assert.deepEqual({
    nodeIntegration: main.options.webPreferences.nodeIntegration,
    contextIsolation: main.options.webPreferences.contextIsolation,
    sandbox: main.options.webPreferences.sandbox,
    webSecurity: main.options.webPreferences.webSecurity,
  }, { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true });
  assert.equal(main.openHandler({ url: "https://evil.example/launcher" }).action, "deny");
  assert.equal(main.openHandler({ url: "https://interarcade.example.com/admin" }).action, "deny");
  const child = main.openHandler({ url: "https://interarcade.example.com/broadcast/waiting" });
  assert.equal(child.action, "allow");
  assert.equal(child.overrideBrowserWindowOptions.webPreferences.nodeIntegration, false);
  assert.equal(child.overrideBrowserWindowOptions.webPreferences.contextIsolation, true);
  assert.equal(child.overrideBrowserWindowOptions.webPreferences.sandbox, true);
  assert.equal(rejectedNavigation(main.webContents, "will-navigate", "https://evil.example/"), true);
  assert.equal(rejectedNavigation(main.webContents, "will-redirect", "https://evil.example/"), true);
  assert.equal(rejectedNavigation(main.webContents, "will-navigate", "https://interarcade.example.com/launcher"), false);
  let permission = true;
  run.permissions.request(main.webContents, "camera", (allowed) => { permission = allowed; });
  assert.equal(permission, false);
  assert.equal(run.permissions.check(), false);
  let webviewBlocked = false;
  run.app.emit("web-contents-created", {}, new EventEmitter());
  const contents = new EventEmitter();
  run.app.emit("web-contents-created", {}, contents);
  contents.emit("will-attach-webview", { preventDefault() { webviewBlocked = true; } });
  assert.equal(webviewBlocked, true);
  const before = main.url;
  run.ipc.emit("ia:retry", { sender: {} });
  assert.equal(main.url, before);

  for (const invalid of ("http://remote.example", "https://user:password@interarcade.example.com")) {
    const result = await boot(invalid);
    assert.equal(result.app.quitCalled, true);
    assert.equal(result.windows.length, 0);
  }
  console.log("Desktop security contract passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
