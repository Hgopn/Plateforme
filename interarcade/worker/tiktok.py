"""TikTok listener worker, isolated from the Flask API layer."""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Callable


class TikTokWorker:
    def __init__(self, username: str, tenant_id: str, session_id: str, emit: Callable, sign_api_key: str = ""):
        self.username = username
        self.tenant_id = tenant_id
        self.session_id = session_id
        self.emit = emit
        self.sign_api_key = sign_api_key
        self.should_run = True
        self.thread: threading.Thread | None = None

    def start(self):
        self.thread = threading.Thread(target=self._thread_main, name=f"tiktok-{self.username}", daemon=True)
        self.thread.start()

    def stop(self):
        self.should_run = False

    def _thread_main(self):
        asyncio.run(self._run())

    async def _run(self):
        # Imports remain lazy so API-only processes can start without TikTokLive.
        from TikTokLive import TikTokLiveClient
        from TikTokLive.client.errors import UserOfflineError
        from TikTokLive.events import GiftEvent, LikeEvent

        if self.sign_api_key:
            os.environ["TIKTOKLIVE_SIGN_API_KEY"] = self.sign_api_key
        client = TikTokLiveClient(unique_id=self.username)

        @client.on(GiftEvent)
        async def on_gift(event):
            if getattr(event, "repeat_end", True) is False:
                return
            self.emit(
                "gift",
                getattr(event.user, "unique_id", "unknown"),
                gift=getattr(event.gift, "name", "unknown"),
                count=getattr(event, "repeat_count", 1),
            )

        @client.on(LikeEvent)
        async def on_like(event):
            self.emit(
                "like",
                getattr(event.user, "unique_id", "unknown"),
                count=getattr(event, "total_like_count", 1),
            )

        while self.should_run:
            try:
                await client.connect()
                while getattr(client, "connected", False) and self.should_run:
                    await asyncio.sleep(1)
            except UserOfflineError:
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(5)
