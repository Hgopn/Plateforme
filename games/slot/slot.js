// ======================================================
// slot.js — Machine à sous InterArcade (OVH + TikTok Live)
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

  // --- Compatibilité Electron ---
  let ipcRenderer = null;
  try {
    if (window.require) {
      const electron = window.require("electron");
      ipcRenderer = electron.ipcRenderer;
    }
  } catch {
    console.warn("⚠️ ipcRenderer non disponible (mode navigateur).");
  }

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
    currentPlayerEl.textContent = `🎮 ${name}`;
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
      .slice(0, 5)
      .forEach(([name, score]) => {
        const li = document.createElement("li");
        li.innerHTML = `<span>${name}</span><span>${score}</span>`;
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
    playSound("spin-start");

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
      playSound("jackpot");
    } else if (unique === 2) {
      scores[playerName] += 25;
      resultEl.textContent = `✨ Deux symboles identiques ! Bien joué ${playerName}`;
      playSound("small-win");
    } else {
      scores[playerName] += 5;
      resultEl.textContent = `😅 Merci ${playerName} pour le soutien`;
      playSound("fail");
    }

    updateLeaderboard();
    await delay(1000);
  }

  // === UTILITAIRES ===
  function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function playSound(type) {
    const audio = document.createElement("audio");
    if (type === "spin-start") audio.src = "../assets/sound_spin.mp3";
    else if (type === "jackpot") audio.src = "../assets/sound_jackpot.mp3";
    else if (type === "small-win") audio.src = "../assets/sound_smallwin.mp3";
    else audio.src = "../assets/sound_fail.mp3";
    audio.volume = 0.3;
    audio.play().catch(() => {});
  }

  // 🎮 Bouton manuel (test local)
  spinBtn.addEventListener("click", () => {
    enqueueSpin({ from: "Test", gift: "Manuel", count: 1 });
  });

  // ======================================================
  // 🔗 Connexion Socket.IO vers ton serveur OVH (InterArcade)
  // ======================================================

  const urlParams = new URLSearchParams(window.location.search);
  const USERNAME = urlParams.get("username") || "songmicon";
  const SOCKET_URL = "http://51.38.238.227:5000";

  let socket = null;
  try {
    socket = io(SOCKET_URL, {
      transports: ["websocket"],
      query: { username: USERNAME }
    });

    socket.on("ia:event", (data) => {
      if (data && data.type === "gift") {
        enqueueSpin(data);
      }
    });

  } catch (err) {
    console.error("❌ Erreur Socket.IO :", err);
  }
});
