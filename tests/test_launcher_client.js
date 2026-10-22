"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/launcher.js"), "utf8");
const account = { email: "creator@example.com", csrf_token: "csrf", entitled_games: [], platforms: [] };

function harness(responder) {
  const elements = new Map();
  const requests = [];
  const windows = [];
  const windowEvents = {};
  function element(id) {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {
        value: "", textContent: "", checked: false, disabled: false,
        firstChild: { textContent: "" }, handlers: {},
        classList: {
          add: (name) => classes.add(name), remove: (name) => classes.delete(name),
          toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
          contains: (name) => classes.has(name),
        },
        addEventListener(name, fn) { this.handlers[name] = fn; },
      });
    }
    return elements.get(id);
  }
  const location = { hash: "", origin: "http://127.0.0.1:5000" };
  const window = {
    location, scrollTo() {}, addEventListener(name, fn) { windowEvents[name] = fn; },
    open() {
      const child = { closed: false, location: { replace(value) { child.url = value; } },
        focus() {}, close() { child.closed = true; } };
      windows.push(child);
      return child;
    },
  };
  const context = { window, location, document: { getElementById: element, querySelectorAll: () => [] },
    URLSearchParams, encodeURIComponent, console, setInterval: () => {},
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      const result = await responder(url, options);
      return { ok: result.status < 400, json: async () => result.body };
    },
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return { context, element, requests, windows, windowEvents };
}

async function settle() { await new Promise((resolve) => setImmediate(resolve)); }

test("a double click opens one test session and closing Dark ends it", async () => {
  let creates = 0;
  let ends = 0;
  const ui = harness(async (url, options) => {
    if (url.endsWith("/me")) return { status: 200, body: account };
    if (url.endsWith("/active")) return { status: 200, body: { session: null } };
    if (url === "/api/v1/creator/sessions" && options.method === "POST") {
      creates += 1;
      await settle();
      return { status: 201, body: { session_id: "session-1", token: "game-token", mode: "test" } };
    }
    if (url.endsWith("/end")) { ends += 1; return { status: 200, body: {} }; }
    return { status: 200, body: { status: "active", mode: "test", sources: [] } };
  });
  await settle();
  const first = ui.context.launchDark("test");
  const second = ui.context.launchDark("test");
  await Promise.all([first, second]);
  assert.equal(creates, 1);
  assert.equal(ui.windows.length, 1);
  assert.match(ui.windows[0].url, /games\/dark\/dark\.html#/);
  assert.match(ui.windows[0].url, /mode=test/);
  ui.windows[0].closed = true;
  await ui.context.refreshSessionStatus();
  assert.equal(ends, 1);
  assert.equal(ui.element("session-controls").classList.contains("hidden"), true);
});

test("server and license failures are shown in plain language", async () => {
  const offline = harness(async () => { throw new Error("ECONNREFUSED secret internals"); });
  await settle();
  assert.match(offline.element("auth-error").textContent, /Connexion au serveur impossible/);
  assert.doesNotMatch(offline.element("auth-error").textContent, /ECONNREFUSED/);
  const gated = harness(async (url, options) => {
    if (url.endsWith("/me")) return { status: 200, body: account };
    if (url.endsWith("/active")) return { status: 200, body: { session: null } };
    if (options.method === "POST") return { status: 403, body: { error: "license_required" } };
    return { status: 200, body: {} };
  });
  await settle();
  await gated.context.launchDark("live");
  assert.match(gated.element("launch-message").textContent, /licence Dark/);
  assert.equal(gated.windows[0].closed, true);
});

test("return to library ends the active session", async () => {
  let ends = 0;
  const ui = harness(async (url, options) => {
    if (url.endsWith("/me")) return { status: 200, body: account };
    if (url.endsWith("/active")) return { status: 200, body: { session: null } };
    if (url.endsWith("/end")) { ends += 1; return { status: 200, body: {} }; }
    if (options.method === "POST") return { status: 201,
      body: { session_id: "session-1", token: "game-token", mode: "test" } };
    return { status: 200, body: { status: "active", mode: "test", sources: [] } };
  });
  await settle();
  await ui.context.launchDark("test");
  await ui.element("back-library").handlers.click();
  assert.equal(ends, 1);
  assert.equal(ui.context.location.hash, "bibliotheque");
});

test("closing the launcher sends a keepalive stop request", async () => {
  const ui = harness(async (url, options) => {
    if (url.endsWith("/me")) return { status: 200, body: account };
    if (url.endsWith("/active")) return { status: 200, body: { session: null } };
    if (options.method === "POST") return { status: 201,
      body: { session_id: "session-1", token: "game-token", mode: "test" } };
    return { status: 200, body: { status: "active", mode: "test", sources: [] } };
  });
  await settle();
  await ui.context.launchDark("test");
  ui.windowEvents.pagehide();
  await settle();
  const stop = ui.requests.find((item) => item.url.endsWith("/end"));
  assert.equal(stop.options.keepalive, true);
  assert.equal(stop.options.headers["X-CSRF-Token"], "csrf");
});

test("live connection, offline, reconnecting and listener loss have distinct states", async () => {
  let sourceStatus = "connecting";
  const ui = harness(async (url, options) => {
    if (url.endsWith("/me")) return { status: 200, body: account };
    if (url.endsWith("/active")) return { status: 200, body: { session: null } };
    if (options.method === "POST") return { status: 201,
      body: { session_id: "session-1", token: "game-token", mode: "live" } };
    return { status: 200, body: { status: "active", mode: "live",
      sources: [{ platform: "tiktok", status: sourceStatus }] } };
  });
  await settle();
  await ui.context.launchDark("live");
  for (const [status, expected] of [
    ["connecting", "Connexion TikTok en cours"], ["connected", "TikTok connecté"],
    ["offline", "Live non détecté"], ["reconnecting", "Reconnexion TikTok"],
    ["lost", "Connexion au listener perdue"],
  ]) {
    sourceStatus = status;
    await ui.context.refreshSessionStatus();
    assert.match(ui.element("session-state").textContent, new RegExp(expected));
  }
});
