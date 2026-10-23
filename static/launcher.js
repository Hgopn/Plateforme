"use strict";

const $ = (id) => document.getElementById(id);
const state = { account: null, csrf: null, session: null, gameWindow: null, registering: false,
  launching: false, ending: false };

const errors = {
  invalid_credentials: "Email ou mot de passe incorrect.",
  email_already_registered: "Cette adresse possède déjà un compte.",
  invalid_registration: "Saisissez un email valide et un mot de passe d'au moins 12 caractères.",
  too_many_attempts: "Trop de tentatives. Patientez quinze minutes avant de réessayer.",
  invalid_tiktok_username: "Saisissez un pseudo TikTok valide.",
  license_required: "Une licence Dark est nécessaire pour lancer un vrai live. Le mode Test est disponible.",
  tiktok_not_configured: "Enregistrez votre @pseudo TikTok avant de lancer le Live.",
  dark_run_inactive: "Le jeu démarre encore. Réessayez dans un instant.",
  unauthorized: "Votre session a expiré. Reconnectez-vous.",
  session_already_active: "Une session est déjà active. Terminez-la avant de changer de mode.",
  session_not_found: "Cette session est terminée. Vous pouvez relancer Dark.",
  test_session_required: "Le mode Test n'est plus actif. Relancez-le depuis la bibliothèque.",
};

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin", ...options,
      headers: {
        "Content-Type": "application/json",
        ...(state.csrf && options.method && options.method !== "GET" ? { "X-CSRF-Token": state.csrf } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error("Connexion au serveur impossible. Vérifiez votre réseau puis réessayez.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errors[data.error] || "Le service est momentanément indisponible. Réessayez dans un instant.");
  return data;
}

function setView(view) {
  ["library", "dark", "account"].forEach((name) => $(name + "-view").classList.toggle("hidden", name !== view));
  $("nav-library").classList.toggle("nav-active", view !== "account");
  $("nav-account").classList.toggle("nav-active", view === "account");
  location.hash = view === "dark" ? "dark" : view === "account" ? "compte" : "bibliotheque";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderAccount() {
  const account = state.account;
  if (!account) return;
  $("auth-screen").classList.add("hidden");
  $("app-shell").classList.remove("hidden");
  $("account-email").textContent = account.email;
  $("account-detail-email").textContent = account.email;
  const entitled = account.entitled_games.includes("dark");
  $("account-entitlements").textContent = account.entitled_games.length
    ? account.entitled_games.map((game) => game.charAt(0).toUpperCase() + game.slice(1)).join(" · ")
    : "Aucun jeu sous licence";
  $("license-status").textContent = entitled
    ? "Votre licence donne accès au Live de Dark."
    : "Mode Test disponible. Le lancement Live requiert une licence Dark.";
  const tiktok = account.platforms.find((platform) => platform.platform === "tiktok");
  $("tiktok-status").textContent = tiktok ? `@${tiktok.username} configuré` : "Non configuré";
  $("tiktok-username").value = tiktok ? `@${tiktok.username}` : "";
  setView(location.hash === "#dark" ? "dark" : location.hash === "#compte" ? "account" : "library");
  restoreSession();
}

async function restoreSession() {
  try {
    const result = await api("/api/v1/creator/sessions/active");
    if (!result.session || state.session) return;
    state.session = result.session;
    $("session-controls").classList.remove("hidden");
    $("test-controls").classList.toggle("hidden", result.session.mode !== "test");
    $("session-mode").textContent = result.session.mode === "test" ? "MODE TEST" : "LIVE TIKTOK";
    $("launch-message").textContent = "Session retrouvée. Cliquez sur le même mode pour rouvrir la fenêtre Dark.";
    await refreshSessionStatus();
  } catch (error) {
    $("launch-message").textContent = error.message;
  }
}

function showAuth() {
  state.account = null;
  state.csrf = null;
  $("app-shell").classList.add("hidden");
  $("auth-screen").classList.remove("hidden");
}

function toggleRegister() {
  state.registering = !state.registering;
  $("auth-title").textContent = state.registering ? "Créer votre compte" : "Bienvenue";
  $("auth-subtitle").textContent = state.registering
    ? "Votre bibliothèque vous attend. Aucun paiement aujourd'hui."
    : "Connectez-vous pour retrouver votre bibliothèque.";
  $("auth-submit").firstChild.textContent = state.registering ? "Créer mon compte " : "Se connecter ";
  $("auth-toggle").textContent = state.registering ? "Déjà un compte ? Se connecter" : "Créer un compte";
  $("auth-password").autocomplete = state.registering ? "new-password" : "current-password";
  $("auth-error").textContent = "";
}

async function submitAuth(event) {
  event.preventDefault();
  $("auth-error").textContent = "";
  $("auth-submit").disabled = true;
  try {
    const account = await api(`/api/v1/creator/${state.registering ? "register" : "login"}`, {
      method: "POST",
      body: JSON.stringify({
        email: $("auth-email").value,
        password: $("auth-password").value,
        remember: $("auth-remember").checked,
      }),
    });
    state.account = account;
    state.csrf = account.csrf_token;
    $("auth-password").value = "";
    renderAccount();
  } catch (error) {
    $("auth-error").textContent = error.message;
  } finally {
    $("auth-submit").disabled = false;
  }
}

async function configureTikTok(event) {
  event.preventDefault();
  $("launch-message").textContent = "Enregistrement du compte…";
  try {
    const result = await api("/api/v1/creator/platforms/tiktok", {
      method: "POST", body: JSON.stringify({ username: $("tiktok-username").value }),
    });
    state.account.platforms = [{ platform: "tiktok", username: result.username,
      source_account_id: result.username.toLowerCase() }];
    $("tiktok-status").textContent = `@${result.username} configuré`;
    $("launch-message").textContent = "Compte TikTok enregistré. InterArcade surveillera ce pseudo au lancement du Live.";
  } catch (error) {
    $("launch-message").textContent = error.message;
  }
}

async function endSession() {
  const session = state.session;
  if (!session || state.ending) return;
  state.ending = true;
  state.session = null;
  $("session-controls").classList.add("hidden");
  if (state.gameWindow && !state.gameWindow.closed) state.gameWindow.close();
  state.gameWindow = null;
  try {
    await api(`/api/v1/creator/sessions/${encodeURIComponent(session.session_id)}/end`, { method: "POST" });
  } catch (error) {
    $("launch-message").textContent = error.message;
  } finally {
    state.ending = false;
  }
}

async function refreshSessionStatus() {
  if (!state.session) return;
  try {
    const info = await api(`/api/v1/creator/sessions/${encodeURIComponent(state.session.session_id)}`);
    if (info.status !== "active") {
      state.session = null;
      $("session-controls").classList.add("hidden");
      if (state.gameWindow && !state.gameWindow.closed) state.gameWindow.close();
      state.gameWindow = null;
      $("launch-message").textContent = "La session est terminée. Vous pouvez relancer Dark.";
      return;
    }
    if (info.mode === "test") {
      $("session-state").textContent = "Test actif";
    } else {
      const source = info.sources.find((item) => item.platform === "tiktok");
      const labels = { starting: "Connexion TikTok en cours…", connecting: "Connexion TikTok en cours…",
        running: "Connexion TikTok en cours…", connected: "TikTok connecté",
        offline: "Live non détecté", reconnecting: "Reconnexion TikTok…",
        lost: "Connexion au listener perdue", error: "Connexion TikTok en erreur",
        stopping: "Arrêt en cours", stopped: "TikTok arrêté" };
      $("session-state").textContent = labels[source?.status] || "Session active";
      if (source?.status === "error") $("launch-message").textContent = "La connexion TikTok a échoué. Réessayez ou contactez l'assistance.";
      if (source?.status === "offline") $("launch-message").textContent = "Aucun live détecté pour ce compte. InterArcade continue de vérifier.";
      if (source?.status === "lost") $("launch-message").textContent = "Le listener ne répond plus. InterArcade tente de reprendre la connexion.";
    }
    if (state.gameWindow?.closed) {
      $("launch-message").textContent = "Fenêtre Dark fermée. La session se termine.";
      await endSession();
    }
  } catch (error) {
    $("session-state").textContent = "Serveur indisponible";
    $("launch-message").textContent = error.message;
  }
}

async function launchDark(mode) {
  if (state.launching || state.ending) return;
  if (state.session && state.session.mode !== mode) {
    $("launch-message").textContent = errors.session_already_active;
    return;
  }
  if (state.gameWindow && !state.gameWindow.closed) {
    state.gameWindow.focus();
    $("launch-message").textContent = "Dark est déjà ouvert.";
    return;
  }
  state.launching = true;
  const gameWindow = window.open("/broadcast/waiting", "interarcade-dark", "width=1100,height=760,resizable=yes");
  if (!gameWindow) {
    $("launch-message").textContent = "Autorisez l'ouverture de la fenêtre Dark dans votre navigateur.";
    state.launching = false;
    return;
  }
  state.gameWindow = gameWindow;
  $("launch-message").textContent = mode === "test" ? "Préparation du mode Test…" : "Préparation du Live TikTok…";
  $("test-dark").disabled = true;
  $("launch-dark").disabled = true;
  try {
    const session = state.session || await api("/api/v1/creator/sessions", {
      method: "POST", body: JSON.stringify({ game_id: "dark", mode }),
    });
    state.session = session;
    const fragment = new URLSearchParams({
      session_id: session.session_id, token: session.token,
      broadcast: "1", live_notices: $("live-overlay").checked ? "1" : "0", mode,
    });
    gameWindow.location.replace(`/games/dark/dark.html#${fragment}`);
    gameWindow.focus();
    $("session-controls").classList.remove("hidden");
    $("test-controls").classList.toggle("hidden", mode !== "test");
    $("session-mode").textContent = mode === "test" ? "MODE TEST" : "LIVE TIKTOK";
    $("session-state").textContent = "Fenêtre Dark ouverte";
    refreshSessionStatus();
    $("launch-message").textContent = mode === "test"
      ? "Mode Test actif. Utilisez les actions ci-dessous pour préparer votre stream."
      : "Live demandé. La connexion du worker peut prendre quelques instants.";
  } catch (error) {
    gameWindow.close();
    state.gameWindow = null;
    $("launch-message").textContent = error.message;
  } finally {
    state.launching = false;
    $("test-dark").disabled = false;
    $("launch-dark").disabled = false;
  }
}

async function sendTestAction() {
  if (!state.session || state.session.mode !== "test") return;
  try {
    await api(`/api/v1/creator/sessions/${encodeURIComponent(state.session.session_id)}/actions`, {
      method: "POST",
      body: JSON.stringify({ action_type: $("action-type").value, actor_username: "Spectateur test" }),
    });
    $("launch-message").textContent = "Action envoyée à Dark.";
  } catch (error) {
    $("launch-message").textContent = error.message;
  }
}

$("auth-form").addEventListener("submit", submitAuth);
$("auth-toggle").addEventListener("click", toggleRegister);
$("tiktok-form").addEventListener("submit", configureTikTok);
$("hero-dark").addEventListener("click", () => setView("dark"));
document.querySelectorAll(".open-dark").forEach((button) => button.addEventListener("click", () => setView("dark")));
$("brand-home").addEventListener("click", () => setView("library"));
$("nav-library").addEventListener("click", () => setView("library"));
$("nav-account").addEventListener("click", () => setView("account"));
$("back-library").addEventListener("click", async () => { await endSession(); setView("library"); });
$("test-dark").addEventListener("click", () => launchDark("test"));
$("launch-dark").addEventListener("click", () => launchDark("live"));
$("send-action").addEventListener("click", sendTestAction);
$("live-overlay").addEventListener("change", () => {
  if (state.gameWindow && !state.gameWindow.closed) {
    state.gameWindow.postMessage({ type: "ia:overlay", enabled: $("live-overlay").checked }, location.origin);
  }
});
$("stop-session").addEventListener("click", endSession);
$("logout-button").addEventListener("click", async () => {
  await endSession();
  try { await api("/api/v1/creator/logout", { method: "POST" }); } catch (error) { /* Expired login. */ }
  showAuth();
});

api("/api/v1/creator/me").then((account) => {
  state.account = account;
  state.csrf = account.csrf_token;
  renderAccount();
}).catch((error) => {
  showAuth();
  if (error.message !== errors.unauthorized) $("auth-error").textContent = error.message;
});
setInterval(refreshSessionStatus, 4000);
if (window.interarcadeDesktop?.onBroadcastClosed) {
  window.interarcadeDesktop.onBroadcastClosed(() => {
    if (state.session && !state.launching) endSession();
  });
}
window.addEventListener("pagehide", () => {
  if (!state.session || !state.csrf) return;
  fetch(`/api/v1/creator/sessions/${encodeURIComponent(state.session.session_id)}/end`, {
    method: "POST", credentials: "same-origin", keepalive: true,
    headers: { "X-CSRF-Token": state.csrf },
  }).catch(() => {});
});
