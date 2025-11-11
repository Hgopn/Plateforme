# ============================================================
# ✅ secret.py — InterArcade Cloud (licences dynamiques + manifest Render + serve static)
# ============================================================
import eventlet, json, os
eventlet.monkey_patch()

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ============================================================
# 🔑 CHARGEMENT DES LICENCES
# ============================================================
LICENSES_FILE = "licenses.json"

def load_licenses():
    """Charge les licences depuis licenses.json s'il existe"""
    if os.path.exists(LICENSES_FILE):
        try:
            with open(LICENSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Erreur lecture {LICENSES_FILE}: {e}")
    return {}

# Licences de secours si le fichier n’est pas trouvé
DEFAULT_LICENSES = {
    "IA-TEST-BASIC": {"games": ["slot"]},
    "IA-TEST-PRO": {"games": ["slot", "duel", "race", "plinko"]},
    ("songmicon", "IA-SONGMI-PRO"): {"games": ["slot", "plinko", "race", "duel"]},
}

# ============================================================
# 🔹 MANIFEST JEUX (servi à l'application InterArcade)
# ============================================================
# ✅ On simplifie le format pour correspondre à ce qu'attend renderer.js
GAMES_MANIFEST = {
    "games": ["slot"]
    # "plinko", "duel", "race" à réactiver plus tard
}

# ============================================================
# 🌐 ROUTES API
# ============================================================
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/verify_key", methods=["POST", "GET"])
def verify_key():
    """Vérifie si la clé et le pseudo sont autorisés (compatibilité double format)"""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or request.args.get("username") or "").strip()
    key = (data.get("key") or request.args.get("key") or "").strip()

    if not username or not key:
        return jsonify({"status": "unauthorized", "reason": "missing"}), 400

    licenses = load_licenses() or DEFAULT_LICENSES

    # ✅ 1. Format (username, key)
    if (username, key) in licenses:
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": licenses[(username, key)].get("games", [])
        })

    # ✅ 2. Format simple "IA-KEY"
    if key in licenses:
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": licenses[key].get("games", [])
        })

    # ✅ 3. Format JSON : "username": {"key": "...", "games": [...]}
    if username in licenses and licenses[username].get("key") == key:
        return jsonify({
            "status": "authorized",
            "username": username,
            "games": licenses[username].get("games", [])
        })

    print(f"⛔ Licence refusée : {username} / {key}")
    return jsonify({"status": "unauthorized"}), 200


# ✅ Route manifest JSON pour l'application InterArcade
@app.route("/games/manifest.json", methods=["GET"])
def games_manifest():
    """Manifest simple utilisé par l'application InterArcade"""
    return jsonify(GAMES_MANIFEST)


# ============================================================
# 🕹️ SERVEURS DES JEUX (HTML/CSS/JS)
# ============================================================
@app.route("/games/<path:filename>")
def serve_game_file(filename):
    """Permet à Render de servir les fichiers statiques des jeux"""
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
# 🚀 Lancement du serveur
# ============================================================
if __name__ == "__main__":
    print("🚀 Serveur InterArcade Cloud prêt sur http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
