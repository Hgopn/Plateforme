"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function makeClient(onMove = null) {
  const drawnSprites = [];
  const rotations = [];
  const lightRadii = [];
  const requests = [];
  const listeners = new Map();
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
    getElementById: (id) => {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement: () => ({ getContext: () => context }),
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
      location: { search: "?session_id=test&token=test", origin: "http://localhost" },
      devicePixelRatio: 1,
      clearTimeout: noop, setTimeout: noop, clearInterval: noop,
      setInterval: noop, addEventListener: noop,
    },
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
  const source = fs.readFileSync(path.join(__dirname, "../games/dark/dark.js"), "utf8");
  vm.runInContext(source, sandbox, { filename: "games/dark/dark.js" });
  return {
    setState: vm.runInContext("setState", sandbox),
    advance: vm.runInContext("advanceVisualPlayer", sandbox),
    move: vm.runInContext("move", sandbox),
    drawPlayer: vm.runInContext("drawPlayer", sandbox),
    render: vm.runInContext("render", sandbox),
    position: () => vm.runInContext("({ ...visualPlayer })", sandbox),
    queued: () => vm.runInContext("visualWaypoints.length", sandbox),
    keydown: (key, repeat = false) => listeners.get("keydown")({
      key, repeat, preventDefault: noop,
    }),
    keyup: (key) => listeners.get("keyup")({ key }),
    requests, drawnSprites, rotations, lightRadii,
  };
}

function gameState(level, size, player, moves) {
  return {
    level, level_count: 3, moves, status: "active", player,
    map: { tiles: Array(size).fill(".".repeat(size)) },
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
