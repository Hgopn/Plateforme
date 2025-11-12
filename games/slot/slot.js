// ======================================================
// slot.js — Mini-jeu Machine à sous InterArcade (version stable TikTok Live / Render compatible)
// ======================================================

// --- Variables globales ---
let spinning = false;
const spinQueue = [];

// === INITIALISATION ===
document.addEventListener("DOMContentLoaded", () => {
  const playerEl = document.getElementById("player");
  const resultEl = document.getElementById("result");
  const spinBtn = document.getElementById("spin-btn");
  const reels = document.querySelectorAll(".reel");
  const currentPlayerEl = document.getElementById("current-player"); // ✅ nouvel élément

  // --- Compatibilité : si Electron existe, on le garde, sinon on passe par window ---
  let ipcRenderer = null;
  try {
    if (window.require) {
      const electron = window.require("electron");
      ipcRenderer = electron.ipcRenderer;
    }
  } catch {
    console.warn("⚠️ ipcRenderer non disponible, passage en mode postMessage.");
  }

  // 🎮 Bouton manuel (test local)
  spinBtn.addEventListener("click", () => {
    enqueueSpin({ from: "Test", gift: "Manuel", count: 1 });
  });

  // 🧩 Si ipcRenderer est dispo → écoute des événements Electron
  if (ipcRenderer) {
    ipcRenderer
      .invoke("get-player")
      .then((player) => {
        if (playerEl)
          playerEl.textContent = `Bienvenue ${player || "Joueur anonyme"} !`;
      })
      .catch((err) => console.error("Erreur get-player :", err));

    ipcRenderer.on("slot:spin", (_evt, payload) => {
      console.log("🎯 Événement cadeau reçu (Electron) :", payload);
      enqueueSpin(payload);
    });

    ipcRenderer.on("slot:player", (_evt, playerName) => {
      if (!currentPlayerEl) return;
      currentPlayerEl.textContent = `🎰 ${playerName} is spinning...`;
      currentPlayerEl.style.opacity = "1";
      setTimeout(() => (currentPlayerEl.style.opacity = "0"), 3500);
    });
  }

  // 🧠 Sinon → on écoute les messages via window.postMessage
  window.addEventListener("message", (event) => {
    const data = event.data;
    if (data?.type === "slot:spin") {
      console.log("📩 Spin reçu via window.postMessage :", data);
      enqueueSpin(data);
    } else if (data?.type === "slot:player") {
      if (currentPlayerEl) {
        currentPlayerEl.textContent = `🎰 ${data.username} is spinning...`;
        currentPlayerEl.style.opacity = "1";
        setTimeout(() => (currentPlayerEl.style.opacity = "0"), 3500);
      }
    }
  });

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

  // === ANIMATION DU SPIN ===
  async function runSpinAnimation(event) {
    const symbols = ["🍒", "💎", "🔔", "⭐", "🍀"];
    const spinCount = 12;
    const spinSpeed = 80;

    resultEl.textContent = `🎁 ${event.from || "Viewer"} envoie ${event.gift || "cadeau"} x${event.count || 1}`;
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
      resultEl.textContent = `🎉 JACKPOT pour ${event.from || "Viewer"} ! (${event.gift})`;
      playSound("jackpot");
    } else if (unique === 2) {
      resultEl.textContent = `✨ Deux symboles identiques ! Bien joué ${event.from || "Viewer"}`;
      playSound("small-win");
    } else {
      resultEl.textContent = `😅 Merci ${event.from || "Viewer"} pour le ${event.gift || "cadeau"}`;
      playSound("fail");
    }

    await delay(1000);
  }

  // === UTILITAIRES ===
  function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // === EFFETS SONORES ===
  function playSound(type) {
    const audio = document.createElement("audio");
    if (type === "spin-start") audio.src = "../assets/sound_spin.mp3";
    else if (type === "jackpot") audio.src = "../assets/sound_jackpot.mp3";
    else if (type === "small-win") audio.src = "../assets/sound_smallwin.mp3";
    else audio.src = "../assets/sound_fail.mp3";
    audio.volume = 0.3;
    audio.play().catch(() => {});
  }
});
