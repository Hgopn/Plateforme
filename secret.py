# ============================================================
# ✅ secret.py — InterArcade Cloud (version modulaire par jeu)
# ============================================================
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# === LICENCES UTILISATEURS ===
# Chaque entrée peut être :
# 1️⃣ Par clé unique : "IA-TEST-BASIC"
# 2️⃣ Ou par tuple (username, key)
# Chaque utilisateur a sa liste de jeux autorisés (games)
LICENSES = {
    # 🔹 Exemple : licence générique "basic"
    "IA-TEST-BASIC": {"games": ["slot"]},

    # 🔹 Exemple : licence PRO globale
    "IA-TEST-PRO": {"games": ["slot", "duel", "race", "plinko"]},

    # 🔹 Exemple : licence utilisateur spécifique
    ("songmicon", "IA-SONGMI-PRO"): {"games": ["slot", "plinko", "race"]},

    # 🔹 Exemple : un utilisateur qui n’a qu’un jeu débloqué
    ("creatorX", "IA-CRX-SLOT"): {"games": ["slot"]},

    # 🔹 Exemple : un autre utilisateur avec 2 jeux
    ("creatorY", "IA-CRY-DUEL"): {"games": ["duel", "plinko"]},
}


@app.route("/health")
def health():
    """Test de santé du serveur"""
    return jsonify({"status": "ok"})


@app.route("/verify_key", methods=["POST", "GET"])
def verify_key():
    """Vérifie si la clé et le pseudo sont autorisés"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or request.args.get("username") or "").strip()
    key = (data.get("key") or request.args.get("key") or "").strip()

    if not username or not key:
        return jsonify({"status": "unauthorized", "reason": "missing"}), 400

    # 🔎 Vérifie d’abord la correspondance (username, key)
    if (username, key) in LICENSES:
        user_data = LICENSES[(username, key)]
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": user_data.get("games", []),
        })

    # 🔎 Sinon, tente une clé générique
    if key in LICENSES:
        user_data = LICENSES[key]
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": user_data.get("games", []),
        })

    # ❌ Clé inconnue
    return jsonify({"status": "unauthorized"}), 200


# === RELAIS D'ÉVÉNEMENTS TIKTOK ===
@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data)  # ✅ relai global sans broadcast


@app.route("/test_emit")
def test_emit():
    """Test manuel pour Render → InterArcade"""
    data = {"type": "gift", "username": "test_user", "gift": "Rose", "count": 1}
    print(f"🧪 Test manuel envoyé : {data}")
    socketio.emit("ia:event", data)
    return jsonify({"status": "ok", "sent": data})


if __name__ == "__main__":
    print("🚀 Serveur InterArcade Cloud prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
