// ======================================================
// fight.js — Inter Fight Arena (V1)
// Base : équipes + joueurs + commandes chat
// ======================================================

// ===== CONFIG =====
const MAX_HP = 100;

// ===== STATE =====
const players = {}; // { username: { team, hp, el } }

const teams = {
  left: {
    hp: 1000,
    container: document.getElementById("players-left"),
    hpFill: document.getElementById("hp-left"),
  },
  right: {
    hp: 1000,
    container: document.getElementById("players-right"),
    hpFill: document.getElementById("hp-right"),
  },
};

// ======================================================
// 🧍‍♂️ CRÉATION VISUELLE DU JOUEUR
// ======================================================
function createPlayerElement(username, team) {
  const div = document.createElement("div");
  div.className = "player";

  const name = document.createElement("div");
  name.className = "player-name";
  name.textContent = username;

  const body = document.createElement("div");
  body.className = "player-body"; // futur stickman animé

  div.appendChild(name);
  div.appendChild(body);

  return div;
}

// ======================================================
// ➕ AJOUT DANS UNE ÉQUIPE
// ======================================================
function joinTeam(username, team) {
  if (players[username]) {
    console.log(`⛔ ${username} est déjà dans une équipe`);
    return;
  }

  if (!teams[team]) return;

  const playerEl = createPlayerElement(username, team);
  teams[team].container.appendChild(playerEl);

  players[username] = {
    team,
    hp: MAX_HP,
    el: playerEl,
  };

  console.log(`✅ ${username} a rejoint l'équipe ${team}`);
}

// ======================================================
// 💬 SIMULATION DES COMMENTAIRES (V1)
// PLUS TARD → branché sur TikTokLive
// ======================================================
function handleChatCommand(username, message) {
  const msg = message.toLowerCase().trim();

  if (msg === "!left") joinTeam(username, "left");
  if (msg === "!right") joinTeam(username, "right");
}

// ======================================================
// ⚔️ FUTURES MÉCANIQUES (PRÉPARÉES)
// ======================================================
function attack(attackerName, damage = 20) {
  const attacker = players[attackerName];
  if (!attacker) return;

  const enemyTeam = attacker.team === "left" ? "right" : "left";
  teams[enemyTeam].hp = Math.max(0, teams[enemyTeam].hp - damage);
  updateTeamHP(enemyTeam);

  console.log(`💥 ${attackerName} attaque ${enemyTeam} (-${damage})`);
}

function heal(username, amount = 15) {
  const player = players[username];
  if (!player) return;

  player.hp = Math.min(MAX_HP, player.hp + amount);
  console.log(`💚 ${username} se soigne (+${amount})`);
}

// ======================================================
// ❤️ BARRES DE VIE
// ======================================================
function updateTeamHP(team) {
  const percent = Math.max(0, teams[team].hp / 1000) * 100;
  teams[team].hpFill.style.width = `${percent}%`;
}

// ======================================================
// 🧪 MODE TEST LOCAL (TEMPORAIRE)
// ======================================================
window.testFight = () => {
  handleChatCommand("Alice", "!left");
  handleChatCommand("Bob", "!right");
  handleChatCommand("Charlie", "!left");
  handleChatCommand("David", "!right");

  setTimeout(() => attack("Alice", 120), 1500);
  setTimeout(() => attack("Bob", 80), 3000);
};

// ======================================================
// INIT
// ======================================================
console.log("⚔️ Inter Fight Arena prêt (V1)");
console.log("👉 Tape testFight() dans la console pour tester");
