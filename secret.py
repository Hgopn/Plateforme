# ============================================================
# ✅ secret.py — InterArcade Cloud (Version STABLE)
# Multi-utilisateurs, rooms, manifest, start/stop listeners
# Compatible TikTokLive v6.6.1 + EulerStream (via EULER_API_KEY)
# ============================================================

import eventlet
eventlet.monkey_patch()

import os, json, threading, asyncio
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, join_room, leave_room
from flask_cors import CORS

# ============================================================
# 🌍 Flask + Socket.IO
# ============================================================
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ============================================================
# 🔑 EULERSTREAM API KEY
# ============================================================
EULER_API_KEY = os.getenv("EULER_API_KEY")
if not EULER_API_KEY:
    print("⚠️ Aucune EULER_API_KEY détectée → mode anonyme (risque RATE_LIMIT)")

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
    ("songmicon", "IA-SONGMI-PRO"): {"games": ["slot", "plinko", "race", "duel","marble"]},
}

# ============================================================
# 🔹 MANIFEST JEUX
# ============================================================
GAMES_MANIFEST = {"games": ["slot","dark","marble"]}

@app.route("/games/manifest.json")
def games_manifest():
    return jsonify(GAMES_MANIFEST)

# ============================================================
# 🌐 ROUTES API : health + vérification de licence
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
        return jsonify({"status": "authorized",
                        "username": username,
                        "games": licenses[(username, key)].get("games", [])})

    if key in licenses:
        return jsonify({"status": "authorized",
                        "username": username,
                        "games": licenses[key].get("games", [])})

    if username in licenses and licenses[username].get("key") == key:
        return jsonify({"status": "authorized",
                        "username": username,
                        "games": licenses[username].get("games", [])})

    print(f"⛔ Licence refusée : {username}/{key}")
    return jsonify({"status": "unauthorized"}), 200

# ============================================================
# 🕹️ SERVEURS DES JEUX (STATIC /games)
# ============================================================
@app.route("/games/<path:filename>")
def serve_game_file(filename):
    base = os.path.join(os.getcwd(), "games")
    full = os.path.join(base, filename)
    if not os.path.exists(full):
        print(f"❌ Fichier introuvable : {filename}")
        return jsonify({"error": "not_found", "path": filename}), 404
    return send_from_directory(base, filename)

# ============================================================
# 🔐 SOCKET.IO : rooms par utilisateur
# ============================================================
@socketio.on("connect")
def on_connect():
    username = (request.args.get("username") or "").strip()
    if username:
        join_room(username)
        print(f"🔌 Client {request.sid} rejoint @{username}")
    else:
        print(f"🔌 Client {request.sid} connecté sans username")

@socketio.on("disconnect")
def on_disconnect():
    username = (request.args.get("username") or "").strip()
    if username:
        leave_room(username)
        print(f"🔌 Client {request.sid} quitte @{username}")
    else:
        print(f"🔌 Client {request.sid} déconnecté")

# ============================================================
# 🎥 RELAIS EVENTS TIKTOK → rooms
# ============================================================
@socketio.on("tiktok_event")
def relay_event(data):
    target = (data or {}).get("target")
    if target:
        print(f"📡 Relay vers @{target} : {data}")
        socketio.emit("ia:event", data, to=target)
    else:
        print(f"📡 Relay global : {data}")
        socketio.emit("ia:event", data)

# ============================================================
# 🔁 MULTI-LISTENER TIKTOK
# ============================================================
listeners = {}

def start_listener_for(username: str):
    """Start a TikTok listener for a username"""
    import socketio as sio_client
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import GiftEvent, LikeEvent
    from TikTokLive.client.errors import UserOfflineError

    if username in listeners and listeners[username].get("should_run"):
        print(f"⚠️ Listener déjà actif pour @{username}")
        return

    print(f"🚀 Start listener @{username}")
    listeners[username] = {"thread": None, "should_run": True}

    sio = sio_client.Client()
    BACKEND_URL = "http://51.38.238.227:5000"

    async def maintain_socket():
        while listeners.get(username, {}).get("should_run", False):
            try:
                sio.connect(BACKEND_URL, transports=["websocket"])
                print(f"🟢 Socket connecté @{username}")
                break
            except Exception as e:
                print(f"❌ SockErr @{username}: {e}")
                await asyncio.sleep(5)

    # ============================================================
    # ⚠️ FIX : TikTokLive 6.6.1 → plus de sign_api_key
    # Injection correcte via variable d'environnement
    # ============================================================
    if EULER_API_KEY:
        os.environ["TIKTOKLIVE_SIGN_API_KEY"] = EULER_API_KEY
        print(f"🔐 EulerStream activé @{username}")
    else:
        print(f"⚠️ @{username} en mode anonyme (risque RATE_LIMIT)")

    client = TikTokLiveClient(unique_id=username)

    # --- Gift ---
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
            "target": username
        }
        print(f"🎁 Gift @{username}: {data}")
        try:
            sio.emit("tiktok_event", data)
        except Exception as e:
            print(f"⚠️ Emit gift err @{username}: {e}")

    # --- Like ---
    @client.on(LikeEvent)
    async def on_like(event: LikeEvent):
        count = getattr(event, "total_like_count", 1)
        data = {
            "type": "like",
            "username": event.user.unique_id,
            "count": count,
            "target": username
        }
        print(f"❤️ Like @{username}: {data}")
        try:
            sio.emit("tiktok_event", data)
        except Exception as e:
            print(f"⚠️ Emit like err @{username}: {e}")

    # --- Main loop ---
    async def run():
        await maintain_socket()
        while listeners.get(username, {}).get("should_run", False):
            try:
                print(f"📡 Connexion Live @{username}")
                await client.connect()

                while getattr(client, "connected", True) and listeners.get(username, {}).get("should_run", False):
                    await asyncio.sleep(1)

                if not listeners.get(username, {}).get("should_run", False):
                    break

            except UserOfflineError:
                if not listeners.get(username, {}).get("should_run", False):
                    break
                print(f"⚠️ @{username} offline, retry 10s")
                await asyncio.sleep(10)

            except Exception as e:
                if not listeners.get(username, {}).get("should_run", False):
                    break
                print(f"❌ ListenerErr @{username}: {e}")
                await asyncio.sleep(5)

        print(f"🧹 Listener terminé @{username}")

    # ✅ CORRECTION ICI : plus de asyncio.run() dans un thread
    def _run_async(coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
        loop.close()

    thread = threading.Thread(target=_run_async, args=(run(),), daemon=True)
    thread.start()
    listeners[username]["thread"] = thread
    print(f"✅ Listener lancé @{username}")

# ============================================================
# 🌐 API START/STOP
# ============================================================
@app.route("/start_listener", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"status": "error", "reason": "missing_username"}), 400

    threading.Thread(target=start_listener_for, args=(username,), daemon=True).start()
    return jsonify({"status": "ok", "message": f"listener_started_for_{username}"})

@app.route("/stop_listener", methods=["POST"])
def api_stop():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()

    if username not in listeners:
        return jsonify({"status": "not_found", "username": username}), 404

    listeners[username]["should_run"] = False
    print(f"🧹 Stop requested @{username}")
    return jsonify({"status": "stopping", "username": username})

# ============================================================
# 🚀 Lancement serveur
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 InterArcade Cloud → port {port}")
    socketio.run(app, host="0.0.0.0", port=port)
