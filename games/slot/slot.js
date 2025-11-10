// ======================================================
// slot.js — Mini-jeu Machine à sous InterArcade (version stable TikTok Live)
// ======================================================

const { ipcRenderer } = require("electron");

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

  // 🧩 Récupère le pseudo du joueur depuis main.js
  ipcRenderer
    .invoke("get-player")
    .then((player) => {
      playerEl.textContent = `Bienvenue ${player || "Joueur anonyme"} !`;
    })
    .catch((err) => console.error("Erreur get-player :", err));

  // 🎮 Bouton manuel (test)
  spinBtn.addEventListener("click", () => {
    enqueueSpin({ from: "Test", gift: "Manuel", count: 1 });
  });

  // 🎁 Réception d’un spin automatique depuis InterArcade (TikTok gift)
  ipcRenderer.on("slot:spin", (_evt, payload) => {
    console.log("🎯 Événement cadeau reçu :", payload);
    enqueueSpin(payload);
  });

  // 🧠 Réception du joueur actif depuis main.js
  ipcRenderer.on("slot:player", (_evt, playerName) => {
    if (!currentPlayerEl) return;
    currentPlayerEl.textContent = `🎰 ${playerName} is spinning...`;
    currentPlayerEl.style.opacity = "1";

    setTimeout(() => {
      currentPlayerEl.style.opacity = "0";
    }, 3500);
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
    // 🔁 Si d’autres cadeaux sont en attente, on relance la suivante
    if (spinQueue.length > 0) maybeSpinNext();
  }

  // === ANIMATION DU SPIN ===
  async function runSpinAnimation(event) {
    const symbols = ["🍒", "💎", "🔔", "⭐", "🍀"];
    const spinCount = 12; // nombre de rotations avant le résultat final
    const spinSpeed = 80; // vitesse en ms par "frame"

    resultEl.textContent = `🎁 ${event.from} envoie ${event.gift} x${event.count}`;
    playSound("spin-start");

    // 🎞️ Animation rapide des rouleaux
    for (let i = 0; i < spinCount; i++) {
      reels.forEach((r) => {
        r.textContent = symbols[Math.floor(Math.random() * symbols.length)];
      });
      await delay(spinSpeed);
    }

    // 🎯 Résultat final aléatoire
    const results = Array.from(reels).map(
      () => symbols[Math.floor(Math.random() * symbols.length)]
    );
    reels.forEach((r, i) => (r.textContent = results[i]));

    // 🔍 Vérification du résultat
    const unique = new Set(results).size;
    if (unique === 1) {
      resultEl.textContent = `🎉 JACKPOT pour ${event.from} ! (${event.gift})`;
      playSound("jackpot");
    } else if (unique === 2) {
      resultEl.textContent = `✨ Deux symboles identiques ! Bien joué ${event.from}`;
      playSound("small-win");
    } else {
      resultEl.textContent = `😅 Merci ${event.from} pour le ${event.gift}`;
      playSound("fail");
    }

    await delay(1000);
  }

  // === UTILITAIRES ===
  function delay(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // === EFFETS SONORES SIMPLES ===
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
