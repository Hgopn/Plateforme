console.log("DARK.JS chargé");

// 🔥 AJOUT — Niveau affiché en haut
let currentLevel = 0;  
function updateLevelDisplay() {
  const el = document.getElementById("level-display");
  if (el) el.textContent = "LEVEL " + (currentLevel + 1);
}

// ========================
// 🧩 NIVEAUX (LEVEL 1 + LEVEL 2)
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
  ]
];

let map = LEVELS[0];
let player = { x: 1, y: 1 };
let tileSize = 50;


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
        return;
      }
    }
  }
}

renderMaze();
initPlayerFromSpawn();

// 🔥 AJOUT
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

function drawPlayer() {
  const px = player.x * tileSize;
  const py = player.y * tileSize;

  ctx.fillStyle = "white";
  ctx.fillRect(px + tileSize * 0.3, py + tileSize * 0.3, tileSize * 0.4, tileSize * 0.4);
}

function drawLight() {
  ctx.clearRect(0, 0, 500, 500);

  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "black";
  ctx.fillRect(0, 0, 500, 500);

  let cx = player.x * tileSize + tileSize / 2;
  let cy = player.y * tileSize + tileSize / 2;

  cx += (Math.random() - 0.5) * 2;
  cy += (Math.random() - 0.5) * 2;

  const radius = tileSize * 1.4;

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

  // 🔥 AJOUT
  updateLevelDisplay();
}


// ========================
// 🎮 DÉPLACEMENT
// ========================
function move(dx, dy) {
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
