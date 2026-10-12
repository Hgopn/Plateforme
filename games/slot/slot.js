// ======================================================
// slot.js — Machine à sous InterArcade
// ======================================================

// --- Variables globales ---
let spinning = false;
const spinQueue = [];
const scores = {};

// === INITIALISATION ===
document.addEventListener("DOMContentLoaded", () => {
  const playerEl = document.getElementById("player");
  const resultEl = document.getElementById("result");
  const spinBtn = document.getElementById("spin-btn");
  const reels = document.querySelectorAll(".reel");
  const currentPlayerEl = document.getElementById("current-player");
  const leaderboardList = document.getElementById("leaderboard-list");

  // ======================================================
  // 🆕 SCALE GLOBAL DU JEU (FIXE, TYPE JEU VIDÉO)
  // ======================================================
  const GAME_WIDTH = 1200;
  const GAME_HEIGHT = 800;
  const gameRoot = document.getElementById("game-root");

  function applyGameScale() {
    if (!gameRoot) return;

    const scaleX = window.innerWidth / GAME_WIDTH;
    const scaleY = window.innerHeight / GAME_HEIGHT;
    const scale = Math.min(scaleX, scaleY);

    gameRoot.style.transform = `scale(${scale})`;
    gameRoot.style.transformOrigin = "top left";
  }

  applyGameScale();
  window.addEventListener("resize", applyGameScale);
  // ======================================================

  // === FILE D’ATTENTE DE SPINS ===
  function enqueueSpin(payload) {
    if (!payload) return;
    spinQueue.push(payload);
    maybeSpinNext();
  }

  async function maybeSpinNext() {
    if (spinning || spinQueue.length === 0) return;
    spinning = true;

    const event = spinQueue.shift();
    try {
      await runSpinAnimation(event);
    } catch (err) {
      console.error("Erreur pendant le spin :", err);
    }

    spinning = false;
    if (spinQueue.length > 0) maybeSpinNext();
  }

  // === AFFICHAGE JOUEUR EN COURS ===
  function showCurrentPlayer(name) {
    currentPlayerEl.textContent = `${name}`;
    currentPlayerEl.classList.add("show");

    clearTimeout(showCurrentPlayer._timer);
    showCurrentPlayer._timer = setTimeout(() => {
      currentPlayerEl.classList.remove("show");
    }, 2500);
  }

  // === LEADERBOARD ===
  function updateLeaderboard() {
    leaderboardList.innerHTML = "";

    Object.entries(scores)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .forEach(([name, score]) => {
        const li = document.createElement("li");
        const nameEl = document.createElement("span");
        const scoreEl = document.createElement("span");
        nameEl.textContent = name;
        scoreEl.textContent = score;
        li.append(nameEl, scoreEl);
        leaderboardList.appendChild(li);
      });
  }

  // === ANIMATION DU SPIN ===
  async function runSpinAnimation(event) {
    const symbols = ["🍒", "💎", "🔔", "⭐", "🍀"];
    const spinCount = 12;
    const spinSpeed = 80;

    const playerName = event.from || "Viewer";
    showCurrentPlayer(playerName);

    if (!scores[playerName]) scores[playerName] = 0;

    resultEl.textContent = `🎁 ${playerName} envoie ${event.gift || "cadeau"} x${event.count || 1}`;
    for (let i = 0; i < spinCount; i++) {
      reels.forEach((r) => {
        r.textContent = symbols[Math.floor(Math.random() * symbols.length)];
      });
      await delay(spinSpeed);
    }

    const results = Array.from(reels).map(
      () => symbols[Math.floor(Math.random() * symbols.length)]
    );
    reels.forEach((r, i) => (r.textContent = results[i]));

    const unique = new Set(results).size;
    if (unique === 1) {
      scores[playerName] += 50;
      resultEl.textContent = `🎉 JACKPOT pour ${playerName} !`;
    } else if (unique === 2) {
      scores[playerName] += 25;
      resultEl.textContent = `✨ Deux symboles identiques ! Bien joué ${playerName}`;
    } else {
      scores[playerName] += 5;
      resultEl.textContent = `😅 Merci ${playerName} pour le soutien`;
    }

    updateLeaderboard();
    await delay(1000);
  }

  // === UTILITAIRES ===
  function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // 🎮 Bouton manuel (test local)
  spinBtn.addEventListener("click", () => {
    enqueueSpin({ from: "Test", gift: "Manuel", count: 1 });
  });

  // ======================================================
  // Connexion Socket.IO InterArcade
  // ======================================================
  const urlParams = new URLSearchParams(window.location.search);
  const SOCKET_URL = window.location.origin;

  let socket = null;
  try {
    socket = io(SOCKET_URL, {
      transports: ["websocket"],
      auth: { token: urlParams.get("token") || "" }
    });

    socket.on("ia:event", (data) => {
      const event = data?.payload || data;
      if (event && data.type === "gift") {
        enqueueSpin({ ...event, from: data.actor || event.from });
      }
    });
  } catch (err) {
    console.error("❌ Erreur Socket.IO :", err);
  }
});
