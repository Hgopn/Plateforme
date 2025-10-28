from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS
import eventlet
eventlet.monkey_patch()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# === BASE DE LICENCES SIMPLIFIÉE ===
LICENSES = {
    "IA-TEST-BASIC": {"plan": "basic"},
    "IA-TEST-PRO": {"plan": "pro"},
    ("songmicon", "IA-SONGMI-PRO"): {"plan": "pro"}
}

@app.route("/health")
def health():
    """Simple route pour vérifier que le backend est vivant."""
    return jsonify({"status": "ok"})

@app.route("/verify_key", methods=["GET", "POST"])
def verify_key():
    """Vérifie une clé d’accès InterArcade (GET = test / POST = prod)."""
    if request.method == "GET":
        username = request.args.get("username", "").strip()
        key = request.args.get("key", "").strip()
    else:
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        key = (data.get("key") or "").strip()

    if not username or not key:
        return jsonify({"status": "unauthorized", "reason": "missing"}), 400

    if (username, key) in LICENSES:
        return jsonify({"status": "authorized", "plan": LICENSES[(username, key)]["plan"]})

    if key in LICENSES:
        return jsonify({"status": "authorized", "plan": LICENSES[key]["plan"]})

    return jsonify({"status": "unauthorized"}), 200

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
