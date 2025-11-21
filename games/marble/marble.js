console.log("MARBLE.JS chargé 🎱");

// ===============================
// 🔗 CONNEXION AU BACKEND OVH
// ===============================
const urlParams = new URLSearchParams(window.location.search);
const USERNAME = urlParams.get("username") || "songmicon";

const SOCKET_URL = "http://51.38.238.227:5000";

let socket = io(SOCKET_URL, {
  transports: ["websocket"],
  query: { username: USERNAME }
});

console.log("Connexion à OVH pour MARBLE…");

socket.on("connect", () => console.log("🟢 Connecté MARBLE"));
socket.on("disconnect", () => console.log("🔴 Déconnecté MARBLE"));

// ===============================
// 📊 COMPTEURS
// ===============================
let likeCounter = 0;
let giftCounter = 0;

const likeEl = document.getElementById("likeCount");
const giftEl = document.getElementById("giftCount");

// ===============================
// 🔔 LISTEN EVENTS TIKTOK
// ===============================
socket.on("ia:event", (data) => {
  if (!data) return;

  if (data.type === "like") {
    likeCounter += 1;
    likeEl.textContent = likeCounter;
  }

  if (data.type === "gift") {
    giftCounter += data.count || 1;
    giftEl.textContent = giftCounter;
  }
});

// ===============================
// 🏁 COURSE DE BILLES
// ===============================
const marbleLikes = document.getElementById("marbleLikes");
const marbleGifts = document.getElementById("marbleGifts");
const finishLine = document.getElementById("finishLine");
const winnerEl = document.getElementById("winner");

let interval = null;
let raceRunning = false;

document.getElementById("startBtn").addEventListener("click", startRace);

function startRace() {
  if (raceRunning) return;
  raceRunning = true;
  winnerEl.textContent = "";
  
  let posLikes = 0;
  let posGifts = 0;
  const finish = 460;

  interval = setInterval(() => {
    // Aléatoire mais équilibré
    posLikes += Math.random() * 7 + 3;
    posGifts += Math.random() * 7 + 3;

    marbleLikes.style.top = posLikes + "px";
    marbleGifts.style.top = posGifts + "px";

    if (posLikes >= finish || posGifts >= finish) {
      clearInterval(interval);
      raceRunning = false;

      if (posLikes > posGifts) {
        winnerEl.textContent = "🏆 GAGNANT : ❤️ Likes";
      } else {
        winnerEl.textContent = "🏆 GAGNANT : 🎁 Cadeaux";
      }
    }
  }, 60);
}
