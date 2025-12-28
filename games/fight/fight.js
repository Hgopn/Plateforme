// ================================
// Inter Fight Arena — fight.js
// VERSION STABLE V3 (CSS-driven)
// ================================

console.log("⚔️ Inter Fight Arena prêt (V3)");

// -------------------------------
// CONFIG
// -------------------------------
const STICKMAN_IMG = "./stickman.png";
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
// UI HELPERS
// -------------------------------
function updateTeamHP() {
  if (hpLeftEl) hpLeftEl.style.width = teams.left.hp + "%";
  if (hpRightEl) hpRightEl.style.width = teams.right.hp + "%";
}

// -------------------------------
// STICKMAN FACTORY (SANS STYLE)
// -------------------------------
function createStickman(username) {
  const wrapper = document.createElement("div");
  wrapper.className = "player";
  wrapper.dataset.user = username;

  const img = document.createElement("img");
  img.src = STICKMAN_IMG;
  img.alt = username;
  img.draggable = false;

  const name = document.createElement("span");
  name.textContent = username;

  wrapper.appendChild(img);
  wrapper.appendChild(name);

  return wrapper;
}

// -------------------------------
// RENDER
// -------------------------------
function renderPlayers() {
  if (leftPlayersEl) leftPlayersEl.innerHTML = "";
  if (rightPlayersEl) rightPlayersEl.innerHTML = "";

  teams.left.players.forEach(username => {
    leftPlayersEl.appendChild(createStickman(username));
  });

  teams.right.players.forEach(username => {
    rightPlayersEl.appendChild(createStickman(username));
  });
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
    console.log(`⚠️ ${username} déjà dans une équipe`);
    return;
  }

  teams[team].players.push(username);
  console.log(`✅ ${username} rejoint ${team.toUpperCase()}`);
  renderPlayers();
}

function attack(fromTeam, damage = 10) {
  const target = fromTeam === "left" ? "right" : "left";
  teams[target].hp = Math.max(0, teams[target].hp - damage);
  console.log(`💥 ${fromTeam} attaque ${target} (-${damage})`);
  updateTeamHP();
}

// -------------------------------
// TEST LOCAL
// -------------------------------
window.testFight = function () {
  joinTeam("Alice", "left");
  joinTeam("Bob", "right");
  joinTeam("Charlie", "left");
  joinTeam("David", "right");

  setTimeout(() => attack("left", 15), 800);
  setTimeout(() => attack("right", 20), 1600);
};
