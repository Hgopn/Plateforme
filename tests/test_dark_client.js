"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { createDarkActionState } = require("../games/dark/dark_actions.js");

function makeClient(onMove = null, search = "?session_id=test&token=test", hash = "") {
  const drawnSprites = [];
  const rotations = [];
  const lightRadii = [];
  const maskFills = [];
  const gradientStops = [];
  const requests = [];
  const listeners = new Map();
  const windowListeners = new Map();
  const opener = {};
  const bodyClasses = new Set();
  const noop = () => {};
  const context = {
    save: noop, restore: noop, translate: noop, clearRect: noop, fillRect: noop,
    strokeRect: noop, beginPath: noop, moveTo: noop, lineTo: noop, stroke: noop,
    fill: noop, arc: noop, ellipse: noop, quadraticCurveTo: noop,
    setTransform: noop,
    rotate: (angle) => rotations.push(angle),
    drawImage: (image) => { if (image.src) drawnSprites.push(image.src); },
    createRadialGradient: (...args) => {
      lightRadii.push(args[5]);
      return { addColorStop: noop };
    },
  };
  const lightContext = {
    ...context,
    fillRect: (...args) => maskFills.push({ color: lightContext.fillStyle, args }),
    createRadialGradient: (...args) => {
      lightRadii.push(args[5]);
      const stops = [];
      gradientStops.push(stops);
      return { addColorStop: (offset, color) => stops.push({ offset, color }) };
    },
  };
  const canvas = { getContext: () => context, style: {} };
  const element = () => ({
    textContent: "", classList: { add: noop, remove: noop },
    querySelector: element, addEventListener: noop,
  });
  const elements = new Map();
  elements.set("game-canvas", canvas);
  elements.set("viewport", {
    clientWidth: 640, clientHeight: 640,
    getBoundingClientRect: () => ({ width: 640, height: 640 }),
  });
  const document = {
    body: { classList: { toggle: (name, enabled) => {
      if (enabled) bodyClasses.add(name); else bodyClasses.delete(name);
    } } },
    getElementById: (id) => {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement: () => ({ getContext: () => lightContext }),
    addEventListener: (name, handler) => listeners.set(name, handler),
    querySelectorAll: () => [],
  };
  class ImageStub {
    complete = true;
    naturalWidth = 1024;
  }
  const sandbox = {
    document, Image: ImageStub, URLSearchParams,
    performance: { now: () => 0 },
    window: {
      location: { search, hash, origin: "http://localhost" },
      opener,
      devicePixelRatio: 1,
      clearTimeout: noop, setTimeout: noop, clearInterval: noop,
      setInterval: noop, addEventListener: (name, handler) => windowListeners.set(name, handler),
      dispatchEvent: noop,
    },
    CustomEvent: class { constructor(name, options) { this.name = name; this.detail = options.detail; } },
    fetch: (url, options) => {
      if (!url.endsWith("/move")) return new Promise(() => {});
      const direction = JSON.parse(options.body).direction;
      requests.push(direction);
      const result = onMove(direction);
      return Promise.resolve({ ok: true, json: async () => result });
    },
    io: () => ({ on: noop }),
    requestAnimationFrame: noop,
  };
  vm.createContext(sandbox);
  const actionsSource = fs.readFileSync(path.join(__dirname, "../games/dark/dark_actions.js"), "utf8");
  vm.runInContext(actionsSource, sandbox, { filename: "games/dark/dark_actions.js" });
  const source = fs.readFileSync(path.join(__dirname, "../games/dark/dark.js"), "utf8");
  vm.runInContext(source, sandbox, { filename: "games/dark/dark.js" });
  return {
    token: vm.runInContext("TOKEN", sandbox),
    bodyClasses,
    noticesEnabled: () => vm.runInContext("showLiveNotices", sandbox),
    sendMessage: (data, origin = "http://localhost", source = opener) =>
      windowListeners.get("message")({ data, origin, source }),
    setState: vm.runInContext("setState", sandbox),
    advance: vm.runInContext("advanceVisualPlayer", sandbox),
    move: vm.runInContext("move", sandbox),
    drawPlayer: vm.runInContext("drawPlayer", sandbox),
    render: vm.runInContext("render", sandbox),
    receiveAction: vm.runInContext("receiveLiveAction", sandbox),
    effects: () => vm.runInContext("liveActions.snapshot()", sandbox),
    element: (id) => elements.get(id),
    position: () => vm.runInContext("({ ...visualPlayer })", sandbox),
    queued: () => vm.runInContext("visualWaypoints.length", sandbox),
    keydown: (key, repeat = false) => listeners.get("keydown")({
      key, repeat, preventDefault: noop,
    }),
    keyup: (key) => listeners.get("keyup")({ key }),
    requests, drawnSprites, rotations, lightRadii, maskFills, gradientStops,
  };
}

test("broadcast token stays in the fragment and marks the test window", () => {
  const client = makeClient(null, "?token=old", "#session_id=new&token=fragment-secret&broadcast=1&mode=test");
  assert.equal(client.token, "fragment-secret");
  assert.equal(client.bodyClasses.has("broadcast"), true);
  assert.equal(client.bodyClasses.has("test-mode"), true);
});

test("only the same-origin launcher can toggle action notices", () => {
  const client = makeClient();
  assert.equal(client.noticesEnabled(), true);
  client.sendMessage({ type: "ia:overlay", enabled: false }, "https://other.example");
  assert.equal(client.noticesEnabled(), true);
  client.sendMessage({ type: "ia:overlay", enabled: false });
  assert.equal(client.noticesEnabled(), false);
  client.sendMessage({ type: "ia:overlay", enabled: true });
  assert.equal(client.noticesEnabled(), true);
});

function gameState(level, size, player, moves) {
  return {
    level, level_count: 3, moves, status: "active", player,
    map: { tiles: Array(size).fill(".".repeat(size)), exit: { x: size - 2, y: size - 2 } },
  };
}

function liveAction(actionType, eventId = actionType, platform = "test") {
  return {
    schema_version: 1, game_id: "dark", session_id: "test", action_type: actionType,
    duration_ms: 8000, event_id: eventId, source_platform: platform,
    source_account_id: `${platform}-creator`, actor_id: `${platform}:viewer-1`,
    actor_username: "Alex",
  };
}

test("confirmed movement crosses cells continuously and follows corners", () => {
  const client = makeClient();
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), null, true);
  client.setState(gameState(1, 10, { x: 2, y: 1 }, 1));
  client.setState(gameState(1, 10, { x: 2, y: 2 }, 2));
  client.advance(100);
  assert.equal(client.position().x, 1.8);
  assert.equal(client.position().y, 1);
  client.advance(50);
  assert.equal(client.position().x, 2);
  assert.ok(client.position().y > 1 && client.position().y < 2);
  client.advance(100);
  assert.deepEqual({ ...client.position() }, { x: 2, y: 2 });
});

test("a blocked step never animates, and a level transition clears queued steps", () => {
  const client = makeClient();
  const start = gameState(1, 10, { x: 1, y: 1 }, 0);
  client.setState(start, null, true);
  client.setState(start, { moved: false });
  assert.equal(client.queued(), 0);
  assert.equal(client.advance(100).walking, false);
  assert.deepEqual({ ...client.position() }, { x: 1, y: 1 });
  client.setState(gameState(1, 10, { x: 2, y: 1 }, 1));
  client.setState(gameState(2, 15, { x: 1, y: 1 }, 2));
  assert.equal(client.queued(), 0);
  assert.deepEqual({ ...client.position() }, { x: 1, y: 1 });
  client.setState(gameState(3, 20, { x: 3, y: 2 }, 3));
  assert.deepEqual({ ...client.position() }, { x: 3, y: 2 });
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), { transition: { type: "reset" } });
  assert.deepEqual({ ...client.position() }, { x: 1, y: 1 });
});

test("four facing sprites animate during walking and light radius stays configurable", () => {
  const client = makeClient();
  for (const direction of ["down", "up", "left", "right"]) {
    client.drawPlayer(100, 100, 64, direction, true);
    assert.equal(client.drawnSprites.at(-1), `assets/player_${direction}.png`);
  }
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), null, true);
  client.setState(gameState(1, 10, { x: 2, y: 1 }, 1));
  client.advance(50);
  client.drawPlayer(100, 100, 64, "right", true);
  assert.notEqual(client.rotations.at(-1), 0);
  client.drawPlayer(100, 100, 64, "right", false);
  assert.equal(client.rotations.at(-1), 0);
  client.render(0);
  assert.equal(client.lightRadii.at(-1), 64 * 1.25);
});

test("the Dark light cover hides walls and the staircase beyond its soft edge", () => {
  const client = makeClient();
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), null, true);
  client.render(0);
  assert.equal(client.maskFills.at(-1).color, "rgba(1, 4, 2, 1)");
  assert.deepEqual(client.maskFills.at(-1).args, [0, 0, 640, 640]);
  const stops = client.gradientStops.at(-1);
  assert.equal(stops[0].offset, 0);
  assert.equal(stops[0].color, "rgba(0, 0, 0, 1)");
  assert.ok(stops[1].offset > .65 && stops[1].offset < .85);
  assert.equal(stops[1].color, "rgba(0, 0, 0, 1)");
  assert.deepEqual(stops[2], { offset: 1, color: "rgba(0, 0, 0, 0)" });
});

test("rapid key repeats cannot validate a second cell before interpolation ends", async () => {
  let serverMoves = 0;
  const client = makeClient(() => {
    serverMoves += 1;
    return {
      state: gameState(1, 10, { x: 1 + serverMoves, y: 1 }, serverMoves),
      outcome: { moved: true, collision: false, transition: null },
    };
  });
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), null, true);
  client.keydown("ArrowRight");
  client.keydown("ArrowRight", true);
  client.keydown("ArrowRight", true);
  await client.move("right");
  await new Promise(setImmediate);
  assert.equal(client.requests.length, 1);
  assert.equal(client.queued(), 1);

  client.advance(50);
  assert.equal(client.position().x, 1.4);
  client.keydown("ArrowRight", true);
  await client.move("right");
  client.render(50);
  assert.equal(client.requests.length, 1);

  client.advance(75);
  assert.deepEqual({ ...client.position() }, { x: 2, y: 1 });
  client.render(66);
  await new Promise(setImmediate);
  assert.equal(client.requests.length, 2);
  assert.equal(client.queued(), 1);
  client.keyup("ArrowRight");
  client.advance(125);
  client.render(82);
  assert.equal(client.requests.length, 2);
  assert.deepEqual({ ...client.position() }, { x: 3, y: 1 });
});

test("quick taps during an active step do not queue an extra move", async () => {
  let serverMoves = 0;
  const client = makeClient(() => {
    serverMoves += 1;
    return {
      state: gameState(1, 10, { x: 1 + serverMoves, y: 1 }, serverMoves),
      outcome: { moved: true, collision: false, transition: null },
    };
  });
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), null, true);
  client.keydown("ArrowRight");
  await new Promise(setImmediate);
  client.advance(50);
  client.keyup("ArrowRight");
  client.keydown("ArrowRight");
  client.keyup("ArrowRight");
  client.advance(75);
  client.render(16);
  await new Promise(setImmediate);
  assert.equal(client.requests.length, 1);
  assert.deepEqual({ ...client.position() }, { x: 2, y: 1 });
});

test("each live action expires back to the normal Dark state", () => {
  let now = 0;
  const actions = createDarkActionState(() => now);
  const expected = {
    LIGHT_BOOST: "lightScale", LIGHT_REDUCE: "lightScale", REVEAL_MAP: "reveal",
    PLAYER_HELP: "help", PLAYER_HINDER: "hinder",
  };
  for (const [type, key] of Object.entries(expected)) {
    assert.equal(actions.apply(liveAction(type)), true);
    const active = actions.snapshot();
    assert.equal(active.active.length, 1);
    assert.notEqual(active[key], key === "lightScale" ? 1 : false);
    now += 8000;
    assert.deepEqual(actions.snapshot(), {
      lightScale: 1, reveal: false, help: false, hinder: false, active: [],
    });
  }
});

test("successive actions replace their slot, refresh duration and never stack without a bound", () => {
  let now = 0;
  const actions = createDarkActionState(() => now);
  assert.equal(actions.apply(liveAction("LIGHT_BOOST", "one")), true);
  now = 1000;
  assert.equal(actions.apply(liveAction("LIGHT_REDUCE", "two")), true);
  assert.equal(actions.snapshot().lightScale, .7);
  assert.equal(actions.apply(liveAction("LIGHT_REDUCE", "two")), false);
  assert.equal(actions.apply(liveAction("PLAYER_HELP", "three")), true);
  assert.equal(actions.snapshot().active.length, 2);
  now = 4000;
  assert.equal(actions.apply(liveAction("PLAYER_HELP", "four")), true);
  assert.equal(actions.snapshot().active.length, 2);
  now = 9000;
  assert.equal(actions.snapshot().lightScale, 1);
  assert.equal(actions.snapshot().help, true);
  now = 12000;
  assert.equal(actions.snapshot().help, false);
});

test("two simulated platforms keep identical display names as distinct actors", () => {
  const actions = createDarkActionState(() => 0);
  actions.apply(liveAction("PLAYER_HELP", "tiktok:event-1", "tiktok"));
  actions.apply(liveAction("REVEAL_MAP", "twitch:event-1", "twitch"));
  const active = actions.snapshot().active;
  assert.equal(active.length, 2);
  assert.equal(active[0].actor_username, active[1].actor_username);
  assert.notEqual(active[0].actor_id, active[1].actor_id);
  assert.notEqual(active[0].source_platform, active[1].source_platform);
});

test("live effects change only visuals and reset clears them", () => {
  const client = makeClient();
  const start = gameState(1, 10, { x: 1, y: 1 }, 0);
  client.setState(start, null, true);
  client.receiveAction(liveAction("LIGHT_BOOST"));
  client.render(0);
  assert.equal(client.lightRadii.at(-1), 64 * 1.25 * 1.6);
  client.receiveAction(liveAction("LIGHT_REDUCE"));
  client.render(0);
  assert.equal(client.lightRadii.at(-1), 64 * 1.25 * .7);
  client.receiveAction(liveAction("REVEAL_MAP"));
  const beforeReveal = client.lightRadii.length;
  client.render(0);
  assert.equal(client.lightRadii.length, beforeReveal);
  client.receiveAction(liveAction("PLAYER_HELP"));
  client.render(0);
  assert.equal(client.element("live-help").textContent, "Sortie ↘");
  client.receiveAction(liveAction("PLAYER_HINDER"));
  client.setState(gameState(1, 10, { x: 2, y: 1 }, 1));
  client.advance(100);
  assert.equal(client.position().x, 1.56);
  client.setState(gameState(1, 10, { x: 1, y: 1 }, 0), { transition: { type: "reset" } });
  assert.equal(client.effects().active.length, 0);
  client.render(0);
  assert.equal(client.lightRadii.at(-1), 64 * 1.25);
});

test("action notices can be disabled while effects remain active", () => {
  const client = makeClient(null, "?session_id=test&token=test&live_notices=0");
  client.setState(gameState(2, 15, { x: 1, y: 1 }, 0), null, true);
  client.receiveAction(liveAction("LIGHT_BOOST"));
  assert.equal(client.element("live-action-notice").textContent, "");
  assert.equal(client.effects().lightScale, 1.6);
});
