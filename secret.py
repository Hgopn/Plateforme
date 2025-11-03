# ✅ secret.py — Version publique Render stable (InterArcade Cloud)
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# === LICENCES ===
LICENSES = {
    "IA-TEST-BASIC": {"plan": "basic"},
    "IA-TEST-PRO": {"plan": "pro"},
    ("songmicon", "IA-SONGMI-PRO"): {"plan": "pro"},
}

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

# === RÉCEPTION D'ÉVÉNEMENTS TIKTOK ===
@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data)  # ✅ relai global sans broadcast

@app.route("/test_emit")
def test_emit():
    """Test manuel pour vérifier Render → InterArcade"""
    data = {"type": "gift", "username": "test_user", "gift": "Rose", "count": 1}
    print(f"🧪 Test manuel envoyé : {data}")
    socketio.emit("ia:event", data)
    return jsonify({"status": "ok", "sent": data})

if __name__ == "__main__":
    print("🚀 Serveur InterArcade Cloud prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
