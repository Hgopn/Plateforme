# ✅ secret.py — Serveur Flask / Socket.IO / Licences InterArcade
import eventlet
eventlet.monkey_patch()  # ⚠️ doit être tout en haut

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

# --- Config Flask ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# === BASE DES LICENCES ===
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

# === RÉCEPTION D'ÉVÉNEMENTS TIKTOK ===
@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data, broadcast=True)  # 🔥 diffuse à tous les clients connectés

# === LANCEMENT SERVEUR ===
if __name__ == "__main__":
    print("🚀 Serveur InterArcade prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
