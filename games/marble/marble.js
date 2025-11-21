console.log("[marble] JS chargé");

// ===============================
// 🔗 CONNEXION AU BACKEND OVH
// ===============================
let ipcRenderer = null;
let socket = null;

try {
  if (window.require) {
    ipcRenderer = window.require("electron").ipcRenderer;
  }
} catch {}

// username
const USERNAME = new URLSearchParams(window.location.search).get("username") || "songmicon";
const SOCKET_URL = "http://51.38.238.227:5000";

// scores
let giftScore = 0;
let likeScore = 0;

let giftProgress = 0;
let likeProgress = 0;

const GIFT_TARGET = 50;
const LIKE_TARGET = 500;

const OBSTACLE_POSITIONS = [0.15, 0.33, 0.55, 0.75, 0.9];
let hitGiftObstacles = new Set();
let hitLikeObstacles = new Set();

// DOM elements
let giftScoreEl, likeScoreEl;
let pathEl, totalLength;
let ballGiftEl, ballLikeEl;
let obstaclesGroup;

// ===============================
// INIT DOM
// ===============================
document.addEventListener("DOMContentLoaded", () => {

  giftScoreEl = document.getElementById("gift-score");
  likeScoreEl = document.getElementById("like-score");
  pathEl = document.getElementById("track-path");
  ballGiftEl = document.getElementById("ball-gift");
  ballLikeEl = document.getElementById("ball-like");
  obstaclesGroup = document.getElementById("obstacles");

  if (!pathEl) {
    console.error("[MARBLE] track-path introuvable.");
    return;
  }

  totalLength = pathEl.getTotalLength();

  createObstacles();
  setBallPosition(ballGiftEl, 0);
  setBallPosition(ballLikeEl, 0);

  connectSocket();
});

// ===============================
// SOCKET.IO
// ===============================
function connectSocket() {
  try {
    socket = io(SOCKET_URL, {
      transports: ["websocket"],
      query: { username: USERNAME }
    });

    socket.on("ia:event", data => {
      if (!data || (data.target && data.target !== USERNAME)) return;
      if (data.type === "gift") handleGiftEvent(data);
      if (data.type === "like") handleLikeEvent(data);
    });

  } catch (err) {
    console.error("Socket error", err);
  }
}

// ===============================
// PISTE
// ===============================
function setBallPosition(ballEl, progress) {
  const dist = Math.max(0, Math.min(1, progress)) * totalLength;
  const pt = pathEl.getPointAtLength(dist);
  ballEl.setAttribute("cx", pt.x);
  ballEl.setAttribute("cy", pt.y);
}

function createObstacles() {
  obstaclesGroup.innerHTML = "";
  OBSTACLE_POSITIONS.forEach(pos => {
    const pt = pathEl.getPointAtLength(pos * totalLength);
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", pt.x);
    c.setAttribute("cy", pt.y);
    c.setAttribute("r", 14);
    c.setAttribute("class", "obstacle");
    obstaclesGroup.appendChild(c);
  });
}

function applyObstaclePenalty(progress, lastProgress, hitSet, label) {
  let newP = progress;
  OBSTACLE_POSITIONS.forEach(pos => {
    if (lastProgress < pos && newP >= pos && !hitSet.has(pos)) {
      hitSet.add(pos);
      newP -= 0.04;
    }
  });
  return Math.max(0, newP);
}

// ===============================
// EVENTS
// ===============================
function handleGiftEvent(e) {
  const count = e.count || 1;
  const giftName = (e.gift || "").toLowerCase();

  let power = count;
  if (giftName.includes("lion") || giftName.includes("unicorn")) power *= 4;

  giftScore += power;
  giftScoreEl.textContent = giftScore;

  const last = giftProgress;
  giftProgress = Math.min(1, giftScore / GIFT_TARGET);
  giftProgress = applyObstaclePenalty(giftProgress, last, hitGiftObstacles, "GIFTS");

  setBallPosition(ballGiftEl, giftProgress);

  if (giftProgress >= 1) onRaceEnd("GIFTS");
}

function handleLikeEvent(e) {
  const count = e.count || 1;

  likeScore += count / 15;
  likeScoreEl.textContent = Math.round(likeScore);

  const last = likeProgress;
  likeProgress = Math.min(1, likeScore / LIKE_TARGET);
  likeProgress = applyObstaclePenalty(likeProgress, last, hitLikeObstacles, "LIKES");

  setBallPosition(ballLikeEl, likeProgress);

  if (likeProgress >= 1) onRaceEnd("LIKES");
}

// ===============================
// FIN DE COURSE
// ===============================
function onRaceEnd(winner) {
  flashFinish(winner);
}

function flashFinish(winner) {
  const flash = document.createElement("div");
  flash.style.position = "fixed";
  flash.style.inset = "0";
  flash.style.background = winner === "GIFTS"
    ? "rgba(255,215,0,0.45)"
    : "rgba(255,0,255,0.45)";
  flash.style.zIndex = "999";
  flash.style.transition = "opacity .5s";
  document.body.appendChild(flash);

  setTimeout(() => {
    flash.style.opacity = "0";
    setTimeout(() => flash.remove(), 500);
  }, 50);
}
