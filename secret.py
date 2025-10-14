from flask import Flask, render_template
from flask_socketio import SocketIO
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, LikeEvent
import threading

# ---------------------------
# ⚙️ CONFIGURATION DE BASE
# ---------------------------
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

TIKTOK_USERNAME = "songmicon"
client = TikTokLiveClient(unique_id=TIKTOK_USERNAME)

# ---------------------------
# 🧠 ROUTES WEB
# ---------------------------
@app.route("/")
def index():
    return render_template("page.html")

# ---------------------------
# 🎁 ÉVÉNEMENTS TIKTOK
# ---------------------------
@client.on(GiftEvent)
async def on_gift(event):
    user = event.user.unique_id
    gift = event.gift.name
    repeat = event.gift.repeat_count
    msg = f"🎁 {user} a envoyé {gift} x{repeat}"

    print(msg)
    socketio.emit("gift", {"user": user, "gift": gift, "repeat": repeat})

@client.on(LikeEvent)
async def on_like(event):
    user = event.user.unique_id
    likes = event.likeCount
    msg = f"❤️ {user} a envoyé {likes} likes"

    print(msg)
    socketio.emit("like", {"user": user, "likes": likes})

# ---------------------------
# 🚀 THREAD POUR TIKTOKLIVE
# ---------------------------
def run_tiktok():
    client.run()

# ---------------------------
# ▶️ LANCEMENT
# ---------------------------
if __name__ == '__main__':
    tiktok_thread = threading.Thread(target=run_tiktok)
    tiktok_thread.daemon = True
    tiktok_thread.start()

    print("✅ Serveur lancé sur http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
