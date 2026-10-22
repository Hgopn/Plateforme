"""TikTok connector metadata and server-owned Dark mappings."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from interarcade.app import create_app, socketio
from interarcade.config import Config
from interarcade.database import Database
from interarcade.dark_tiktok_mapping import DarkTikTokMapping
from interarcade.events import event_from_source
from interarcade.logging import JsonFormatter
from interarcade.worker.live_source import LiveSourceBinding
from interarcade.worker.tiktok import TikTokWorker


class MappingTestConfig(Config):
    SECRET_KEY = "tiktok-mapping-test-secret"
    SESSION_SECRET = "tiktok-mapping-test-session"
    ADMIN_TOKEN = "tiktok-mapping-test-admin"
    INTERNAL_EVENT_TOKEN = "tiktok-mapping-test-internal"
    ALLOWED_ORIGINS = "http://localhost:5000"
    REQUIRE_WORKER_HEARTBEAT = False
    DEMO_MODE = True
    DEMO_TENANT_ID = "tiktok-mapping-tenant"
    DEMO_USERNAME = "creator"


def native_event(event_id, *, user="alex", user_id="viewer-42", **fields):
    return SimpleNamespace(
        user=SimpleNamespace(unique_id=user, user_id=user_id),
        base_message=SimpleNamespace(message_id=event_id, create_time=1_760_000_000),
        **fields,
    )


class TikTokConnectorTests(unittest.TestCase):
    def setUp(self):
        self.emitted = []
        binding = LiveSourceBinding("source-1", "tenant", "session", "tiktok", "songmicon", "songmicon")
        self.worker = TikTokWorker(binding, lambda *args, **kwargs: self.emitted.append((args, kwargs)))

    def test_euler_key_is_optional_and_passed_to_sdk_signer_when_present(self):
        with patch("TikTokLive.TikTokLiveClient") as client_class:
            self.worker._new_client()
            client_class.assert_called_once_with(unique_id="songmicon")

        blank_key_worker = TikTokWorker(self.worker.binding, lambda *_args, **_kwargs: None,
                                       sign_api_key="  ")
        with patch("TikTokLive.TikTokLiveClient") as client_class:
            blank_key_worker._new_client()
            client_class.assert_called_once_with(unique_id="songmicon")

        self.worker.sign_api_key = "test-key-do-not-log"
        with patch("TikTokLive.TikTokLiveClient") as client_class:
            self.worker._new_client()
            client_class.assert_called_once_with(
                unique_id="songmicon",
                web_kwargs={"signer_kwargs": {"sign_api_key": "test-key-do-not-log"}},
            )

    def test_connection_error_does_not_log_key_from_exception(self):
        secret = "test-key-do-not-log"
        self.worker.sign_api_key = secret

        class FailingClient:
            connected = False

            def on(self, _event_type):
                return lambda handler: handler

            async def connect(self, **_kwargs):
                raise RuntimeError(secret)

        async def stop_after_error(_seconds):
            self.worker.should_run = False

        with patch.object(self.worker, "_new_client", return_value=FailingClient()), \
                patch.object(self.worker, "_discover_room", new=AsyncMock(return_value=(101, 1))), \
                patch.object(self.worker, "_pause", side_effect=stop_after_error), \
                self.assertLogs("interarcade.worker.tiktok", level="ERROR") as captured:
            asyncio.run(self.worker._run())
        self.assertEqual(len(captured.records), 1)
        self.assertEqual(captured.records[0].getMessage(), "tiktok_connection_failed")
        self.assertEqual(captured.records[0].error_type, "RuntimeError")
        self.assertNotIn(secret, JsonFormatter().format(captured.records[0]))
        self.assertIsNone(captured.records[0].exc_info)

    def test_room_discovery_drops_previous_room_and_reads_live_status(self):
        web = SimpleNamespace(params={"room_id": "old-room"})
        response = {"data": {"user": {"roomId": "202"}, "liveRoom": {"status": 2}}}
        with patch(
            "TikTokLive.client.web.routes.fetch_room_id_api.FetchRoomIdAPIRoute.fetch_user_room_data",
            new=AsyncMock(return_value=response),
        ) as fetch:
            room_id, status = asyncio.run(self.worker._discover_room(SimpleNamespace(web=web)))
        self.assertEqual((room_id, status), (202, 2))
        self.assertNotIn("room_id", web.params)
        fetch.assert_awaited_once_with(web, "songmicon")

    def test_at_prefix_is_normalized_only_for_sdk_discovery(self):
        binding = LiveSourceBinding("source", "tenant", "session", "tiktok", "@songmicon", "@songmicon")
        worker = TikTokWorker(binding, lambda *_args, **_kwargs: None)
        self.assertEqual(worker.username, "songmicon")
        self.assertEqual(worker.binding.account_id, "@songmicon")

    def test_offline_probe_is_bounded_but_new_room_is_probed_immediately(self):
        with patch("interarcade.worker.tiktok.monotonic", side_effect=[100, 101, 102, 500]):
            self.assertTrue(self.worker._offline_probe_due(101))
            self.assertFalse(self.worker._offline_probe_due(101))
            self.assertTrue(self.worker._offline_probe_due(202))
            self.assertTrue(self.worker._offline_probe_due(202))

    def test_websocket_loss_reconnects_once_to_each_detected_room(self):
        from TikTokLive.events import ConnectEvent, DisconnectEvent

        worker = self.worker

        class FakeClient:
            connected = False

            def __init__(self):
                self.handlers = {}
                self.calls = []

            def on(self, event_type):
                def register(handler):
                    self.handlers[event_type] = handler
                    return handler
                return register

            async def connect(self, **kwargs):
                self.calls.append(kwargs)
                self.connected = True
                await self.handlers[ConnectEvent](SimpleNamespace(room_id=kwargs["room_id"]))
                self.connected = False
                await self.handlers[DisconnectEvent](SimpleNamespace())
                if len(self.calls) == 2:
                    worker.should_run = False

        client = FakeClient()
        with patch.object(worker, "_new_client", return_value=client) as make_client, \
                patch.object(worker, "_discover_room", new=AsyncMock(side_effect=[(101, 2), (202, 2)])), \
                patch.object(worker, "_pause", new=AsyncMock()), \
                self.assertLogs("interarcade.worker.tiktok", level="INFO") as captured:
            asyncio.run(worker._run())
        self.assertEqual([call["room_id"] for call in client.calls], [101, 202])
        self.assertTrue(all(call["fetch_live_check"] is False for call in client.calls))
        self.assertEqual(make_client.call_count, 1)
        messages = [record.getMessage() for record in captured.records]
        self.assertEqual(messages.count("tiktok_room_detected"), 2)
        self.assertEqual(messages.count("tiktok_websocket_connected"), 2)
        self.assertEqual(messages.count("tiktok_websocket_lost"), 2)
        detected = [record for record in captured.records if record.getMessage() == "tiktok_room_detected"]
        self.assertEqual(detected[1].previous_room_id, "101")

    def test_offline_old_room_does_not_repeat_signed_connections_until_room_changes(self):
        worker = self.worker

        class FakeClient:
            connected = False

            def __init__(self):
                self.calls = []

            def on(self, _event_type):
                return lambda handler: handler

            async def connect(self, **kwargs):
                self.calls.append(kwargs["room_id"])
                if len(self.calls) == 2:
                    worker.should_run = False

        client = FakeClient()
        with patch.object(worker, "_new_client", return_value=client), \
                patch.object(worker, "_discover_room", new=AsyncMock(
                    side_effect=[(101, 4), (101, 4), (202, 4)]
                )), patch.object(worker, "_pause", new=AsyncMock()):
            asyncio.run(worker._run())
        self.assertEqual(client.calls, [101, 202])

    def test_rate_limit_failure_waits_longer_before_reconnect(self):
        worker = self.worker

        class SignatureRateLimitError(Exception):
            pass

        class FakeClient:
            connected = False

            def on(self, _event_type):
                return lambda handler: handler

            async def connect(self, **_kwargs):
                raise SignatureRateLimitError()

        async def pause(seconds):
            worker.should_run = False
            self.assertEqual(seconds, 60)

        with patch.object(worker, "_new_client", return_value=FakeClient()), \
                patch.object(worker, "_discover_room", new=AsyncMock(return_value=(101, 2))), \
                patch.object(worker, "_pause", side_effect=pause):
            asyncio.run(worker._run())

    def test_stop_disconnects_active_websocket_without_waiting_for_live_end(self):
        from TikTokLive.events import ConnectEvent, DisconnectEvent

        worker = self.worker

        class FakeClient:
            connected = False

            def __init__(self):
                self.handlers = {}
                self.connected_event = asyncio.Event()
                self.closed_event = asyncio.Event()
                self.disconnect_calls = 0

            def on(self, event_type):
                def register(handler):
                    self.handlers[event_type] = handler
                    return handler
                return register

            async def connect(self, **kwargs):
                self.connected = True
                await self.handlers[ConnectEvent](SimpleNamespace(room_id=kwargs["room_id"]))
                self.connected_event.set()
                await self.closed_event.wait()

            async def disconnect(self):
                self.disconnect_calls += 1
                self.connected = False
                await self.handlers[DisconnectEvent](SimpleNamespace())
                self.closed_event.set()

        async def journey():
            client = FakeClient()
            with patch.object(worker, "_new_client", return_value=client), \
                    patch.object(worker, "_discover_room", new=AsyncMock(return_value=(101, 2))):
                task = asyncio.create_task(worker._run())
                await asyncio.wait_for(client.connected_event.wait(), 2)
                worker.stop()
                await asyncio.wait_for(task, 2)
            return client

        client = asyncio.run(journey())
        self.assertEqual(client.disconnect_calls, 1)
        self.assertFalse(client.connected)

    def test_live_end_closes_old_websocket_before_new_room_connects(self):
        from TikTokLive.events import ConnectEvent, DisconnectEvent, LiveEndEvent

        worker = self.worker

        class FakeClient:
            connected = False

            def __init__(self):
                self.handlers = {}
                self.rooms = []
                self.disconnect_calls = 0

            def on(self, event_type):
                def register(handler):
                    self.handlers[event_type] = handler
                    return handler
                return register

            async def connect(self, **kwargs):
                self.rooms.append(kwargs["room_id"])
                self.connected = True
                await self.handlers[ConnectEvent](SimpleNamespace(room_id=kwargs["room_id"]))
                if len(self.rooms) == 1:
                    await self.handlers[LiveEndEvent](SimpleNamespace())
                else:
                    self.connected = False
                    worker.should_run = False

            async def disconnect(self):
                self.disconnect_calls += 1
                self.connected = False
                await self.handlers[DisconnectEvent](SimpleNamespace())

        client = FakeClient()
        with patch.object(worker, "_new_client", return_value=client), \
                patch.object(worker, "_discover_room", new=AsyncMock(side_effect=[(101, 2), (202, 2)])), \
                patch.object(worker, "_pause", new=AsyncMock()):
            asyncio.run(worker._run())
        self.assertEqual(client.rooms, [101, 202])
        self.assertEqual(client.disconnect_calls, 1)

    def test_follow_event_preserves_native_identity_id_and_timestamp(self):
        asyncio.run(self.worker.handle_follow_event(native_event("follow-1")))
        self.assertEqual(len(self.emitted), 1)
        args, fields = self.emitted[0]
        self.assertEqual(args, ("follow", "alex"))
        self.assertEqual((fields["actor_platform_id"], fields["event_id"]), ("viewer-42", "follow-1"))
        self.assertTrue(fields["timestamp"].endswith("+00:00"))

    def test_streak_intermediates_are_skipped_and_final_total_is_emitted_once(self):
        gift = SimpleNamespace(id=5655, name="Sample gift", diamond_count=20, streakable=True)
        for count, streaking in ((1, True), (2, True), (3, False)):
            event = native_event(f"gift-{count}", gift=gift, repeat_count=count,
                                 repeat_end=not streaking, streaking=streaking)
            asyncio.run(self.worker.handle_gift_event(event))
        self.assertEqual(len(self.emitted), 1)
        args, fields = self.emitted[0]
        self.assertEqual(args, ("gift", "alex"))
        self.assertEqual(fields["event_id"], "gift-3")
        self.assertEqual(fields["count"], 3)
        self.assertEqual(fields["gift_id"], "5655")
        self.assertEqual((fields["gift_diamond_count"], fields["gift_total_diamonds"]), (20, 60))
        self.assertTrue(fields["repeat_end"])

    def test_non_streakable_gift_does_not_wait_for_repeat_end(self):
        gift = SimpleNamespace(id=2, name="One shot", diamond_count=1, streakable=False)
        asyncio.run(self.worker.handle_gift_event(
            native_event("gift-one", gift=gift, repeat_count=1, repeat_end=False)
        ))
        self.assertEqual(len(self.emitted), 1)


class TikTokDarkMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        MappingTestConfig.DATABASE_URL = f"sqlite:///{Path(self.temp_dir.name) / 'mapping.sqlite'}"
        self.app = create_app(MappingTestConfig)
        self.client = self.app.test_client()
        self.db = self.app.extensions["database"]
        self.internal = {"X-InterArcade-Internal-Token": MappingTestConfig.INTERNAL_EVENT_TOKEN}
        created = self.client.post("/api/v1/demo/session", json={"game_id": "dark"})
        self.session = created.get_json()
        self.token = {"Authorization": f"Bearer {self.session['token']}"}
        self.client.post(f"/api/v1/sessions/{self.session['session_id']}/games/dark/start", headers=self.token)
        attached = self.client.post(
            f"/api/v1/sessions/{self.session['session_id']}/sources",
            headers={"Authorization": f"Bearer {MappingTestConfig.ADMIN_TOKEN}"},
            json={
                "source_platform": "tiktok", "source_account_id": "songmicon",
                "source_username": "songmicon", "simulated": True,
            },
        )
        self.assertEqual(attached.status_code, 202)
        self.socket = socketio.test_client(self.app, auth={"token": self.session["token"]})
        self.socket.get_received()

    def tearDown(self):
        self.socket.disconnect()
        self.temp_dir.cleanup()

    def send(self, event_type, event_id, payload=None, actor="alex", viewer_id="viewer-42"):
        return self.client.post("/api/v1/internal/events", headers=self.internal, json={
            "schema_version": 1,
            "tenant_id": MappingTestConfig.DEMO_TENANT_ID,
            "session_id": self.session["session_id"],
            "source_platform": "tiktok",
            "source_account_id": "songmicon",
            "source_username": "songmicon",
            "event_type": event_type,
            "actor_username": actor,
            "actor_platform_id": viewer_id,
            "event_id": event_id,
            "timestamp": "2026-10-13T12:00:00+00:00",
            "payload": payload or {},
        })

    def actions(self):
        return [item["args"][0] for item in self.socket.get_received() if item["name"] == "ia:action"]

    def test_follow_maps_to_help_with_original_event_metadata(self):
        response = self.send("follow", "follow-1")
        self.assertEqual(response.status_code, 202)
        actions = self.actions()
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["action_type"], "PLAYER_HELP")
        self.assertEqual(action["trigger"]["original_event_type"], "follow")
        self.assertEqual(action["trigger"]["original_event_id"], response.get_json()["event_id"])
        self.assertEqual((action["source_platform"], action["source_account_id"], action["actor_id"]),
                         ("tiktok", "songmicon", "tiktok:viewer-42"))
        duplicate = self.send("follow", "follow-1")
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.db.fetchone("SELECT COUNT(*) AS count FROM event_outbox")["count"], 2)

    def test_likes_accumulate_to_configured_threshold_and_survive_reopen(self):
        for count, event_id in ((20, "like-1"), (29, "like-2")):
            self.assertEqual(self.send("like", event_id, {"count": count}).status_code, 202)
            self.assertEqual(self.actions(), [])
        self.assertEqual(self.send("like", "like-3").status_code, 202)
        self.assertEqual([item["action_type"] for item in self.actions()], ["LIGHT_BOOST"])
        self.assertEqual(self.send("like", "like-3").status_code, 200)
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.send("like", "like-4", {"count": 100}).status_code, 202)
        self.assertEqual([item["action_type"] for item in self.actions()], ["LIGHT_BOOST"])
        self.assertEqual(self.db.fetchone(
            "SELECT total_count FROM dark_live_like_progress WHERE session_id = ?",
            (self.session["session_id"],),
        )["total_count"], 150)
        reopened = Database(MappingTestConfig.DATABASE_URL)
        reopened.initialize()
        self.assertEqual(reopened.fetchone(
            "SELECT total_count FROM dark_live_like_progress WHERE session_id = ?",
            (self.session["session_id"],),
        )["total_count"], 150)

    def test_small_medium_large_gifts_and_streak_total(self):
        cases = ((1, "LIGHT_BOOST"), (20, "PLAYER_HELP"), (200, "REVEAL_MAP"))
        for diamonds, expected in cases:
            with self.subTest(diamonds=diamonds):
                response = self.send("gift", f"gift-{diamonds}", {
                    "gift": "Generic sample", "gift_name": "Generic sample", "gift_id": str(diamonds),
                    "count": 1, "repeat_count": 1, "repeat_end": True,
                    "gift_diamond_count": diamonds, "gift_total_diamonds": diamonds,
                })
                self.assertEqual(response.status_code, 202)
                action = self.actions()[0]
                self.assertEqual(action["action_type"], expected)
                self.assertEqual(action["trigger"]["gift_id"], str(diamonds))
                self.assertEqual(action["trigger"]["gift_total_diamonds"], diamonds)
        self.send("gift", "streak-final", {
            "gift": "Generic sample", "gift_name": "Generic sample", "gift_id": "streak",
            "count": 3, "repeat_count": 3, "repeat_end": True,
            "gift_diamond_count": 20, "gift_total_diamonds": 60,
        })
        self.assertEqual(self.actions()[0]["action_type"], "PLAYER_HELP")

    def test_unknown_event_and_unknown_gift_value_are_kept_without_action(self):
        self.assertEqual(self.send("comment", "comment-1", {"comment": "hello"}).status_code, 202)
        self.assertEqual(self.send("gift", "gift-unknown", {"gift": "Unknown", "count": 1}).status_code, 202)
        self.assertEqual(self.send("gift", "gift-zero", {
            "gift": "Unknown", "count": 1, "gift_total_diamonds": 0,
        }).status_code, 202)
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.db.fetchone("SELECT COUNT(*) AS count FROM event_outbox")["count"], 3)

    def test_name_override_is_configurable_without_game_code(self):
        source = Path(Config.DARK_TIKTOK_MAPPING_PATH)
        data = json.loads(source.read_text())
        data["gifts"]["name_overrides"]["custom gift"] = "LIGHT_REDUCE"
        data["gifts"]["id_overrides"]["12345"] = "REVEAL_MAP"
        path = Path(self.temp_dir.name) / "mapping.json"
        path.write_text(json.dumps(data))
        mapping = DarkTikTokMapping.from_path(path)
        event = event_from_source(
            "tiktok", "tenant", "session", "gift", "alex",
            source_account_id="songmicon", gift="Custom Gift", count=1,
        )
        self.assertEqual(mapping.decide(event).action_type, "LIGHT_REDUCE")
        event_with_id = event_from_source(
            "tiktok", "tenant", "session", "gift", "alex",
            source_account_id="songmicon", gift="Custom Gift", gift_id="12345", count=1,
        )
        self.assertEqual(mapping.decide(event_with_id).action_type, "REVEAL_MAP")
        self.assertEqual(mapping.like_threshold, 50)

    def test_dark_game_modules_have_no_platform_specific_logic(self):
        root = Path(__file__).resolve().parent.parent
        paths = [
            root / "interarcade" / "games" / "dark.py",
            root / "interarcade" / "games" / "dark_actions.py",
            *sorted((root / "games" / "dark").glob("*.js")),
        ]
        for path in paths:
            with self.subTest(path=path.name):
                content = path.read_text(encoding="utf-8").casefold()
                self.assertNotIn("tiktok", content)
                self.assertNotIn("twitch", content)

    def test_trace_shows_receive_mapping_delivery_without_secrets(self):
        with patch.object(MappingTestConfig, "TIKTOK_DARK_TRACE", True), \
                self.assertLogs("interarcade.api", level="INFO") as captured:
            response = self.send("follow", "trace-follow")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            [record.getMessage() for record in captured.records],
            ["tiktok_event_received", "tiktok_dark_mapping", "dark_action_delivered"],
        )
        logs = "\n".join(JsonFormatter().format(record) for record in captured.records)
        self.assertIn('"action_type": "PLAYER_HELP"', logs)
        self.assertNotIn(MappingTestConfig.INTERNAL_EVENT_TOKEN, logs)
        self.assertNotIn(MappingTestConfig.ADMIN_TOKEN, logs)


if __name__ == "__main__":
    unittest.main()
