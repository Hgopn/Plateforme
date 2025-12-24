// ================================
// Inter Fight Arena — fight.js
// VERSION STABLE V2 (stickmans visuels)
// ================================

console.log("⚔️ Inter Fight Arena prêt (V2 – stickmans)");

// -------------------------------
// CONFIG
// -------------------------------
const STICKMAN_IMG = "stickman.png"; // chemin relatif
const MAX_HP = 100;

// -------------------------------
// DATA
// -------------------------------
const teams = {
  left: {
    hp: MAX_HP,
    players: []
  },
  right: {
    hp: MAX_HP,
    players: []
  }
};

// -------------------------------
// ELEMENTS
// -------------------------------
const leftPlayersEl = document.getElementById("players-left");
const rightPlayersEl = document.getElementById("players-right");

const hpLeftEl = document.getElementById("hp-left");
const hpRightEl = document.getElementById("hp-right");

// -------------------------------
// HELPERS
// -------------------------------
function safeStyle(el, prop, value) {
  if (!el) return;
  el.style[prop] = value;
}

function createStickman(username, team) {
  const wrapper = document.createElement("div");
  wrapper.className = "player";
  wrapper.dataset.user = username;

  wrapper.style.display = "flex";
  wrapper.style.flexDirection = "column";
  wrapper.style.alignItems = "center";
  wrapper.style.gap = "4px";

  // pseudo
  const name = document.createElement("div");
  name.textContent = username;
  name.style.fontSize = "11px";
  name.style.opacity = "0.85";

  // image
  const img = document.createElement("img");
  img.src = STICKMAN_IMG;
  img.alt = "stickman";
  img.style.width = "40px";
  img.style.height = "40px";
  img.style.objectFit = "contain";

  // couleur équipe
  img.style.filter =
    team === "left"
      ? "drop-shadow(0 0 6px #3b82f6)"
      : "drop-shadow(0 0 6px #ef4444)";

  wrapper.appendChild(name);
  wrapper.appendChild(img);

  return wrapper;
}

// -------------------------------
// UI UPDATE
// -------------------------------
function renderPlayers() {
  if (leftPlayersEl) leftPlayersEl.innerHTML = "";
  if (rightPlayersEl) rightPlayersEl.innerHTML = "";

  teams.left.players.forEach(p => {
    const stickman = createStickman(p, "left");
    leftPlayersEl.appendChild(stickman);
  });

  teams.right.players.forEach(p => {
    const stickman = createStickman(p, "right");
    rightPlayersEl.appendChild(stickman);
  });
}

function updateTeamHP() {
  safeStyle(hpLeftEl, "width", teams.left.hp + "%");
  safeStyle(hpRightEl, "width", teams.right.hp + "%");
}

// -------------------------------
// GAME LOGIC
// -------------------------------
function joinTeam(username, team) {
  if (!teams[team]) return;

  if (
    teams.left.players.includes(username) ||
    teams.right.players.includes(username)
  ) {
    console.log(`⚠️ ${username} est déjà dans une équipe`);
    return;
  }

  teams[team].players.push(username);
  console.log(`✅ ${username} rejoint l'équipe ${team.toUpperCase()}`);
  renderPlayers();
}

function attack(fromTeam, damage = 10) {
  const target = fromTeam === "left" ? "right" : "left";

  teams[target].hp -= damage;
  if (teams[target].hp < 0) teams[target].hp = 0;

  console.log(`💥 ${fromTeam} attaque ${target} (-${damage} HP)`);
  updateTeamHP();
}

// -------------------------------
// TEST MODE
// -------------------------------
window.testFight = function () {
  joinTeam("Alice", "left");
  joinTeam("Bob", "right");
  joinTeam("Charlie", "left");
  joinTeam("David", "right");

  setTimeout(() => attack("left", 15), 800);
  setTimeout(() => attack("right", 20), 1600);
};
