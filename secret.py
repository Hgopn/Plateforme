# ============================================================
# ✅ secret.py — InterArcade Cloud (licences dynamiques + manifest Render + serve static + listener TikTok intégré)
# ============================================================
import eventlet, json, os, threading, asyncio
eventlet.monkey_patch()

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

# ============================================================
# 🌍 Flask + Socket.IO
# ============================================================
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ============================================================
# 🔑 CHARGEMENT DES LICENCES
# ============================================================
LICENSES_FILE = "licenses.json"

def load_licenses():
    if os.path.exists(LICENSES_FILE):
        try:
            with open(LICENSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erreur lecture {LICENSES_FILE}: {e}")
    return {}

DEFAULT_LICENSES = {
    "IA-TEST-BASIC": {"games": ["slot"]},
    "IA-TEST-PRO": {"games": ["slot", "duel", "race", "plinko"]},
    ("songmicon", "IA-SONGMI-PRO"): {"games": ["slot", "plinko", "race", "duel"]},
}

# ============================================================
# 🔹 MANIFEST JEUX
# ============================================================
GAMES_MANIFEST = {"games": ["slot"]}

# ============================================================
# 🌐 ROUTES API
# ============================================================
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/verify_key", methods=["POST", "GET"])
def verify_key():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or request.args.get("username") or "").strip()
    key = (data.get("key") or request.args.get("key") or "").strip()

    if not username or not key:
        return jsonify({"status": "unauthorized", "reason": "missing"}), 400

    licenses = load_licenses() or DEFAULT_LICENSES

    if (username, key) in licenses:
        return jsonify({"status": "authorized", "username": username, "games": licenses[(username, key)].get("games", [])})
    if key in licenses:
        return jsonify({"status": "authorized", "username": username, "games": licenses[key].get("games", [])})
    if username in licenses and licenses[username].get("key") == key:
        return jsonify({"status": "authorized", "username": username, "games": licenses[username].get("games", [])})

    print(f"⛔ Licence refusée : {username} / {key}")
    return jsonify({"status": "unauthorized"}), 200

@app.route("/games/manifest.json")
def games_manifest():
    return jsonify(GAMES_MANIFEST)

# ============================================================
# 🕹️ SERVEURS DES JEUX
# ============================================================
@app.route("/games/<path:filename>")
def serve_game_file(filename):
    games_dir = os.path.join(os.getcwd(), "games")
    file_path = os.path.join(games_dir, filename)
    if not os.path.exists(file_path):
        print(f"❌ Fichier introuvable : {file_path}")
        return jsonify({"error": "Fichier introuvable", "path": filename}), 404
    return send_from_directory(games_dir, filename)

# ============================================================
# 🎥 RELAIS D'ÉVÉNEMENTS TIKTOK
# ============================================================
@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data)

@app.route("/test_emit")
def test_emit():
    data = {"type": "gift", "username": "test_user", "gift": "Rose", "count": 1}
    print(f"🧪 Test manuel envoyé : {data}")
    socketio.emit("ia:event", data)
    return jsonify({"status": "ok", "sent": data})

# ============================================================
# 🔁 TIKTOK LISTENER INTÉGRÉ
# ============================================================
def start_tiktok_listener():
    import socketio as sio_client
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import GiftEvent, LikeEvent, CommentEvent, ConnectEvent, DisconnectEvent
    from TikTokLive.client.errors import UserOfflineError

    USERNAME = "songmicon"
    BACKEND_URL = "https://plateforme-v2.onrender.com"

    sio = sio_client.Client()

    async def connect_socket():
        while True:
            try:
                sio.connect(BACKEND_URL, transports=["websocket"])
                print(f"🟢 Listener connecté à Render ({BACKEND_URL})")
                break
            except Exception as e:
                print(f"❌ Tentative reconnexion Socket.IO: {e}")
                await asyncio.sleep(5)

    client = TikTokLiveClient(unique_id=USERNAME)

    # ✅ Fix : on n'envoie le spin qu'à la fin du streak
    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent):
        if not event.repeat_end:
            return  # Ignorer les signaux intermédiaires

        data = {
            "type": "gift",
            "username": event.user.unique_id,
            "from": event.user.unique_id,
            "gift": event.gift.name,
            "count": event.repeat_count,
        }
        print(f"🎁 Listener: Cadeau reçu (streak terminé) {data}")
        try:
            sio.emit("tiktok_event", data)
        except Exception as e:
            print(f"⚠️ Erreur d’émission: {e}")

    @client.on(LikeEvent)
    async def on_like(event: LikeEvent):
        data = {"type": "like", "username": event.user.unique_id, "count": event.like_count}
        sio.emit("tiktok_event", data)
        print(f"❤️ Like reçu: {data}")

    async def run_listener():
        await connect_socket()
        while True:
            try:
                print(f"🚀 Connexion au live TikTok @{USERNAME}")
                await client.connect()
                while getattr(client, "connected", True):
                    await asyncio.sleep(2)
            except UserOfflineError:
                print("⚠️ Le live TikTok n’est pas en ligne, nouvelle tentative...")
                await asyncio.sleep(10)
            except Exception as e:
                print(f"❌ Erreur TikTokListener: {e}")
                await asyncio.sleep(5)

    asyncio.run(run_listener())

# ============================================================
# 🚀 Lancement du serveur + listener
# ============================================================
if __name__ == "__main__":
    print("🚀 Serveur InterArcade Cloud prêt sur http://0.0.0.0:5000")
    threading.Thread(target=start_tiktok_listener, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)
