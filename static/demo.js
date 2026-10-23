const games = [
  { id: "slot", name: "Slot", icon: "🎰", color: "#e66c3c", description: "La machine à cadeaux du live.", detail: "Chaque cadeau fait tourner la machine et construit le classement." },
  { id: "dark", name: "Dark", icon: "🌑", color: "#78a878", description: "Une exploration souterraine dans l’obscurité.", detail: "Traversez trois labyrinthes et trouvez chaque escalier avec pour seul repère un cercle de lumière." },
  { id: "marble", name: "Marble", icon: "🔮", color: "#d49554", description: "La course des likes et des cadeaux.", detail: "Likes et cadeaux font avancer les billes vers la victoire." },
  { id: "fight", name: "Fight", icon: "⚔️", color: "#c85c42", description: "L’arène interactive Inter Fight.", detail: "Une arène où la communauté rejoint les équipes et déclenche les actions." },
];
let currentGame = null;
let session = null;
let tiktokConfigured = false;
const $ = (id) => document.getElementById(id);

function setView(viewName) {
  document.querySelectorAll(".view").forEach((view) => view.classList.add("hidden"));
  const view = $(`view-${viewName}`);
  if (view) view.classList.remove("hidden");
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === viewName));
  const labels = { home: "Accueil", library: "Mes jeux", account: "Compte & licence", sessions: "Sessions" };
  $("current-location").textContent = labels[viewName] || "Jeu";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function bindNavigation() {
  document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", (event) => {
    event.preventDefault();
    setView(item.dataset.view);
  }));
}

function card(game) {
  return `<article class="game-card game-card-${game.id}"><div class="game-icon">${game.icon}</div><h3>${game.name}</h3><p>${game.description}</p><button class="open-button" data-game="${game.id}">Voir la fiche →</button></article>`;
}

function renderCards() {
  $("home-cards").innerHTML = games.slice(0, 3).map(card).join("");
  $("library-cards").innerHTML = games.map(card).join("");
  document.querySelectorAll("[data-game]").forEach((button) => button.addEventListener("click", () => showGame(button.dataset.game)));
}

function updateRuntimeState(id, healthy) {
  const element = $(id);
  element.classList.toggle("ok", healthy);
  element.classList.toggle("bad", !healthy);
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/v1/demo/status");
    const data = await response.json();
    updateRuntimeState("status-api", data.health?.api);
    updateRuntimeState("status-worker", data.health?.worker);
    updateRuntimeState("status-database", data.health?.database);
    $("status-version").textContent = `Version ${data.version || "—"}`;
  } catch (error) {
    ["status-api", "status-worker", "status-database"].forEach((id) => updateRuntimeState(id, false));
    $("status-version").textContent = "Runtime inaccessible";
  }
}

async function createDemoSession() {
  const response = await fetch("/api/v1/demo/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ game_id: currentGame.id }) });
  if (!response.ok) throw new Error("session unavailable");
  return response.json();
}

async function endCurrentSession() {
  const ending = session;
  session = null;
  $("game-frame").src = "about:blank";
  if (!ending) return;
  try {
    await fetch(`/api/v1/sessions/${encodeURIComponent(ending.session_id)}/end`, {
      method: "POST",
      headers: { Authorization: `Bearer ${ending.token}` },
    });
  } catch (error) {
    console.warn("Impossible de fermer proprement la session locale", error);
  }
}

async function launchGame(mode) {
  if (!currentGame) return;
  if (currentGame.id === "dark" && mode === "tiktok") return;
  await endCurrentSession();
  $("game-session").textContent = mode === "test" ? "Préparation du test…" : "Connexion TikTok…";
  try {
    session = await createDemoSession();
    const query = new URLSearchParams({ username: session.username || "demo-creator", token: session.token, session_id: session.session_id });
    if (currentGame.id === "marble") query.set("marble_config", JSON.stringify(marbleConfig()));
    $("game-frame").src = `/games/${currentGame.id}/${currentGame.id}.html?${query}`;
    $("game-session").textContent = mode === "test" ? "Session de test active" : "Prêt pour TikTok";
    $("event-result").textContent = mode === "test" ? "Le jeu est prêt à recevoir des simulations." : (tiktokConfigured ? "Compte configuré — aucune connexion live réelle n’a été lancée." : "Configurez un compte TikTok de test avant une connexion réelle.");
    $("dark-action-result").textContent = "";
    $("dark-live-session-id").textContent = currentGame.id === "dark" ? session.session_id : "—";
  } catch (error) {
    $("game-session").textContent = "Session indisponible";
    $("event-result").textContent = "Impossible de créer la session locale.";
  }
}

async function showGame(gameId) {
  await endCurrentSession();
  currentGame = games.find((game) => game.id === gameId);
  $("game-title").textContent = currentGame.name;
  $("game-description").textContent = currentGame.detail;
  $("game-frame").src = "about:blank";
  $("game-session").textContent = "Pas de session";
  $("event-result").textContent = "";
  $("dark-live-session-id").textContent = "—";
  tiktokConfigured = false;
  $("tiktok-account-status").textContent = "Non configuré";
  $("marble-settings").classList.toggle("visible", currentGame.id === "marble");
  $("dark-actions").classList.toggle("visible", currentGame.id === "dark");
  $("launch-tiktok").disabled = currentGame.id === "dark";
  $("launch-tiktok").textContent = currentGame.id === "dark"
    ? "Live TikTok après validation"
    : "Lancer avec TikTok →";
  setView("game");
}

function configureTikTok() {
  const username = $("tiktok-username").value.trim();
  if (!username) return;
  tiktokConfigured = true;
  $("tiktok-account-status").textContent = `Compte @${username} configuré`;
  $("event-result").textContent = "Compte mémorisé pour la démo — connexion live réelle non tentée.";
}

function marbleConfig() {
  return {
    gift_target: Number($("marble-gift-target").value) || 50,
    like_target: Number($("marble-like-target").value) || 500,
    like_unit: Number($("marble-like-unit").value) || 15,
  };
}

async function sendEvent() {
  if (!session || !currentGame) {
    $("event-result").textContent = "Commencez par tester ou lancer le jeu.";
    return;
  }
  const type = $("event-type").value;
  const payload = type === "gift" ? { gift: $("event-gift").value, count: Number($("event-count").value) || 1 } : { count: Number($("event-count").value) || 1 };
  const response = await fetch("/api/v1/demo/events", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: session.session_id, type, actor: $("event-actor").value || "demo-viewer", payload }) });
  $("event-result").textContent = response.ok ? `✓ ${type} envoyé à ${currentGame.name}` : "Événement refusé";
}

async function sendDarkAction() {
  if (!session || currentGame?.id !== "dark") {
    $("dark-action-result").textContent = "Démarrez d’abord Dark avec « Tester le jeu ».";
    return;
  }
  const actionType = $("dark-action-type").value;
  const response = await fetch("/api/v1/demo/dark/actions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.token}` },
    body: JSON.stringify({
      session_id: session.session_id,
      action_type: actionType,
      source_platform: $("dark-action-platform").value,
      actor_username: $("dark-action-actor").value.trim() || "demo-viewer",
    }),
  });
  $("dark-action-result").textContent = response.ok
    ? `✓ ${actionType} envoyé à Dark`
    : "Action refusée";
}

$("refresh-status").addEventListener("click", refreshStatus);
$("back-button").addEventListener("click", async () => { await endCurrentSession(); setView("library"); });
$("test-game").addEventListener("click", () => launchGame("test"));
$("launch-tiktok").addEventListener("click", () => launchGame("tiktok"));
$("configure-tiktok").addEventListener("click", configureTikTok);
$("send-event").addEventListener("click", sendEvent);
$("send-dark-action").addEventListener("click", sendDarkAction);
$("event-type").addEventListener("change", () => { $("gift-field").style.display = $("event-type").value === "gift" ? "grid" : "none"; });
renderCards(); bindNavigation(); refreshStatus(); setInterval(refreshStatus, 10000);
const requestedGame = window.location.hash.slice(1);
if (games.some((game) => game.id === requestedGame)) showGame(requestedGame);
