// ================================
// Inter Fight Arena — fight.js
// VERSION STABLE V1 (sans TikTok)
// ================================

console.log("⚔️ Inter Fight Arena prêt (V1)");
console.log("👉 Tape testFight() dans la console pour tester");

// -------------------------------
// DATA
// -------------------------------
const teams = {
  left: {
    hp: 100,
    players: []
  },
  right: {
    hp: 100,
    players: []
  }
};

// -------------------------------
// ELEMENTS (sécurisés)
// -------------------------------
const leftPlayersEl = document.getElementById("players-left");
const rightPlayersEl = document.getElementById("players-right");

const hpLeftEl = document.getElementById("hp-left");
const hpRightEl = document.getElementById("hp-right");

// -------------------------------
// SAFE HELPERS
// -------------------------------
function safeStyle(el, prop, value) {
  if (!el) return;
  el.style[prop] = value;
}

// -------------------------------
// UPDATE UI
// -------------------------------
function renderPlayers() {
  if (leftPlayersEl) {
    leftPlayersEl.innerHTML = "";
    teams.left.players.forEach(p => {
      const div = document.createElement("div");
      div.className = "player";
      div.textContent = p;
      leftPlayersEl.appendChild(div);
    });
  }

  if (rightPlayersEl) {
    rightPlayersEl.innerHTML = "";
    teams.right.players.forEach(p => {
      const div = document.createElement("div");
      div.className = "player";
      div.textContent = p;
      rightPlayersEl.appendChild(div);
    });
  }
}

function updateTeamHP() {
  safeStyle(hpLeftEl, "width", teams.left.hp + "%");
  safeStyle(hpRightEl, "width", teams.right.hp + "%");
}

// -------------------------------
// GAME LOGIC
// -------------------------------
function joinTeam(username, team) {
  if (teams.left.players.includes(username) || teams.right.players.includes(username)) {
    return;
  }

  teams[team].players.push(username);
  console.log(`✅ ${username} a rejoint l'équipe ${team}`);
  renderPlayers();
}

function attack(fromTeam, damage = 10) {
  const target = fromTeam === "left" ? "right" : "left";
  teams[target].hp -= damage;
  if (teams[target].hp < 0) teams[target].hp = 0;

  console.log(`💥 Attaque ${fromTeam} → ${target} (-${damage} HP)`);
  updateTeamHP();
}

// -------------------------------
// TEST MODE (LOCAL)
// -------------------------------
window.testFight = function () {
  joinTeam("Alice", "left");
  joinTeam("Bob", "right");
  joinTeam("Charlie", "left");
  joinTeam("David", "right");

  setTimeout(() => attack("left"), 500);
  setTimeout(() => attack("right"), 1000);
};
