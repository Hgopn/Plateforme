# ✅ secret.py — Serveur Flask / Socket.IO / Licences InterArcade (stabilisé Render)
import eventlet
eventlet.monkey_patch()  # ⚠️ doit être tout en haut

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 🔧 IMPORTANT : async_mode="eventlet" + log désactivés
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)

# === LICENCES ===
LICENSES = {
    "IA-TEST-BASIC": {"plan": "basic"},
    "IA-TEST-PRO": {"plan": "pro"},
    ("songmicon", "IA-SONGMI-PRO"): {"plan": "pro"},
}

# === ROUTES ===
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

    if (username, key) in LICENSES:
        return jsonify({"status": "authorized", "plan": LICENSES[(username, key)]["plan"]})
    if key in LICENSES:
        return jsonify({"status": "authorized", "plan": LICENSES[key]["plan"]})
    return jsonify({"status": "unauthorized"}), 200


# === ÉVÉNEMENTS SOCKET.IO (TikTok → InterArcade) ===
@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data)  # ✅ diffuse à tous les clients connectés


# === ROUTE DE TEST / DEBUG ===
@app.route("/test_emit", methods=["GET"])
def test_emit():
    data = {
        "type": "gift",
        "username": "test_user",
        "gift": "Rose",
        "count": 1
    }
    print(f"🧪 Test manuel envoyé : {data}")
    socketio.emit("ia:event", data)
    return jsonify({"status": "ok", "sent": data})


# === LANCEMENT ===
if __name__ == "__main__":
    print("🚀 Serveur InterArcade prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
