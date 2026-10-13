"""TikTok listener worker, isolated from the Flask API layer."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable

from .live_source import LiveSourceBinding


def _actor(event) -> str:
    return str(getattr(getattr(event, "user", None), "unique_id", "unknown") or "unknown")


def _actor_platform_id(event) -> str:
    user = getattr(event, "user", None)
    for name in ("user_id", "id", "unique_id"):
        value = getattr(user, name, None)
        if value is not None and str(value).strip():
            return str(value)
    return "unknown"


def normalize_gift(event) -> tuple[str, dict]:
    return _actor(event), {
        "gift": str(getattr(getattr(event, "gift", None), "name", "unknown") or "unknown"),
        "count": max(1, int(getattr(event, "repeat_count", 1) or 1)),
    }


def normalize_like(event) -> tuple[str, dict]:
    return _actor(event), {"count": max(1, int(getattr(event, "count", 1) or 1))}


class TikTokWorker:
    def __init__(
        self, binding: LiveSourceBinding, emit: Callable,
        sign_api_key: str = "", on_stopped: Callable | None = None,
    ):
        self.binding = binding
        self.username = binding.username
        self.tenant_id = binding.tenant_id
        self.session_id = binding.session_id
        self.emit = emit
        self.sign_api_key = sign_api_key
        self.should_run = True
        self.thread: threading.Thread | None = None
        self.on_stopped = on_stopped
        self.client = None
        self.logger = logging.getLogger("interarcade.worker.tiktok")

    def start(self):
        self.thread = threading.Thread(target=self._thread_main, name=f"tiktok-{self.username}", daemon=True)
        self.thread.start()

    def stop(self):
        self.should_run = False

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        finally:
            if self.on_stopped:
                self.on_stopped()

    async def _run(self):
        # Imports remain lazy so API-only processes can start without TikTokLive.
        from TikTokLive import TikTokLiveClient
        from TikTokLive.client.errors import UserOfflineError
        from TikTokLive.events import CommentEvent, FollowEvent, GiftEvent, LikeEvent, ShareEvent

        if self.sign_api_key:
            os.environ["TIKTOKLIVE_SIGN_API_KEY"] = self.sign_api_key
        client = TikTokLiveClient(unique_id=self.username)
        self.client = client

        @client.on(GiftEvent)
        async def on_gift(event):
            if getattr(event, "repeat_end", True) is False:
                return
            actor, payload = normalize_gift(event)
            await asyncio.to_thread(self.emit, "gift", actor, actor_platform_id=_actor_platform_id(event), **payload)

        @client.on(LikeEvent)
        async def on_like(event):
            actor, payload = normalize_like(event)
            await asyncio.to_thread(self.emit, "like", actor, actor_platform_id=_actor_platform_id(event), **payload)

        @client.on(CommentEvent)
        async def on_comment(event):
            await asyncio.to_thread(
                self.emit,
                "comment",
                _actor(event),
                actor_platform_id=_actor_platform_id(event),
                comment=str(getattr(event, "comment", "") or ""),
            )

        @client.on(ShareEvent)
        async def on_share(event):
            await asyncio.to_thread(
                self.emit, "share", _actor(event), actor_platform_id=_actor_platform_id(event), count=1
            )

        @client.on(FollowEvent)
        async def on_follow(event):
            await asyncio.to_thread(self.emit, "follow", _actor(event), actor_platform_id=_actor_platform_id(event))

        while self.should_run:
            try:
                await client.connect()
                while getattr(client, "connected", False) and self.should_run:
                    await asyncio.sleep(1)
            except UserOfflineError:
                self.logger.warning("TikTok user is offline", extra={"component": "tiktok"})
                await asyncio.sleep(10)
            except Exception:
                self.logger.exception("TikTok connection failed", extra={"component": "tiktok"})
                await asyncio.sleep(5)
        if getattr(client, "connected", False):
            try:
                await client.disconnect()
            except Exception:
                self.logger.exception("TikTok client disconnect failed", extra={"component": "tiktok"})
