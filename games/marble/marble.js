"use strict";

// Marble V2 is a renderer: scores, round status and the winner come from API.
const params = new URLSearchParams(window.location.search);
const SESSION_ID = params.get("session_id") || "";
const TOKEN = params.get("token") || "";
const SOCKET_URL = window.location.origin;
const DEFAULT_CONFIG = { gift_target: 50, like_target: 500, like_unit: 15, lion_multiplier: 4 };
let config = { ...DEFAULT_CONFIG };
let pathEl;
let totalLength = 0;
let giftBall;
let likeBall;
let obstaclesGroup;
const obstaclePositions = [0.15, 0.33, 0.55, 0.75, 0.9];

function logError(message, error) {
  console.error(`[MARBLE] ${message}`, error);
  const status = document.getElementById("marble-status");
  if (status) status.textContent = `Erreur : ${message}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}`, ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

function setBallPosition(ball, progress) {
  if (!pathEl || !totalLength || !ball) return;
  const point = pathEl.getPointAtLength(Math.max(0, Math.min(1, progress)) * totalLength);
  ball.setAttribute("cx", point.x);
  ball.setAttribute("cy", point.y);
}

function renderObstacles() {
  obstaclesGroup.innerHTML = "";
  obstaclePositions.forEach((position) => {
    const point = pathEl.getPointAtLength(position * totalLength);
    const obstacle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    obstacle.setAttribute("cx", point.x); obstacle.setAttribute("cy", point.y);
    obstacle.setAttribute("r", 14); obstacle.setAttribute("class", "obstacle");
    obstaclesGroup.appendChild(obstacle);
  });
}

function renderState(nextState) {
  if (!nextState) return;
  config = nextState.config || config;
  document.getElementById("gift-score").textContent = `${nextState.gift_score} / ${config.gift_target}`;
  document.getElementById("like-score").textContent = `${nextState.like_score} / ${config.like_target}`;
  setBallPosition(giftBall, nextState.gift_score / config.gift_target);
  setBallPosition(likeBall, nextState.like_score / config.like_target);
  const status = document.getElementById("marble-status");
  if (nextState.status === "finished") {
    status.textContent = `Manche terminée — victoire ${nextState.winner}`;
    status.dataset.state = "finished";
  } else if (nextState.status === "ended") {
    status.textContent = "Session terminée";
    status.dataset.state = "ended";
  } else {
    status.textContent = "Manche active — en attente des interactions";
    status.dataset.state = "active";
  }
}

async function startRound(reset = false) {
  if (!SESSION_ID || !TOKEN) {
    logError("session absente", new Error("session_id et token requis"));
    return;
  }
  try {
    const requestedConfig = JSON.parse(params.get("marble_config") || "{}");
    const result = await api(`/api/v1/sessions/${encodeURIComponent(SESSION_ID)}/games/marble/start`, {
      method: "POST",
      body: JSON.stringify({ config: requestedConfig, reset }),
    });
    renderState(result.state);
  } catch (error) { logError("démarrage de la manche impossible", error); }
}

function connectSocket() {
  if (!window.io) { logError("Socket.IO indisponible", new Error("client absent")); return; }
  const socket = window.io(SOCKET_URL, { transports: ["websocket"], auth: { token: TOKEN } });
  socket.on("connect_error", (error) => logError("connexion Socket.IO impossible", error));
  socket.on("ia:game_state", (message) => {
    if (message?.game_id === "marble" && message.session_id === SESSION_ID) renderState(message.state);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  pathEl = document.getElementById("track-path");
  giftBall = document.getElementById("ball-gift");
  likeBall = document.getElementById("ball-like");
  obstaclesGroup = document.getElementById("obstacles");
  if (!pathEl || !obstaclesGroup) { logError("structure du plateau absente", new Error("track-path/obstacles")); return; }
  totalLength = pathEl.getTotalLength();
  renderObstacles();
  document.getElementById("reset-round").addEventListener("click", () => startRound(true));
  connectSocket();
  startRound();
});
