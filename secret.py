# =========================================================
# 🔐 InterArcade Backend — Serveur Flask + Socket.IO
# Gestion des licences et communication temps réel
# =========================================================

import eventlet
eventlet.monkey_patch()  # ⚠️ doit être appelé avant tout autre import

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

# --- Initialisation ---
app = Flask(__name__)
CORS(app)  # autorise les requêtes depuis l'app Electron
socketio = SocketIO(app, cors_allowed_origins="*")

# === MOCK BASE DE LICENCES ===
# Tu pourras remplacer par une vraie base (SQLite, JSON, etc.)
# Deux modèles possibles :
# 1️⃣ clé seule → plan
# 2️⃣ (pseudo, clé) → plan (clé liée à un pseudo)
LICENSES = {
    # modèle 1 (clé seule)
    "IA-TEST-BASIC": {"plan": "basic"},
    "IA-TEST-PRO": {"plan": "pro"},

    # modèle 2 (clé liée à un pseudo)
    ("songmicon", "IA-SONGMI-PRO"): {"plan": "pro"}
}

# === ROUTES API ===
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/verify_key", methods=["GET", "POST"])
if request.method == "GET":
    username = request.args.get("username", "").strip()
    key = request.args.get("key", "").strip()
else:
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    key = (data.get("key") or "").strip()
def verify_key():
    """
    Reçoit: { "username": "...", "key": "IA-XXXX-...." }
    Renvoie:
      { "status": "authorized", "plan": "pro" } ou { "status": "unauthorized" }
    """
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    key = (data.get("key") or "").strip()

    if not username or not key:
        return jsonify({"status": "unauthorized", "reason": "missing"}), 400

    # Vérifie d'abord (pseudo, clé)
    if (username, key) in LICENSES:
        plan = LICENSES[(username, key)]["plan"]
        print(f"✅ Licence valide pour {username} ({plan})")
        return jsonify({"status": "authorized", "plan": plan})

    # Sinon vérifie clé seule
    if key in LICENSES:
        plan = LICENSES[key]["plan"]
        print(f"✅ Licence valide ({plan}) pour clé {key}")
        return jsonify({"status": "authorized", "plan": plan})

    print(f"❌ Licence invalide : {username} / {key}")
    return jsonify({"status": "unauthorized"}), 200


# === SOCKET.IO (canal /events) ===
@socketio.on("connect", namespace="/events")
def handle_connect():
    print("🟢 Client connecté à /events")

@socketio.on("disconnect", namespace="/events")
def handle_disconnect():
    print("🔴 Client déconnecté de /events")


# === Lancement du serveur ===
if __name__ == "__main__":
    print("🚀 Serveur InterArcade prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
