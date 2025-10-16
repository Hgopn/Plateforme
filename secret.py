from flask import Flask, render_template, request
from flask_socketio import SocketIO
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, LikeEvent
import threading
import eventlet
import eventlet.wsgi

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------------------------
# 🧠 DICTIONNAIRE UTILISATEURS
# ---------------------------
clients = {}

def create_tiktok_client(username):
    """Crée un client TikTokLive relié à un pseudo donné"""
    if username in clients:
        return clients[username]

    client = TikTokLiveClient(unique_id=username)

    @client.on(GiftEvent)
    async def on_gift(event):
        data = {
            "user": event.user.unique_id,
            "gift": event.gift.name,
            "repeat": event.gift.repeat_count
        }
        print(f"🎁 {username}: {data['user']} a envoyé {data['gift']} x{data['repeat']}")
        socketio.emit("gift", data, namespace=f"/{username}")

    @client.on(LikeEvent)
    async def on_like(event):
        data = {
            "user": event.user.unique_id,
            "likes": event.likeCount
        }
        print(f"❤️ {username}: {data['user']} a envoyé {data['likes']} likes")
        socketio.emit("like", data, namespace=f"/{username}")

    t = threading.Thread(target=lambda: client.run())
    t.daemon = True
    t.start()

    clients[username] = client
    return client

# ---------------------------
# 🧩 ROUTES FLASK
# ---------------------------
@app.route("/")
def index():
    return render_template("page.html")

@app.route("/slot")
def slot():
    username = request.args.get("username", "inconnu")
    create_tiktok_client(username)
    return render_template("slot.html", username=username)

@app.route("/billes")
def billes():
    username = request.args.get("username", "inconnu")
    create_tiktok_client(username)
    return render_template("billes.html", username=username)

@app.route("/fakir")
def fakir():
    username = request.args.get("username", "inconnu")
    create_tiktok_client(username)
    return render_template("fakir.html", username=username)

# ---------------------------
# 🚀 SERVEUR RENDER
# ---------------------------
if __name__ == '__main__':
    print("✅ Serveur UnisPlay connecté à TikTok en multi-utilisateurs !")
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 5000)), app)
