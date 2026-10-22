"use strict";

// The product launcher puts the short-lived game token in the URL fragment so
// it never enters access logs or Referer headers. Query parameters remain for
// the local pilot and existing test tools.
const params = new URLSearchParams((window.location.hash || "").slice(1)
  || (window.location.search || "").slice(1));
if (document.body) {
  document.body.classList.toggle("broadcast", params.get("broadcast") === "1");
  document.body.classList.toggle("test-mode", params.get("mode") === "test");
}
const SESSION_ID = params.get("session_id") || "";
const TOKEN = params.get("token") || "";
const canvas = document.getElementById("game-canvas");
const context = canvas.getContext("2d");
const lightCanvas = document.createElement("canvas");
const lightContext = lightCanvas.getContext("2d");
const viewport = document.getElementById("viewport");
const levelLabel = document.getElementById("level-label");
const sessionState = document.getElementById("session-state");
const objectiveText = document.getElementById("objective-text");
const moveCount = document.getElementById("move-count");
const message = document.getElementById("message");
const errorPanel = document.getElementById("error-panel");
const liveActionNotice = document.getElementById("live-action-notice");
const liveHelp = document.getElementById("live-help");
// Visual tuning only; the server still decides which grid steps are valid.
const DARK_VISUALS = Object.freeze({
  lightRadiusTiles: 1.25,
  lightIntensity: 1,
  lightSoftness: .27,
  outsideOpacity: 1,
  moveSpeedCellsPerSecond: 8,
});
const DARK_ACTION_UI = Object.freeze({
  showNotices: params.get("live_notices") !== "0",
  noticeMs: 2600,
});
let showLiveNotices = DARK_ACTION_UI.showNotices;
const liveActions = createDarkActionState();
const liveActionLabels = Object.freeze({
  LIGHT_BOOST: "a agrandi la lumière",
  LIGHT_REDUCE: "a réduit la lumière",
  REVEAL_MAP: "a révélé la zone",
  PLAYER_HELP: "a indiqué la sortie",
  PLAYER_HINDER: "a ralenti le joueur",
});
const playerSprites = Object.fromEntries(["down", "up", "left", "right"].map((direction) => {
  const sprite = new Image();
  sprite.src = `assets/player_${direction}.png`;
  return [direction, sprite];
}));

let state = null;
let socket = null;
let movePending = false;
let facing = "down";
let visualPlayer = { x: 1, y: 1 };
let visualWaypoints = [];
let walkPhase = 0;
let messageTimer = null;
let liveNoticeTimer = null;
let lastFrame = performance.now();
let heldDirection = null;
let holdCanRepeat = false;

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TOKEN}`,
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

function showError(text) {
  errorPanel.textContent = text;
  errorPanel.classList.remove("hidden");
  sessionState.textContent = "Session indisponible";
}

function showMessage(kicker, title, detail, duration = 1700) {
  window.clearTimeout(messageTimer);
  message.querySelector(".message-kicker").textContent = kicker;
  message.querySelector("strong").textContent = title;
  message.querySelector("small").textContent = detail;
  message.classList.add("visible");
  if (duration) {
    messageTimer = window.setTimeout(() => message.classList.remove("visible"), duration);
  }
}

function setState(nextState, outcome = null, snap = false) {
  if (!nextState) return;
  const previous = state;
  const resetTransition = outcome?.transition?.type === "reset";
  if (previous && !snap && !resetTransition && previous.level === nextState.level
      && nextState.moves < previous.moves) return;
  const duplicate = state
    && state.level === nextState.level
    && state.moves === nextState.moves
    && state.status === nextState.status;
  const changedLevel = state && state.level !== nextState.level;
  state = nextState;
  if (resetTransition || nextState.status === "finished") liveActions.clear();
  if (changedLevel || resetTransition) stopHolding();
  if (snap || changedLevel || resetTransition) {
    visualWaypoints = [];
    visualPlayer = { ...nextState.player };
    walkPhase = 0;
  } else if (!duplicate && previous && nextState.moves > previous.moves) {
    const stepDistance = Math.abs(nextState.player.x - previous.player.x)
      + Math.abs(nextState.player.y - previous.player.y);
    if (stepDistance === 1) visualWaypoints.push({ ...nextState.player });
    else {
      visualWaypoints = [];
      visualPlayer = { ...nextState.player };
    }
  }
  levelLabel.textContent = `Niveau ${nextState.level} / ${nextState.level_count}`;
  moveCount.textContent = `${nextState.moves} pas`;
  sessionState.textContent = nextState.status === "finished" ? "Parcours terminé" : "Session active";
  objectiveText.textContent = nextState.status === "finished"
    ? "Les trois sorties ont été trouvées."
    : "Cherchez l’escalier dans l’obscurité.";

  const transition = duplicate ? null : outcome?.transition;
  if (transition?.type === "level_complete") {
    showMessage("NIVEAU TERMINÉ", `Entrée dans la zone ${transition.next_level}`, "La grotte s’étend. Trouvez le prochain escalier.");
  } else if (transition?.type === "game_complete") {
    showMessage("PARCOURS TERMINÉ", "Vous avez retrouvé la sortie", "Les trois niveaux de Dark sont terminés.", 0);
  } else if (transition?.type === "reset") {
    showMessage("NOUVEAU PARCOURS", "Retour au niveau 1", "La progression de cette session a été réinitialisée.");
  }
}

function resizeCanvas() {
  const rect = viewport.getBoundingClientRect();
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  lightCanvas.width = canvas.width;
  lightCanvas.height = canvas.height;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  lightContext.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function caveNoise(x, y) {
  return Math.abs(Math.sin(x * 12.9898 + y * 78.233) * 43758.5453) % 1;
}

function drawWall(screenX, screenY, tile, x, y) {
  const shade = 22 + Math.floor(caveNoise(x, y) * 10);
  context.fillStyle = `rgb(${shade - 4}, ${shade + 4}, ${shade})`;
  context.fillRect(screenX, screenY, tile + 1, tile + 1);
  context.strokeStyle = "rgba(130, 151, 137, .09)";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(screenX + tile * .12, screenY + tile * .28);
  context.lineTo(screenX + tile * .52, screenY + tile * .18);
  context.lineTo(screenX + tile * .84, screenY + tile * .36);
  context.stroke();
  context.fillStyle = "rgba(0, 0, 0, .22)";
  context.fillRect(screenX, screenY + tile * .82, tile, tile * .18);
}

function drawFloor(screenX, screenY, tile, x, y) {
  const shade = 11 + Math.floor(caveNoise(x, y) * 5);
  context.fillStyle = `rgb(${shade - 2}, ${shade + 3}, ${shade})`;
  context.fillRect(screenX, screenY, tile + 1, tile + 1);
  if (caveNoise(y + 9, x + 4) > .68) {
    context.fillStyle = "rgba(133, 159, 139, .12)";
    context.beginPath();
    context.arc(screenX + tile * .3, screenY + tile * .62, tile * .035, 0, Math.PI * 2);
    context.fill();
  }
}

function drawExit(screenX, screenY, tile) {
  context.save();
  context.translate(screenX + tile / 2, screenY + tile / 2);
  context.fillStyle = "#859481";
  context.strokeStyle = "#c0ceb8";
  context.lineWidth = Math.max(1, tile * .025);
  for (let step = 0; step < 5; step += 1) {
    const width = tile * (.65 - step * .085);
    const y = tile * (.25 - step * .105);
    context.fillRect(-width / 2, y, width, tile * .085);
    context.strokeRect(-width / 2, y, width, tile * .085);
  }
  context.restore();
}

function drawPlayer(centerX, centerY, tile, direction, walking) {
  const sprite = playerSprites[direction];
  const size = tile * .8;
  const stride = walking ? Math.sin(walkPhase) : 0;
  const bob = walking ? Math.abs(stride) * tile * .055 : 0;
  context.save();
  context.translate(centerX, centerY);
  context.fillStyle = "rgba(0, 0, 0, .55)";
  context.beginPath();
  context.ellipse(0, tile * .24, tile * .2, tile * .065, 0, 0, Math.PI * 2);
  context.fill();
  context.translate(stride * tile * .035, -bob);
  context.rotate(stride * .09);
  if (sprite.complete && sprite.naturalWidth) {
    context.drawImage(sprite, -size / 2, -size * .55, size, size);
  } else {
    context.fillStyle = "#d7ddd3";
    context.beginPath();
    context.ellipse(0, 0, tile * .2, tile * .27, 0, 0, Math.PI * 2);
    context.fill();
  }
  if (walking) {
    context.fillStyle = "#382319";
    for (const side of [-1, 1]) {
      const step = side * stride * tile * .045;
      const sideView = direction === "left" || direction === "right";
      const footX = side * tile * .065 + (sideView ? step : 0);
      const footY = tile * .21 + (sideView ? 0 : step);
      context.beginPath();
      context.ellipse(footX, footY, tile * .041, tile * .025, 0, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.restore();
}

function advanceVisualPlayer(delta, effects = liveActions.snapshot()) {
  const speed = DARK_VISUALS.moveSpeedCellsPerSecond * (effects.hinder ? .7 : 1);
  let remaining = speed * delta / 1000;
  let travelled = 0;
  let direction = facing;
  while (remaining > 0 && visualWaypoints.length) {
    const next = visualWaypoints[0];
    const dx = next.x - visualPlayer.x;
    const dy = next.y - visualPlayer.y;
    const distance = Math.hypot(dx, dy);
    if (distance < .00001) {
      visualPlayer = visualWaypoints.shift();
      continue;
    }
    direction = Math.abs(dx) > Math.abs(dy)
      ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
    const step = Math.min(remaining, distance);
    visualPlayer.x += dx / distance * step;
    visualPlayer.y += dy / distance * step;
    travelled += step;
    remaining -= step;
    if (step >= distance - .00001) visualPlayer = visualWaypoints.shift();
  }
  if (travelled) walkPhase += travelled * Math.PI * 1.3;
  return { walking: travelled > 0, direction };
}

function render(time) {
  const delta = Math.min(32, time - lastFrame);
  lastFrame = time;
  const effects = liveActions.snapshot();
  const motion = advanceVisualPlayer(Math.max(0, delta), effects);
  if (heldDirection && holdCanRepeat && !movePending && !visualWaypoints.length) {
    move(heldDirection);
  }

  const width = viewport.clientWidth;
  const height = viewport.clientHeight;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#020403";
  context.fillRect(0, 0, width, height);
  if (!state) {
    liveHelp.classList.remove("visible");
    requestAnimationFrame(render);
    return;
  }

  const tile = Math.max(46, Math.min(64, Math.floor(Math.min(width, height) / 6.1)));
  const centerX = width / 2;
  const centerY = height / 2;
  const offsetX = centerX - (visualPlayer.x + .5) * tile;
  const offsetY = centerY - (visualPlayer.y + .5) * tile;
  state.map.tiles.forEach((row, y) => {
    [...row].forEach((cell, x) => {
      const screenX = offsetX + x * tile;
      const screenY = offsetY + y * tile;
      if (screenX > width || screenY > height || screenX + tile < 0 || screenY + tile < 0) return;
      if (cell === "#") drawWall(screenX, screenY, tile, x, y);
      else drawFloor(screenX, screenY, tile, x, y);
      if (cell === "E") drawExit(screenX, screenY, tile);
    });
  });

  const flicker = Math.sin(time * .0067) * 2.5 + Math.sin(time * .017) * 1.2;
  const lightRadius = tile * DARK_VISUALS.lightRadiusTiles * effects.lightScale + flicker;
  lightContext.clearRect(0, 0, width, height);
  if (!effects.reveal) {
    lightContext.save();
    // A fully opaque outside prevents walls and the exit from revealing the map.
    // The gradient cuts a soft opening in that cover; it does not tint the map.
    lightContext.fillStyle = `rgba(1, 4, 2, ${DARK_VISUALS.outsideOpacity})`;
    lightContext.fillRect(0, 0, width, height);
    lightContext.globalCompositeOperation = "destination-out";
    const light = lightContext.createRadialGradient(centerX, centerY, 0, centerX, centerY, lightRadius);
    light.addColorStop(0, `rgba(0, 0, 0, ${DARK_VISUALS.lightIntensity})`);
    light.addColorStop(1 - DARK_VISUALS.lightSoftness, `rgba(0, 0, 0, ${DARK_VISUALS.lightIntensity})`);
    light.addColorStop(1, "rgba(0, 0, 0, 0)");
    lightContext.fillStyle = light;
    lightContext.beginPath();
    lightContext.arc(centerX, centerY, lightRadius, 0, Math.PI * 2);
    lightContext.fill();
    lightContext.restore();
    context.drawImage(lightCanvas, 0, 0, width, height);
  }
  if (effects.help && state.status === "active") {
    liveHelp.textContent = `Sortie ${exitDirection(state.map.exit, state.player)}`;
    liveHelp.classList.add("visible");
  } else liveHelp.classList.remove("visible");
  drawPlayer(centerX, centerY, tile, motion.direction, motion.walking);
  requestAnimationFrame(render);
}

function exitDirection(exit, player) {
  const angle = Math.atan2(exit.y - player.y, exit.x - player.x);
  return ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"]
    [Math.round(angle / (Math.PI / 4) + 8) % 8];
}

function receiveLiveAction(action) {
  if (action?.session_id !== SESSION_ID || state?.status !== "active" || !liveActions.apply(action)) return;
  window.dispatchEvent(new CustomEvent("interarcade:action", { detail: action }));
  if (!showLiveNotices) return;
  const platform = action.source_platform;
  const platformLabel = platform.charAt(0).toUpperCase() + platform.slice(1);
  liveActionNotice.textContent = `${action.actor_username} · ${platformLabel} ${liveActionLabels[action.action_type]}`;
  liveActionNotice.classList.add("visible");
  window.clearTimeout(liveNoticeTimer);
  liveNoticeTimer = window.setTimeout(() => liveActionNotice.classList.remove("visible"), DARK_ACTION_UI.noticeMs);
}

window.addEventListener("message", (event) => {
  if (event.origin !== window.location.origin || event.source !== window.opener
      || event.data?.type !== "ia:overlay" || typeof event.data.enabled !== "boolean") return;
  showLiveNotices = event.data.enabled;
  if (!showLiveNotices) liveActionNotice.classList.remove("visible");
});

async function move(direction) {
  if (movePending || visualWaypoints.length || !state || state.status !== "active") return;
  facing = direction;
  movePending = true;
  try {
    const result = await api(`/api/v1/sessions/${encodeURIComponent(SESSION_ID)}/games/dark/move`, {
      method: "POST",
      body: JSON.stringify({ direction }),
    });
    setState(result.state, result.outcome);
    if (!result.outcome?.moved || result.outcome.transition) holdCanRepeat = false;
  } catch (error) {
    holdCanRepeat = false;
    showError(`Déplacement impossible : ${error.message}`);
  } finally {
    movePending = false;
  }
}

async function reset() {
  if (!state || movePending) return;
  stopHolding();
  movePending = true;
  try {
    const result = await api(`/api/v1/sessions/${encodeURIComponent(SESSION_ID)}/games/dark/reset`, {
      method: "POST",
      body: "{}",
    });
    setState(result.state, result.outcome, true);
  } catch (error) {
    showError(`Reset impossible : ${error.message}`);
  } finally {
    movePending = false;
  }
}

function connectEvents() {
  socket = io(window.location.origin, { transports: ["websocket"], auth: { token: TOKEN } });
  socket.on("connect", () => { sessionState.textContent = "Session active"; });
  socket.on("disconnect", () => { sessionState.textContent = "Reconnexion…"; });
  socket.on("ia:game_state", (messageState) => {
    if (messageState?.game_id === "dark" && messageState.session_id === SESSION_ID) {
      setState(messageState.state, messageState.outcome);
    }
  });
  socket.on("ia:event", (event) => {
    window.dispatchEvent(new CustomEvent("interarcade:event", { detail: event }));
    sessionState.textContent = "Événement reçu";
    window.setTimeout(() => {
      if (state?.status === "active") sessionState.textContent = "Session active";
    }, 900);
  });
  socket.on("ia:action", receiveLiveAction);
}

async function start() {
  if (!SESSION_ID || !TOKEN) {
    showError("Ouvrez Dark depuis le launcher InterArcade pour créer une session.");
    return;
  }
  try {
    connectEvents();
    const result = await api(`/api/v1/sessions/${encodeURIComponent(SESSION_ID)}/games/dark/start`, {
      method: "POST",
      body: "{}",
    });
    setState(result.state, null, true);
    window.setTimeout(() => message.classList.remove("visible"), 2300);
  } catch (error) {
    showError(`Dark ne peut pas démarrer : ${error.message}`);
  }
}

const keyDirections = {
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  w: "up", z: "up", s: "down", a: "left", q: "left", d: "right",
};

function stopHolding(direction = heldDirection) {
  if (heldDirection !== direction) return;
  heldDirection = null;
  holdCanRepeat = false;
}

function startHolding(direction) {
  if (heldDirection === direction) return;
  stopHolding();
  heldDirection = direction;
  holdCanRepeat = true;
  move(direction);
}

document.addEventListener("keydown", (event) => {
  const direction = keyDirections[event.key] || keyDirections[event.key.toLowerCase()];
  if (!direction) return;
  event.preventDefault();
  if (event.repeat && heldDirection === direction) return;
  startHolding(direction);
});
document.addEventListener("keyup", (event) => {
  const direction = keyDirections[event.key] || keyDirections[event.key.toLowerCase()];
  if (direction) stopHolding(direction);
});
document.querySelectorAll("[data-direction]").forEach((button) => {
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    button.setPointerCapture(event.pointerId);
    startHolding(button.dataset.direction);
  });
  button.addEventListener("pointerup", () => stopHolding(button.dataset.direction));
  button.addEventListener("pointercancel", () => stopHolding(button.dataset.direction));
  button.addEventListener("click", (event) => {
    if (event.detail === 0) move(button.dataset.direction);
  });
});
document.getElementById("reset-button").addEventListener("click", reset);
window.addEventListener("resize", resizeCanvas);
window.addEventListener("blur", () => stopHolding());
resizeCanvas();
requestAnimationFrame(render);
start();
