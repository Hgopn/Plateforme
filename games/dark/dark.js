console.log("DARK.JS chargé");

// ==================================
// 🔗 CONNEXION AU BACKEND INTERARCADE
// ==================================
let ipcRenderer = null;
let socket = null;

// Compatibilité Electron
try {
  if (window.require) {
    const electron = window.require("electron");
    ipcRenderer = electron.ipcRenderer;
  }
} catch {
  console.warn("ipcRenderer non disponible (navigateur)");
}

// Récupération username (comme Slot)
const urlParams = new URLSearchParams(window.location.search);
const USERNAME = urlParams.get("username") || "songmicon";

// Backend OVH
const SOCKET_URL = "http://51.38.238.227:5000";

// Connexion Socket.IO
try {
  console.log("🔌 [DARK] Connexion Socket.IO à", SOCKET_URL);

  socket = io(SOCKET_URL, {
    transports: ["websocket"],
    query: { username: USERNAME }
  });

  socket.on("connect", () => {
    console.log("🟢 [DARK] Connecté au backend OVH");
  });

  socket.on("disconnect", () => {
    console.warn("🔴 [DARK] Déconnecté du backend OVH");
  });

  // 🎁 Réception des événements TikTok
  socket.on("ia:event", (data) => {
    console.log("📩 [DARK] Event reçu :", data);

    if (data && data.type === "gift") onGiftEvent(data);
    if (data && data.type === "like") onLikeEvent(data);
  });

} catch (err) {
  console.error("❌ Erreur Socket.IO :", err);
}


// ==================================
// 🔥 Lumière & tremblements
// ==================================
let baseLightRadius = 0.9;        // plus petit = plus difficile
let currentLightRadius = baseLightRadius;
let shakeIntensity = 2;

// ==================================
// 🔥 AJOUT — Niveau affiché en haut
// ==================================
let currentLevel = 0;
function updateLevelDisplay() {
  const el = document.getElementById("level-display");
  if (el) el.textContent = "LEVEL " + (currentLevel + 1);
}

// ========================
// 🧩 NIVEAUX
// 0 = mur, 1 = chemin, 2 = sortie, 3 = spawn
// ========================
const LEVELS = [

  // LEVEL 1 — 10×10
  [
    [1,1,1,1,1,1,1,1,1,1],
    [1,3,0,0,0,1,0,0,0,1],
    [1,0,1,1,0,1,0,1,0,1],
    [1,0,1,0,0,0,0,1,0,1],
    [1,0,1,0,1,1,0,0,0,1],
    [1,0,0,0,0,1,1,1,0,1],
    [1,1,1,1,0,0,0,1,0,1],
    [1,0,0,1,0,1,0,1,0,1],
    [1,0,0,0,0,1,0,0,2,1],
    [1,1,1,1,1,1,1,1,1,1],
  ],

  // LEVEL 2 — 15×15
  [
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,3,0,0,1,0,0,0,1,0,0,0,0,0,1],
    [1,0,1,0,1,0,1,0,1,0,1,1,1,0,1],
    [1,0,1,0,0,0,1,0,0,0,0,0,1,0,1],
    [1,0,1,1,1,0,1,1,1,1,1,0,1,0,1],
    [1,0,0,0,1,0,0,0,0,1,0,0,1,0,1],
    [1,1,1,0,1,1,1,1,0,1,1,0,1,0,1],
    [1,0,0,0,0,0,0,1,0,0,0,0,1,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,0,1,0,1],
    [1,0,1,0,0,0,0,0,0,0,1,0,1,0,1],
    [1,0,1,0,1,1,1,1,1,0,1,0,1,0,1],
    [1,0,0,0,1,0,0,0,1,0,0,0,1,0,1],
    [1,1,1,0,1,0,1,0,1,1,1,0,1,0,1],
    [1,0,0,0,0,0,1,0,0,0,1,0,0,2,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
  ],

  // LEVEL 3 — 15×15 (simple)
  [
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,3,0,0,0,0,1,0,0,0,1,0,0,0,1],
    [1,0,1,1,1,0,1,0,1,0,1,0,1,0,1],
    [1,0,1,0,0,0,1,0,1,0,1,0,1,0,1],
    [1,0,1,0,1,1,1,0,1,0,1,0,1,0,1],
    [1,0,0,0,0,0,0,0,1,0,0,0,0,0,1],
    [1,1,1,1,1,1,0,1,1,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,1,0,0,0,1,0,0,1],
    [1,0,1,1,1,1,0,1,1,1,0,1,1,0,1],
    [1,0,1,0,0,0,0,0,0,1,0,0,1,0,1],
    [1,0,1,0,1,1,1,1,0,1,1,0,1,0,1],
    [1,0,0,0,1,0,0,0,1,0,0,0,1,0,1],
    [1,1,1,0,1,1,1,0,1,1,1,0,1,0,1],
    [1,0,0,0,0,0,0,0,0,0,1,0,0,2,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
  ]

];

let map = LEVELS[0];

// ✅ MODIF: player a maintenant une direction
let player = { x: 1, y: 1, dir: "down" };

let tileSize = 50;


// ==================================
// ✅ MODIF: CHARGEMENT DES IMAGES (UNE SEULE FOIS)
// Mets tes PNG ici : images/player_up.png etc.
// ==================================
const playerImages = {
  up: new Image(),
  down: new Image(),
  left: new Image(),
  right: new Image()
};

playerImages.up.src = "assets/player_up.png";
playerImages.down.src = "assets/player_down.png";
playerImages.left.src = "assets/player_left.png";
playerImages.right.src = "assets/player_right.png";


// ========================
// 🧱 LABYRINTHE (DOM)
// ========================
const mazeEl = document.getElementById("maze");

function applyGridSize() {
  const rows = map.length;
  const cols = map[0].length;
  tileSize = 500 / cols;
  mazeEl.style.gridTemplateColumns = `repeat(${cols}, ${tileSize}px)`;
  mazeEl.style.gridTemplateRows = `repeat(${rows}, ${tileSize}px)`;
}

function renderMaze() {
  mazeEl.innerHTML = "";
  applyGridSize();

  map.forEach(row => {
    row.forEach(cell => {
      const div = document.createElement("div");
      div.className = "cell " + (cell === 0 ? "wall" : "path");

      if (cell === 2) {
        div.style.background = "#FFD700";
        div.style.border = "2px solid white";
      }

      mazeEl.appendChild(div);
    });
  });
}

function initPlayerFromSpawn() {
  for (let y = 0; y < map.length; y++) {
    for (let x = 0; x < map[0].length; x++) {
      if (map[y][x] === 3) {
        player.x = x;
        player.y = y;
        // on garde la direction actuelle
        return;
      }
    }
  }
}

renderMaze();
initPlayerFromSpawn();
updateLevelDisplay();


// ========================
// 🌑 CANVAS + LUMIÈRE
// ========================
const canvas = document.createElement("canvas");
canvas.width = 500;
canvas.height = 500;
canvas.style.position = "absolute";
canvas.style.zIndex = "3";
canvas.style.pointerEvents = "none";
document.getElementById("game-container").appendChild(canvas);

const ctx = canvas.getContext("2d");

// ✅ MODIF: drawPlayer dessine le PNG selon la direction
function drawPlayer() {
  const px = player.x * tileSize;
  const py = player.y * tileSize;

  const img = playerImages[player.dir];

  // taille du perso (80% de la case) + centrage
  const size = tileSize * 0.8;
  const offset = (tileSize - size) / 2;

  // fallback si image pas encore chargée → carré blanc (pour éviter bug visuel)
  if (!img || !img.complete) {
    ctx.fillStyle = "white";
    ctx.fillRect(px + tileSize * 0.3, py + tileSize * 0.3, tileSize * 0.4, tileSize * 0.4);
    return;
  }

  ctx.drawImage(img, px + offset, py + offset, size, size);
}

function drawLight() {
  ctx.clearRect(0, 0, 500, 500);

  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "black";
  ctx.fillRect(0, 0, 500, 500);

  let cx = player.x * tileSize + tileSize / 2;
  let cy = player.y * tileSize + tileSize / 2;

  cx += (Math.random() - 0.5) * shakeIntensity;
  cy += (Math.random() - 0.5) * shakeIntensity;

  const radius = tileSize * currentLightRadius;

  ctx.globalCompositeOperation = "destination-out";
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fill();

  ctx.globalCompositeOperation = "source-over";
  drawPlayer();
}

setInterval(drawLight, 50);


// ========================
// 🎮 PASSAGE DE NIVEAU
// ========================
function nextLevel() {
  currentLevel++;

  if (!LEVELS[currentLevel]) {
    alert("🎉 Tous les niveaux terminés !");
    return;
  }

  map = LEVELS[currentLevel];
  renderMaze();
  initPlayerFromSpawn();
  updateLevelDisplay();
}


// ========================
// 🎮 DÉPLACEMENT
// ========================
function move(dx, dy) {
  // ✅ MODIF: on met à jour la direction AVANT de bouger
  if (dx === 1) player.dir = "right";
  if (dx === -1) player.dir = "left";
  if (dy === 1) player.dir = "down";
  if (dy === -1) player.dir = "up";

  const nx = player.x + dx;
  const ny = player.y + dy;

  if (ny < 0 || ny >= map.length) return;
  if (nx < 0 || nx >= map[0].length) return;

  const cell = map[ny][nx];

  if (cell === 0) return;

  if (cell === 2) {
    nextLevel();
    return;
  }

  player.x = nx;
  player.y = ny;
}

document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowUp") move(0, -1);
  if (e.key === "ArrowDown") move(0, 1);
  if (e.key === "ArrowLeft") move(-1, 0);
  if (e.key === "ArrowRight") move(1, 0);
});

document.querySelectorAll("#controls button").forEach(btn => {
  btn.addEventListener("click", () => {
    const dir = btn.dataset.dir;
    if (dir === "up") move(0, -1);
    if (dir === "down") move(0, 1);
    if (dir === "left") move(-1, 0);
    if (dir === "right") move(1, 0);
  });
});


// ==================================
// 🎁 EFFETS DES CADEAUX
// ==================================
function onGiftEvent(event) {
  const gift = event.gift?.toLowerCase() || "";
  const count = event.count || 1;

  console.log("🎁 Cadeau :", gift, "x" + count);

  // Rose → +10% lumière 1 sec
  if (gift.includes("rose")) {
    radiusTemporaryBoost(0.10, 1000);
  }

  // Pistolet → flash
  if (gift.includes("pistolet")) {
    flashScreen();
  }

  // Tous les cadeaux → petit boost court
  radiusTemporaryBoost(0.05 * count, 600);
}


// ==================================
// ❤️ EFFETS DES LIKES
// ==================================
function onLikeEvent(event) {
  console.log("❤️ Like reçu :", event.count);
  shakeTemporaryBoost(3, 700);
}


// ==================================
// 🔆 BOOSTS GÉNÉRIQUES
// ==================================
function radiusTemporaryBoost(percent, duration) {
  currentLightRadius = baseLightRadius + percent;
  setTimeout(() => {
    currentLightRadius = baseLightRadius;
  }, duration);
}

function shakeTemporaryBoost(level, duration) {
  shakeIntensity = level;
  setTimeout(() => {
    shakeIntensity = 2;
  }, duration);
}


// ==================================
// ⚡ FLASH ÉCRAN
// ==================================
function flashScreen() {
  const flash = document.createElement("div");
  flash.style.position = "absolute";
  flash.style.top = "0";
  flash.style.left = "0";
  flash.style.width = "500px";
  flash.style.height = "500px";
  flash.style.background = "white";
  flash.style.opacity = "1";
  flash.style.zIndex = "10";
  flash.style.transition = "opacity 0.3s";
  document.getElementById("game-container").appendChild(flash);

  setTimeout(() => {
    flash.style.opacity = "0";
    setTimeout(() => flash.remove(), 300);
  }, 50);
}
