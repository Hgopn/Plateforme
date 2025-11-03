# ✅ secret.py — Serveur Flask / Socket.IO / Licences InterArcade
import eventlet
eventlet.monkey_patch()  # ⚠️ doit être tout en haut avant tout import

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

# === ROUTES DE TEST ET DE LICENCE ===
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


# === SOCKET.IO ÉVÉNEMENTS ===
@socketio.on("connect")
def on_connect():
    print("✅ Nouveau client connecté au Socket.IO")

@socketio.on("disconnect")
def on_disconnect():
    print("❌ Client déconnecté du Socket.IO")

@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data)  # ✅ envoi global à tous les clients connectés
    return {"status": "ok"}


# === 🔬 ROUTE DE TEST MANUEL (Render → InterArcade) ===
@app.route("/test_emit")
def test_emit():
    """Permet de tester l'envoi manuel d'un événement vers InterArcade"""
    data = {
        "type": "gift",
        "username": "test_user",
        "gift": "Rose",
        "count": 1
    }
    print(f"🧪 Test manuel envoyé : {data}")
    socketio.emit("ia:event", data)
    return jsonify({"status": "ok", "sent": data})


# === LANCEMENT SERVEUR ===
if __name__ == "__main__":
    print("🚀 Serveur InterArcade prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
