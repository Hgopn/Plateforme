# ============================================================
# ✅ secret.py — InterArcade Cloud (version modulaire par jeu + gestion externe)
# ============================================================
import eventlet, json, os
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ============================================================
# 🔑 CHARGEMENT DES LICENCES DEPUIS FICHIER EXTERNE
# ============================================================

LICENSES_FILE = "licenses.json"

def load_licenses():
    """Charge les licences depuis licenses.json s'il existe, sinon fallback sur LICENSES interne."""
    if os.path.exists(LICENSES_FILE):
        try:
            with open(LICENSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erreur lecture {LICENSES_FILE}: {e}")
    return {}

# === LICENCES PAR DÉFAUT (fallback)
DEFAULT_LICENSES = {
    "IA-TEST-BASIC": {"games": ["slot"]},
    "IA-TEST-PRO": {"games": ["slot", "duel", "race", "plinko"]},
    ("songmicon", "IA-SONGMI-PRO"): {"games": ["slot", "plinko", "race", "duel"]},
    ("creatorX", "IA-CRX-SLOT"): {"games": ["slot"]},
    ("creatorY", "IA-CRY-DUEL"): {"games": ["duel", "plinko"]},
}

# ============================================================
# 🌐 ROUTES HTTP
# ============================================================

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

    licenses = load_licenses() or DEFAULT_LICENSES

    # 🔎 Vérifie correspondance exacte
    if (username, key) in licenses:
        user_data = licenses[(username, key)]
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": user_data.get("games", []),
        })

    # 🔎 Ou bien clé générique
    if key in licenses:
        user_data = licenses[key]
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": user_data.get("games", []),
        })

    print(f"⛔ Licence refusée : {username} / {key}")
    return jsonify({"status": "unauthorized"}), 200

# ============================================================
# 🎥 RELAIS D'ÉVÉNEMENTS TIKTOK
# ============================================================
@socketio.on("tiktok_event")
def handle_tiktok_event(data):
    print(f"📡 Événement TikTokLive reçu : {data}")
    socketio.emit("ia:event", data)  # ✅ Relai global

@app.route("/test_emit")
def test_emit():
    """Test manuel pour Render → InterArcade"""
    data = {"type": "gift", "username": "test_user", "gift": "Rose", "count": 1}
    print(f"🧪 Test manuel envoyé : {data}")
    socketio.emit("ia:event", data)
    return jsonify({"status": "ok", "sent": data})

# ============================================================
# 🚀 Lancement du serveur
# ============================================================
if __name__ == "__main__":
    print("🚀 Serveur InterArcade Cloud prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
