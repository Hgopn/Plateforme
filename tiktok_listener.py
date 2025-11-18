# ============================================================
# tiktok_listener.py — version dynamique du username TikTok
# ============================================================

import asyncio
import socketio
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, LikeEvent, CommentEvent, ConnectEvent, DisconnectEvent
from TikTokLive.client.errors import UserOfflineError

BACKEND_URL = "http://51.38.238.227:5000"

# === Connexion Socket.IO vers Render ===
sio = socketio.Client()

async def connect_socket():
    """Connexion robuste à Render"""
    connected = False
    while not connected:
        try:
            print("✅ Tentative de connexion à Socket.IO Render...")
            sio.connect(
                BACKEND_URL,
                socketio_path="/socket.io/",
                transports=["websocket"],
                wait_timeout=10
            )
            print(f"🟢 Connecté à Render ({BACKEND_URL}) via Socket.IO")
            connected = True
        except Exception as e:
            print(f"❌ Échec connexion Render: {e}")
            await asyncio.sleep(5)

# === Client TikTok (ancienne version → unique_id obligatoire)
client = TikTokLiveClient(unique_id="placeholder")

# Variable modifiable dynamiquement
USERNAME = None

def set_username(username: str):
    """Fonction appelée par le backend pour définir le pseudo TikTok"""
    global USERNAME, client
    USERNAME = username
    client.unique_id = username
    print(f"🔄 Nouveau pseudo TikTok défini : @{USERNAME}")

# === ÉVÉNEMENTS ===
@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    print("✅ Connecté au flux TikTok ! En attente d’événements...")

@client.on(DisconnectEvent)
async def on_disconnect(event: DisconnectEvent):
    print("❌ Déconnecté du flux TikTok (le live semble terminé).")

@client.on(GiftEvent)
async def on_gift(event: GiftEvent):
    data = {
        "type": "gift",
        "username": event.user.unique_id,
        "from": event.user.unique_id,
        "gift": event.gift.name,
        "count": event.repeat_count,
        "streaking": event.repeat_end
    }
    print(f"🎁 Cadeau reçu: {data}")
    try:
        sio.emit("tiktok_event", data)
        print("📡 Événement envoyé à Render via Socket.IO")
    except Exception as e:
        print(f"⚠️ Erreur lors de l’émission Socket.IO: {e}")

@client.on(LikeEvent)
async def on_like(event: LikeEvent):
    data = {
        "type": "like",
        "username": event.user.unique_id,
        "from": event.user.unique_id,
        "count": getattr(event, "like_count", None)  # laisser tel quel pour l'instant
    }
    print(f"❤️ Like reçu: {data}")
    try:
        sio.emit("tiktok_event", data)
    except Exception as e:
        print(f"⚠️ Erreur envoi Like: {e}")

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    data = {
        "type": "comment",
        "username": event.user.unique_id,
        "from": event.user.unique_id,
        "comment": event.comment
    }
    print(f"💬 Commentaire reçu: {data}")
    try:
        sio.emit("tiktok_event", data)
    except Exception as e:
        print(f"⚠️ Erreur envoi Comment: {e}")

# === BOUCLE PRINCIPALE ===
async def run_client():
    await connect_socket()

    while True:
        if USERNAME is None:
            print("⏳ Aucun pseudo défini — en attente de set_username() ...")
            await asyncio.sleep(2)
            continue

        try:
            print(f"🚀 Connexion au live TikTok de @{USERNAME} ...")
            await client.connect()
            while getattr(client, "connected", True):
                await asyncio.sleep(2)
        except UserOfflineError:
            print(f"⚠️ Le live de @{USERNAME} n’est pas en ligne. Nouvelle tentative dans 10 secondes...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ Erreur inattendue : {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_client())
