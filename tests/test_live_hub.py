import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interarcade.app import create_app, socketio
from interarcade.config import Config
from interarcade.database import Database
from interarcade.events import actor_identity, event_from_source
from interarcade.worker.service import WorkerService


class LiveHubTestConfig(Config):
    SECRET_KEY = "live-hub-test-secret"
    SESSION_SECRET = "live-hub-test-session"
    ADMIN_TOKEN = "live-hub-test-admin"
    INTERNAL_EVENT_TOKEN = "live-hub-test-internal"
    ALLOWED_ORIGINS = "http://localhost:5000"
    REQUIRE_WORKER_HEARTBEAT = False
    DEMO_MODE = True
    DEMO_TENANT_ID = "live-hub-tenant"
    DEMO_USERNAME = "creator"


class LiveHubTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        LiveHubTestConfig.DATABASE_URL = f"sqlite:///{Path(self.temp_dir.name) / 'live.sqlite'}"
        self.app = create_app(LiveHubTestConfig)
        self.client = self.app.test_client()
        self.db = self.app.extensions["database"]
        self.admin = {"Authorization": f"Bearer {LiveHubTestConfig.ADMIN_TOKEN}"}
        self.internal = {"X-InterArcade-Internal-Token": LiveHubTestConfig.INTERNAL_EVENT_TOKEN}

    def tearDown(self):
        self.temp_dir.cleanup()

    def session(self, game_id="dark"):
        response = self.client.post("/api/v1/demo/session", json={"game_id": game_id})
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def attach(self, session_id, platform, account_id):
        response = self.client.post(
            f"/api/v1/sessions/{session_id}/sources",
            headers=self.admin,
            json={
                "source_platform": platform,
                "source_account_id": account_id,
                "source_username": "creator",
                "simulated": True,
            },
        )
        self.assertEqual(response.status_code, 202)
        return response.get_json()

    def internal_event(self, session_id, platform, account_id, raw_id="provider-1"):
        return self.client.post(
            "/api/v1/internal/events",
            headers=self.internal,
            json={
                "schema_version": 1,
                "tenant_id": LiveHubTestConfig.DEMO_TENANT_ID,
                "session_id": session_id,
                "source_platform": platform,
                "source_account_id": account_id,
                "source_username": "creator",
                "event_type": "gift",
                "actor_platform_id": "viewer-42",
                "actor_username": "alex",
                "event_id": raw_id,
                "payload": {"gift": "Rose", "count": 1},
            },
        )

    def test_session_without_source_still_receives_normalized_test_events(self):
        session = self.session()
        token = {"Authorization": f"Bearer {session['token']}"}
        sources = self.client.get(f"/api/v1/sessions/{session['session_id']}/sources", headers=token)
        self.assertEqual(sources.get_json()["sources"], [])
        self.client.post(f"/api/v1/sessions/{session['session_id']}/games/dark/start", headers=token)
        socket = socketio.test_client(self.app, auth={"token": session["token"]})
        socket.get_received()
        response = self.client.post(
            "/api/v1/demo/events",
            json={
                "session_id": session["session_id"], "type": "like",
                "actor": "alex", "payload": {"count": 2},
            },
        )
        self.assertEqual(response.status_code, 202)
        event = response.get_json()
        self.assertEqual(event["source_platform"], "test")
        self.assertEqual(event["event_type"], "like")
        self.assertEqual(event["event_value"], 2)
        delivered = [item["args"][0] for item in socket.get_received() if item["name"] == "ia:event"]
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["event_id"], event["event_id"])
        self.assertEqual(delivered[0]["actor_id"], actor_identity("test", "alex"))
        socket.disconnect()

    def test_two_simulated_platforms_keep_same_username_and_raw_event_id_distinct(self):
        session = self.session("marble")
        other = self.session("dark")
        token = {"Authorization": f"Bearer {session['token']}"}
        self.client.post(
            f"/api/v1/sessions/{session['session_id']}/games/marble/start",
            headers=token,
            json={"config": {"gift_target": 2}},
        )
        tiktok = self.attach(session["session_id"], "tiktok", "tiktok-creator")
        twitch = self.attach(session["session_id"], "twitch", "twitch-creator")
        self.assertNotEqual(tiktok["id"], twitch["id"])
        sources = self.client.get(f"/api/v1/sessions/{session['session_id']}/sources", headers=token)
        self.assertEqual(len(sources.get_json()["sources"]), 2)

        socket = socketio.test_client(self.app, auth={"token": session["token"]})
        other_socket = socketio.test_client(self.app, auth={"token": other["token"]})
        socket.get_received()
        other_socket.get_received()
        first = self.internal_event(session["session_id"], "tiktok", "tiktok-creator")
        second = self.internal_event(session["session_id"], "twitch", "twitch-creator")
        self.assertEqual((first.status_code, second.status_code), (202, 202))
        first_event, second_event = first.get_json(), second.get_json()
        self.assertTrue({
            "source_platform", "source_account_id", "source_username", "event_type", "event_value",
            "event_id", "timestamp", "session_id", "tenant_id", "actor_id", "actor_platform_id",
        } <= set(first_event))
        self.assertEqual(first_event["actor_username"], second_event["actor_username"])
        self.assertNotEqual(first_event["actor_id"], second_event["actor_id"])
        self.assertNotEqual(first_event["event_id"], second_event["event_id"])
        self.assertEqual(first_event["source_event_id"], second_event["source_event_id"])
        self.assertEqual(first_event["event_value"], second_event["event_value"])
        delivered = [item["args"][0] for item in socket.get_received() if item["name"] == "ia:event"]
        self.assertEqual({item["event_id"] for item in delivered}, {first_event["event_id"], second_event["event_id"]})
        self.assertFalse(any(item["name"] == "ia:event" for item in other_socket.get_received()))
        state = self.client.get(
            f"/api/v1/sessions/{session['session_id']}/games/marble/state", headers=token
        ).get_json()["state"]
        self.assertEqual((state["gift_score"], state["winner"]), (2, "GIFTS"))
        rows = self.db.fetchall(
            "SELECT envelope_json FROM event_outbox WHERE session_id = ? ORDER BY event_id",
            (session["session_id"],),
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {json.loads(row["envelope_json"])["actor_id"] for row in rows},
            {"tiktok:viewer-42", "twitch:viewer-42"},
        )
        duplicate = self.internal_event(session["session_id"], "tiktok", "tiktok-creator")
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate.get_json()["accepted"])
        unknown = self.internal_event(session["session_id"], "twitch", "other-account", "provider-2")
        self.assertEqual(unknown.status_code, 409)
        self.assertEqual(unknown.get_json()["error"], "source_inactive")
        wrong_session = self.internal_event(other["session_id"], "tiktok", "tiktok-creator", "provider-2")
        self.assertEqual(wrong_session.status_code, 409)
        self.assertEqual(wrong_session.get_json()["error"], "source_inactive")

        self.client.post(f"/api/v1/sessions/{session['session_id']}/end", headers=token)
        self.assertEqual(
            {row["status"] for row in self.db.live_sources(session["session_id"])}, {"stopped"}
        )
        socket.disconnect()
        other_socket.disconnect()

    def test_existing_tiktok_route_uses_live_source_connector_without_network(self):
        session = self.session()
        response = self.client.post(
            "/api/v1/listeners/start", headers=self.admin,
            json={
                "tenant_id": LiveHubTestConfig.DEMO_TENANT_ID,
                "username": "creator", "session_id": session["session_id"],
            },
        )
        self.assertEqual(response.status_code, 202)
        source = self.db.live_sources(session["session_id"])[0]
        self.assertEqual((source["platform"], source["account_id"], source["status"]),
                         ("tiktok", "creator", "starting"))

        class FakeTikTok:
            def __init__(self, binding, emit, _sign_api_key, on_stopped, on_status=None,
                         trace=False):
                self.binding = binding
                self.emit = emit
                self.on_stopped = on_stopped
                self.on_status = on_status
                self.should_run = True
                self.started = False

            def start(self):
                self.started = True

            def stop(self):
                self.should_run = False
                self.on_stopped()

        with patch("interarcade.worker.service.TikTokWorker", FakeTikTok):
            service = WorkerService(LiveHubTestConfig)
            events = []
            service._post_event = events.append
            service.run_once()
            worker = service.workers[source["id"]]
            self.assertTrue(worker.started)
            worker.emit("gift", "alex", actor_platform_id="viewer-42", gift="Rose", count=1)
            self.assertEqual(events[0].to_dict()["source_account_id"], "creator")
            self.assertEqual(events[0].to_dict()["actor_id"], "tiktok:viewer-42")
            delivered = self.client.post(
                "/api/v1/internal/events", headers=self.internal, json=events[0].to_dict()
            )
            self.assertEqual(delivered.status_code, 202)
            self.assertEqual(delivered.get_json()["event_id"], events[0].event_id)
            retry = self.client.post(
                "/api/v1/internal/events", headers=self.internal, json=events[0].to_dict()
            )
            self.assertEqual(retry.status_code, 200)
            self.assertFalse(retry.get_json()["accepted"])
            stopped = self.client.post(
                "/api/v1/listeners/stop", headers=self.admin,
                json={"tenant_id": LiveHubTestConfig.DEMO_TENANT_ID},
            )
            self.assertEqual(stopped.status_code, 202)
            service.run_once()
            self.assertEqual(self.db.live_source(source["id"])["status"], "stopped")

    def test_twitch_live_connector_is_not_enabled(self):
        session = self.session()
        response = self.client.post(
            f"/api/v1/sessions/{session['session_id']}/sources",
            headers=self.admin,
            json={
                "source_platform": "twitch", "source_account_id": "creator",
                "source_username": "creator",
            },
        )
        self.assertEqual(response.status_code, 501)
        self.assertEqual(self.db.live_sources(session["session_id"]), [])

    def test_internal_ingress_rejects_invalid_source_fields_without_server_error(self):
        session = self.session()
        body = {
            "tenant_id": LiveHubTestConfig.DEMO_TENANT_ID,
            "session_id": session["session_id"],
            "source_platform": "tiktok",
            "event_type": "like",
            "actor_username": "alex",
            "payload": {"count": 1},
        }
        for change in (
            {"source_platform": 123},
            {"source_account_id": 123},
            {"source_account_id": None},
            {"event_id": 123},
            {"payload": {"count": 1, "source": "twitch"}},
        ):
            response = self.client.post(
                "/api/v1/internal/events", headers=self.internal, json={**body, **change}
            )
            self.assertEqual(response.status_code, 400)

    def test_event_ids_are_scoped_by_account_as_well_as_platform(self):
        first = event_from_source(
            "tiktok", "tenant", "session", "like", "alex", "raw:1",
            source_account_id="creator/a", actor_platform_id="viewer-42", count=1,
        )
        second = event_from_source(
            "tiktok", "tenant", "session", "like", "alex", "raw:1",
            source_account_id="creator:b", actor_platform_id="viewer-42", count=1,
        )
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertEqual(first.actor_id, second.actor_id)


class LiveHubMigrationTests(unittest.TestCase):
    def test_existing_listener_and_outbox_survive_additive_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE listeners (tenant_id TEXT PRIMARY KEY, username TEXT NOT NULL, "
                    "session_id TEXT, status TEXT NOT NULL, last_error TEXT, started_at TEXT, updated_at TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO listeners VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("tenant", "creator", "session", "stopped", None, "2026-01-01", "2026-01-01"),
                )
                connection.execute(
                    "CREATE TABLE event_outbox (event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                    "session_id TEXT NOT NULL, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, "
                    "status TEXT NOT NULL DEFAULT 'accepted', attempts INTEGER NOT NULL DEFAULT 0, "
                    "created_at TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO event_outbox (event_id, tenant_id, session_id, event_type, payload_json, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("old-event", "tenant", "session", "like", "{}", "2026-01-01"),
                )
            database = Database(f"sqlite:///{path}")
            database.initialize()
            database.initialize()
            self.assertEqual(database.live_sources("session")[0]["platform"], "tiktok")
            self.assertEqual(len(database.live_sources("session")), 1)
            database.save_session("new-session", "tenant", "slot")
            database.save_listener("tenant", "creator", "new-session", "starting")
            self.assertEqual(len(database.live_sources("session")), 1)
            self.assertEqual(len(database.live_sources("new-session")), 1)
            old = database.fetchone("SELECT event_id, envelope_json FROM event_outbox WHERE event_id = ?", ("old-event",))
            self.assertEqual(old, {"event_id": "old-event", "envelope_json": None})
            self.assertEqual(database.fetchone("SELECT COUNT(*) AS count FROM listeners")["count"], 1)


if __name__ == "__main__":
    unittest.main()
