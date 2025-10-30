# tiktok_listener.py

import asyncio
import socketio
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, LikeEvent, CommentEvent, ConnectEvent, DisconnectEvent
from TikTokLive.client.errors import UserOfflineError

USERNAME = "songmicon"
BACKEND_URL = "https://plateforme-v2.onrender.com"

# === Connexion Socket.IO vers Render ===
sio = socketio.Client()
try:
    sio.connect(BACKEND_URL)
    print("🟢 Connecté à Render via Socket.IO")
except Exception as e:
    print("❌ Impossible de se connecter à Render:", e)
    print(f"🔗 Tentative connexion Socket.IO vers {BACKEND_URL}")

# === Connexion TikTok ===
client = TikTokLiveClient(unique_id=USERNAME)

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
        "gift": event.gift.name,
        "count": event.repeat_count,
        "streaking": event.repeat_end
        # ❌ 'timestamp' retiré (non présent dans cette version)
    }
    print(f"🎁 Cadeau reçu: {data}")
    sio.emit("tiktok_event", data)

@client.on(LikeEvent)
async def on_like(event: LikeEvent):
    data = {
        "type": "like",
        "username": event.user.unique_id,
        "count": event.like_count
    }
    print(f"❤️ Like reçu: {data}")
    sio.emit("tiktok_event", data)

@client.on(CommentEvent)
async def on_comment(event: CommentEvent):
    data = {
        "type": "comment",
        "username": event.user.unique_id,
        "comment": event.comment
    }
    print(f"💬 Commentaire reçu: {data}")
    sio.emit("tiktok_event", data)

# === BOUCLE DE CONNEXION AUTOMATIQUE ===
async def run_client():
    while True:
        try:
            print(f"🚀 Connexion au live TikTok de @{USERNAME} ...")
            await client.connect()
            # ⏳ Remplace _connected_future par une boucle d’attente tant que connecté
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
