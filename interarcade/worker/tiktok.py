"""TikTok listener worker, isolated from the Flask API layer."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from time import monotonic

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


def _native_event_id(event) -> str | None:
    common = getattr(event, "base_message", None)
    for value in (
        getattr(common, "message_id", None),
        getattr(event, "m_log_id", None),
    ):
        if value is not None and str(value).strip() and str(value) != "0":
            return str(value)
    return None


def _native_timestamp(event) -> str | None:
    common = getattr(event, "base_message", None)
    value = getattr(common, "create_time", None)
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        seconds = value / 1000 if value >= 1_000_000_000_000 else value
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _gift_streaking(event) -> bool:
    gift = getattr(event, "gift", None)
    if gift is None:
        return False
    value = getattr(event, "streaking", None)
    if value is not None:
        return bool(value)
    streakable = getattr(gift, "streakable", getattr(gift, "type", None) == 1)
    return bool(streakable) and not bool(getattr(event, "repeat_end", True))


def _event_metadata(event) -> dict:
    metadata = {"actor_platform_id": _actor_platform_id(event)}
    event_id = _native_event_id(event)
    timestamp = _native_timestamp(event)
    if event_id:
        metadata["event_id"] = event_id
    if timestamp:
        metadata["timestamp"] = timestamp
    return metadata


def normalize_gift(event) -> tuple[str, dict]:
    gift = getattr(event, "gift", None)
    name = str(getattr(gift, "name", "unknown") or "unknown")
    count = max(1, int(getattr(event, "repeat_count", 1) or 1))
    payload = {"gift": name, "count": count}
    if hasattr(gift, "id") and getattr(gift, "id") is not None:
        payload["gift_id"] = str(gift.id)
    if hasattr(gift, "id") or hasattr(gift, "diamond_count"):
        payload["gift_name"] = name
    diamonds = getattr(gift, "diamond_count", None)
    if isinstance(diamonds, int) and not isinstance(diamonds, bool) and diamonds > 0:
        payload["gift_diamond_count"] = diamonds
        payload["gift_total_diamonds"] = diamonds * count
    if hasattr(event, "repeat_count"):
        payload["repeat_count"] = count
    if hasattr(event, "repeat_end"):
        payload["repeat_end"] = bool(event.repeat_end)
    return _actor(event), payload


def normalize_like(event) -> tuple[str, dict]:
    payload = {"count": max(1, int(getattr(event, "count", 1) or 1))}
    total = getattr(event, "total", None)
    if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
        payload["total_likes"] = total
    return _actor(event), payload


class TikTokWorker:
    MAX_RETRY_SECONDS = 30
    OFFLINE_PROBE_SECONDS = 300

    def __init__(
        self, binding: LiveSourceBinding, emit: Callable,
        sign_api_key: str = "", on_stopped: Callable | None = None,
        on_status: Callable | None = None, trace: bool = False,
    ):
        self.binding = binding
        # The binding keeps the account's display form; SDK discovery uses a bare unique_id.
        self.username = binding.username.strip().removeprefix("@")
        self.tenant_id = binding.tenant_id
        self.session_id = binding.session_id
        self.emit = emit
        self.sign_api_key = sign_api_key.strip()
        self.should_run = True
        self.thread: threading.Thread | None = None
        self.on_stopped = on_stopped
        self.on_status = on_status
        self.client = None
        self.logger = logging.getLogger("interarcade.worker.tiktok")
        self.trace = trace
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active_connect_task: asyncio.Task | None = None
        self._connected_this_attempt = False
        self._disconnect_logged = False
        self._last_room_id: int | None = None
        self._last_offline_log_at = 0.0
        self._last_offline_room_id: int | None = None
        self._last_offline_probe_at = 0.0
        self._last_offline_probe_room_id: int | None = None

    async def handle_gift_event(self, event):
        if getattr(event, "gift", None) is None or _gift_streaking(event):
            return
        actor, payload = normalize_gift(event)
        if self.trace:
            self.logger.info("tiktok_event_received", extra={
                "component": "tiktok", "source_platform": "tiktok",
                "source_account_id": self.binding.account_id,
                "event_type": "gift", "event_id": _native_event_id(event),
                "gift_id": payload.get("gift_id"), "gift_name": payload.get("gift_name"),
                "repeat_count": payload.get("repeat_count"),
            })
        await asyncio.to_thread(self.emit, "gift", actor, **_event_metadata(event), **payload)

    async def handle_like_event(self, event):
        actor, payload = normalize_like(event)
        if self.trace:
            self.logger.info("tiktok_event_received", extra={
                "component": "tiktok", "source_platform": "tiktok",
                "source_account_id": self.binding.account_id,
                "event_type": "like", "event_id": _native_event_id(event),
            })
        await asyncio.to_thread(self.emit, "like", actor, **_event_metadata(event), **payload)

    async def handle_follow_event(self, event):
        if self.trace:
            self.logger.info("tiktok_event_received", extra={
                "component": "tiktok", "source_platform": "tiktok",
                "source_account_id": self.binding.account_id,
                "event_type": "follow", "event_id": _native_event_id(event),
            })
        await asyncio.to_thread(self.emit, "follow", _actor(event), **_event_metadata(event))

    def start(self):
        self.thread = threading.Thread(target=self._thread_main, name=f"tiktok-{self.username}", daemon=True)
        self.thread.start()

    def stop(self):
        self.should_run = False
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._interrupt_connection)

    def _interrupt_connection(self):
        if self.client and getattr(self.client, "connected", False):
            asyncio.create_task(self._disconnect_current_connection())
        elif self._active_connect_task and not self._active_connect_task.done():
            self._active_connect_task.cancel()

    async def _disconnect_current_connection(self):
        try:
            await self.client.disconnect()
        except Exception as exc:
            self.logger.error("tiktok_disconnect_failed", extra=self._context(
                error_type=type(exc).__name__,
            ))
            if self._active_connect_task and not self._active_connect_task.done():
                self._active_connect_task.cancel()

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        finally:
            if self.on_stopped:
                self.on_stopped()

    def _new_client(self):
        from TikTokLive import TikTokLiveClient

        kwargs = {"unique_id": self.username}
        if self.sign_api_key:
            kwargs["web_kwargs"] = {"signer_kwargs": {"sign_api_key": self.sign_api_key}}
        return TikTokLiveClient(**kwargs)

    async def _discover_room(self, client) -> tuple[int | None, int | None]:
        from TikTokLive.client.web.routes.fetch_room_id_api import FetchRoomIdAPIRoute

        # TikTokLive adds the previous room_id to all subsequent web requests.
        # It must not influence discovery of a creator's replacement room.
        client.web.params.pop("room_id", None)
        response = await FetchRoomIdAPIRoute.fetch_user_room_data(client.web, self.username)
        data = response.get("data") or {}
        user = data.get("user") or {}
        live = data.get("liveRoom") or {}
        raw_room_id = user.get("roomId") or live.get("roomId")
        try:
            room_id = int(raw_room_id)
            if room_id <= 0:
                room_id = None
        except (TypeError, ValueError):
            room_id = None
        return room_id, live.get("status")

    @staticmethod
    def _retry_delay(failures: int) -> int:
        return min(5 * 2 ** min(max(failures - 1, 0), 3), TikTokWorker.MAX_RETRY_SECONDS)

    async def _pause(self, seconds: int):
        until = monotonic() + seconds
        while self.should_run and (remaining := until - monotonic()) > 0:
            await asyncio.sleep(min(remaining, 1))

    def _context(self, **fields):
        return {
            "component": "tiktok", "source_platform": "tiktok",
            "source_account_id": self.binding.account_id,
            **fields,
        }

    def _status(self, status: str):
        if self.should_run and self.on_status:
            self.on_status(status)

    def _offline_probe_due(self, room_id: int | None) -> bool:
        if room_id is None:
            return False
        current = monotonic()
        if (room_id == self._last_offline_probe_room_id
                and current - self._last_offline_probe_at < self.OFFLINE_PROBE_SECONDS):
            return False
        self._last_offline_probe_room_id = room_id
        self._last_offline_probe_at = current
        return True

    async def _schedule_retry(self, reason: str, seconds: int, room_id: int | None):
        if not self.should_run:
            return
        self._status("offline" if reason in {"room_unavailable", "sdk_offline"} else "reconnecting")
        self.logger.info("tiktok_reconnect_scheduled", extra=self._context(
            room_id=str(room_id) if room_id else None, reason=reason,
            retry_seconds=seconds,
        ))
        await self._pause(seconds)

    async def _close_client(self, client):
        # TikTokLive 6.6.1 close() assumes curl_cffi exists even when it is None.
        # Close its sessions directly when this worker is finished with the client.
        web = getattr(client, "web", None)
        if web is None:
            return
        sessions = (
            getattr(web, "_httpx", None),
            getattr(getattr(web, "signer", None), "client", None),
            getattr(web, "_curl_cffi", None),
        )
        for session in sessions:
            if session is None:
                continue
            close = getattr(session, "aclose", None) or getattr(session, "close", None)
            if close:
                result = close()
                if inspect.isawaitable(result):
                    await result

    async def _run(self):
        # Imports remain lazy so API-only processes can start without TikTokLive.
        from TikTokLive.client.errors import UserOfflineError
        from TikTokLive.events import (
            CommentEvent, ConnectEvent, DisconnectEvent, FollowEvent,
            GiftEvent, LikeEvent, LiveEndEvent, ShareEvent,
        )

        self._loop = asyncio.get_running_loop()
        client = self._new_client()
        self.client = client

        @client.on(ConnectEvent)
        async def on_connect(event):
            self._connected_this_attempt = True
            self._status("connected")
            self.logger.info("tiktok_websocket_connected", extra=self._context(
                room_id=str(getattr(event, "room_id", None) or self._last_room_id),
            ))

        @client.on(DisconnectEvent)
        async def on_disconnect(_event):
            self._disconnect_logged = True
            self._status("reconnecting")
            message = "tiktok_websocket_lost" if self.should_run else "tiktok_websocket_closed"
            self.logger.info(message, extra=self._context(
                room_id=str(self._last_room_id) if self._last_room_id else None,
            ))

        @client.on(LiveEndEvent)
        async def on_live_end(_event):
            self._status("offline")
            self.logger.info("tiktok_room_ended", extra=self._context(
                room_id=str(self._last_room_id) if self._last_room_id else None,
            ))
            await self._disconnect_current_connection()

        @client.on(GiftEvent)
        async def on_gift(event):
            await self.handle_gift_event(event)

        @client.on(LikeEvent)
        async def on_like(event):
            await self.handle_like_event(event)

        @client.on(CommentEvent)
        async def on_comment(event):
            await asyncio.to_thread(
                self.emit,
                "comment",
                _actor(event),
                **_event_metadata(event),
                comment=str(getattr(event, "comment", "") or ""),
            )

        @client.on(ShareEvent)
        async def on_share(event):
            await asyncio.to_thread(
                self.emit, "share", _actor(event), **_event_metadata(event), count=1
            )

        @client.on(FollowEvent)
        async def on_follow(event):
            await self.handle_follow_event(event)

        failures = 0
        try:
            while self.should_run:
                room_id = None
                stage = "room_discovery"
                try:
                    self._status("connecting" if failures == 0 else "reconnecting")
                    room_id, live_status = await self._discover_room(client)
                    if room_id != self._last_room_id:
                        self.logger.info("tiktok_room_detected", extra=self._context(
                            room_id=str(room_id) if room_id else None,
                            previous_room_id=(str(self._last_room_id)
                                              if self._last_room_id else None),
                            sdk_live_status=live_status,
                        ))
                        self._last_room_id = room_id

                    if room_id is None:
                        failures += 1
                        self.logger.warning("tiktok_room_unavailable", extra=self._context(
                            sdk_live_status=live_status,
                        ))
                        await self._schedule_retry("room_unavailable", self._retry_delay(failures), room_id)
                        continue

                    if str(live_status) == "4":
                        self._status("offline")
                        current = monotonic()
                        if (room_id != self._last_offline_room_id
                                or current - self._last_offline_log_at >= self.OFFLINE_PROBE_SECONDS):
                            self.logger.info("tiktok_api_reports_offline", extra=self._context(
                                room_id=str(room_id), sdk_live_status=live_status,
                            ))
                            self._last_offline_room_id = room_id
                            self._last_offline_log_at = current
                        if not self._offline_probe_due(room_id):
                            failures += 1
                            await self._pause(self._retry_delay(failures))
                            continue
                        self.logger.info("tiktok_offline_room_probe", extra=self._context(
                            room_id=str(room_id), sdk_live_status=live_status,
                        ))

                    stage = "sdk_connect"
                    self._connected_this_attempt = False
                    self._disconnect_logged = False
                    self.logger.info("tiktok_connection_attempt", extra=self._context(
                        room_id=str(room_id), sdk_live_status=live_status,
                    ))
                    self._active_connect_task = asyncio.current_task()
                    try:
                        # The username API supplied this room. The SDK's separate
                        # room/check_alive endpoint can reject a newly active room.
                        await client.connect(room_id=room_id, fetch_live_check=False,
                                             fetch_gift_info=True)
                    finally:
                        self._active_connect_task = None

                    if getattr(client, "connected", False):
                        await client.disconnect()
                    if self._connected_this_attempt:
                        if not self._disconnect_logged and self.should_run:
                            self.logger.info("tiktok_websocket_lost", extra=self._context(
                                room_id=str(room_id),
                            ))
                        failures = 0
                        await self._schedule_retry("websocket_lost", 3, room_id)
                    elif self.should_run:
                        failures += 1
                        self.logger.warning("tiktok_connection_ended_before_websocket",
                                            extra=self._context(room_id=str(room_id)))
                        await self._schedule_retry("no_websocket", self._retry_delay(failures), room_id)
                except asyncio.CancelledError:
                    if self.should_run:
                        raise
                    break
                except UserOfflineError:
                    failures += 1
                    self.logger.info("tiktok_sdk_reported_offline", extra=self._context(
                        room_id=str(room_id) if room_id else None,
                    ))
                    await self._schedule_retry("sdk_offline", self._retry_delay(failures), room_id)
                except Exception as exc:
                    failures += 1
                    self.logger.error("tiktok_connection_failed", extra=self._context(
                        room_id=str(room_id) if room_id else None,
                        reason=stage, error_type=type(exc).__name__,
                    ))
                    delay = (60 if type(exc).__name__ == "SignatureRateLimitError"
                             else self._retry_delay(failures))
                    await self._schedule_retry(stage, delay, room_id)
        finally:
            try:
                if getattr(client, "connected", False):
                    await client.disconnect()
                await self._close_client(client)
            except Exception as exc:
                self.logger.error("tiktok_client_close_failed", extra=self._context(
                    error_type=type(exc).__name__,
                ))
            self._active_connect_task = None
            self._loop = None
