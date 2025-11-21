console.log("[marble] JS chargé");

// ===============================
// 🔗 CONNEXION AU BACKEND OVH
// ===============================
let ipcRenderer = null;
let socket = null;

try {
  if (window.require) {
    const electron = window.require("electron");
    ipcRenderer = electron.ipcRenderer;
  }
} catch {
  console.warn("[marble] ipcRenderer non dispo (navigateur).");
}

// username depuis l'URL (comme Slot / Dark)
const urlParams = new URLSearchParams(window.location.search);
const USERNAME = urlParams.get("username") || "songmicon";

// Backend OVH
const SOCKET_URL = "http://51.38.238.227:5000";

// scores bruts
let giftScore = 0;
let likeScore = 0;

// progression 0 → 1 sur la piste
let giftProgress = 0;
let likeProgress = 0;

// obstacles virtuels (positions sur la piste 0 → 1)
const OBSTACLE_POSITIONS = [0.2, 0.45, 0.7, 0.85];
let hitGiftObstacles = new Set();
let hitLikeObstacles = new Set();

// cibles de course (ajustables)
const GIFT_TARGET = 50;   // nb de "points cadeaux" pour finir
const LIKE_TARGET = 500;  // nb de "points likes" pour finir

// pour l'affichage DOM
let giftScoreEl, likeScoreEl;
let pathEl, totalLength;
let ballGiftEl, ballLikeEl;
let obstaclesGroup;

// ===============================
// 🎬 INITIALISATION DOM / SVG
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
  console.log("[MARBLE] Longueur de piste =", totalLength);

  // placer obstacles visuels
  createObstacles();

  // position initiale des billes
  setBallPosition(ballGiftEl, 0);
  setBallPosition(ballLikeEl, 0);

  connectSocket();
});

// ===============================
// 🔵 SOCKET.IO
// ===============================
function connectSocket() {
  try {
    console.log("[MARBLE] Connexion Socket.IO →", SOCKET_URL, "username =", USERNAME);

    socket = io(SOCKET_URL, {
      transports: ["websocket"],
      query: { username: USERNAME }
    });

    socket.on("connect", () => {
      console.log("🟢 [MARBLE] Connecté au backend OVH, id:", socket.id);
    });

    socket.on("disconnect", () => {
      console.warn("🔴 [MARBLE] Déconnecté du backend OVH");
    });

    socket.on("ia:event", (data) => {
      console.log("📩 [MARBLE] Event reçu :", data);

      if (!data || data.target && data.target !== USERNAME) return;

      if (data.type === "gift") handleGiftEvent(data);
      if (data.type === "like") handleLikeEvent(data);
    });
  } catch (err) {
    console.error("❌ [MARBLE] Erreur Socket.IO :", err);
  }
}

// ===============================
// 🧮 UTILITAIRES PISTE
// ===============================
function setBallPosition(ballEl, progress) {
  if (!pathEl || !ballEl) return;
  const clamped = Math.max(0, Math.min(1, progress));
  const dist = clamped * totalLength;
  const point = pathEl.getPointAtLength(dist);
  ballEl.setAttribute("cx", point.x);
  ballEl.setAttribute("cy", point.y);
}

function createObstacles() {
  obstaclesGroup.innerHTML = "";
  OBSTACLE_POSITIONS.forEach((p) => {
    const dist = p * totalLength;
    const pt = pathEl.getPointAtLength(dist);
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", pt.x);
    c.setAttribute("cy", pt.y);
    c.setAttribute("r", 10);
    c.setAttribute("class", "obstacle");
    obstaclesGroup.appendChild(c);
  });
}

// vérifie collision "logique" avec obstacles
function applyObstaclePenalty(progress, lastProgress, hitSet, label) {
  let newProgress = progress;
  OBSTACLE_POSITIONS.forEach((pos) => {
    if (lastProgress < pos && newProgress >= pos && !hitSet.has(pos)) {
      // on vient de rentrer dans un obstacle
      console.log(`[MARBLE] ${label} touche obstacle @`, pos);
      hitSet.add(pos);
      newProgress = Math.max(0, newProgress - 0.05); // petit recul
    }
  });
  return newProgress;
}

// ===============================
// 🎁 CADEAUX
// ===============================
function handleGiftEvent(event) {
  const giftName = (event.gift || "").toLowerCase();
  const count = event.count || 1;

  // poids des cadeaux : 1 cadeau = 1 point par défaut
  let power = count;
  // si tu veux booster certains cadeaux :
  if (giftName.includes("lion") || giftName.includes("univers")) {
    power *= 5;
  }

  giftScore += power;
  giftScoreEl.textContent = giftScore;

  const last = giftProgress;
  giftProgress = Math.min(1, giftScore / GIFT_TARGET);

  // obstacles → pénalité
  giftProgress = applyObstaclePenalty(giftProgress, last, hitGiftObstacles, "GIFTS");

  setBallPosition(ballGiftEl, giftProgress);

  if (giftProgress >= 1) {
    onRaceEnd("GIFTS");
  }
}

// ===============================
// ❤️ LIKES
// ===============================
function handleLikeEvent(event) {
  const count = event.count || 1;

  // likes → beaucoup plus nombreux → on divise
  const power = count / 20; // à ajuster

  likeScore += power;
  likeScoreEl.textContent = Math.round(likeScore);

  const last = likeProgress;
  likeProgress = Math.min(1, likeScore / LIKE_TARGET);

  likeProgress = applyObstaclePenalty(likeProgress, last, hitLikeObstacles, "LIKES");

  setBallPosition(ballLikeEl, likeProgress);

  if (likeProgress >= 1) {
    onRaceEnd("LIKES");
  }
}

// ===============================
// 🏁 FIN DE COURSE
// ===============================
function onRaceEnd(winner) {
  console.log("🏁 COURSE TERMINÉE — gagnant :", winner);
  // pour l’instant : juste un log + léger flash
  flashFinish(winner);
}

function flashFinish(winner) {
  const flash = document.createElement("div");
  flash.style.position = "fixed";
  flash.style.top = "0";
  flash.style.left = "0";
  flash.style.width = "100vw";
  flash.style.height = "100vh";
  flash.style.zIndex = "9999";
  flash.style.pointerEvents = "none";
  flash.style.background =
    winner === "GIFTS"
      ? "rgba(255,215,0,0.4)"
      : "rgba(255,105,180,0.4)";
  flash.style.transition = "opacity 0.5s";
  document.body.appendChild(flash);

  setTimeout(() => {
    flash.style.opacity = "0";
    setTimeout(() => flash.remove(), 500);
  }, 80);
}
