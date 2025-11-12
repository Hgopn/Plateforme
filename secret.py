# ============================================================
# ✅ secret.py — InterArcade Cloud (multi-utilisateurs TikTok + manifest + licences + serve static)
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
# 🔁 MULTI-LISTENERS TIKTOK (un par utilisateur)
# ============================================================
listeners = {}

def start_listener_for(username: str):
    """Lance un listener TikTok pour un pseudo donné"""
    import socketio as sio_client
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import GiftEvent, LikeEvent, CommentEvent, ConnectEvent, DisconnectEvent
    from TikTokLive.client.errors import UserOfflineError

    if username in listeners:
        print(f"⚠️ Listener déjà actif pour @{username}")
        return

    print(f"🚀 Démarrage du listener TikTok pour @{username}")
    sio = sio_client.Client()
    BACKEND_URL = "https://plateforme-v2.onrender.com"

    async def connect_socket():
        while True:
            try:
                sio.connect(BACKEND_URL, transports=["websocket"])
                print(f"🟢 Listener @{username} connecté à Render")
                break
            except Exception as e:
                print(f"❌ Reconnexion Socket.IO @{username}: {e}")
                await asyncio.sleep(5)

    client = TikTokLiveClient(unique_id=username)

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent):
        if not event.repeat_end:
            return
        data = {
            "type": "gift",
            "username": event.user.unique_id,
            "from": event.user.unique_id,
            "gift": event.gift.name,
            "count": event.repeat_count,
        }
        print(f"🎁 Cadeau @{username}: {data}")
        try:
            sio.emit("tiktok_event", data)
        except Exception as e:
            print(f"⚠️ Erreur émission @{username}: {e}")

    @client.on(LikeEvent)
    async def on_like(event: LikeEvent):
        data = {"type": "like", "username": event.user.unique_id, "count": event.like_count}
        sio.emit("tiktok_event", data)
        print(f"❤️ Like @{username}: {data}")

    async def run_listener():
        await connect_socket()
        while True:
            try:
                print(f"📡 Connexion au live TikTok @{username}")
                await client.connect()
                while getattr(client, "connected", True):
                    await asyncio.sleep(2)
            except UserOfflineError:
                print(f"⚠️ @{username} offline, reconnexion dans 10s...")
                await asyncio.sleep(10)
            except Exception as e:
                print(f"❌ Erreur TikTok @{username}: {e}")
                await asyncio.sleep(5)

    thread = threading.Thread(target=lambda: asyncio.run(run_listener()), daemon=True)
    thread.start()
    listeners[username] = thread
    print(f"✅ Listener TikTok lancé pour @{username}")

# ============================================================
# 🌐 ROUTE API : DEMARRER UN LISTENER POUR UN USER
# ============================================================
@app.route("/start_listener", methods=["POST"])
def start_listener_api():
    """Démarre un listener TikTok pour le pseudo reçu"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()

    if not username:
        return jsonify({"status": "error", "reason": "missing_username"}), 400

    threading.Thread(target=start_listener_for, args=(username,), daemon=True).start()
    return jsonify({"status": "ok", "message": f"Listener TikTok lancé pour {username}"}), 200

# ============================================================
# 🚀 Lancement du serveur + listener
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Serveur InterArcade Cloud prêt sur http://0.0.0.0:{port}")

    # 🧩 Lancement du listener TikTok en arrière-plan
    threading.Thread(target=start_tiktok_listener, daemon=True).start()

    # 🧠 Important : Render définit automatiquement PORT, pas besoin de 5000 fixe
    socketio.run(app, host="0.0.0.0", port=port)
