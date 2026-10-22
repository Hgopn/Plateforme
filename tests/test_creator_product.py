"""Creator account, entitlement and Dark product journey tests."""

import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch

from interarcade.app import create_app, socketio
from interarcade.config import Config
from interarcade.database import Database
from interarcade.worker.service import WorkerService


class CreatorConfig(Config):
    SECRET_KEY = "creator-test-secret"
    SESSION_SECRET = "creator-test-session-secret"
    INTERNAL_EVENT_TOKEN = "creator-test-internal"
    ADMIN_TOKEN = "creator-test-admin"
    COOKIE_SECURE = False
    DEMO_MODE = False
    REQUIRE_WORKER_HEARTBEAT = False
    ALLOWED_ORIGINS = ""


class CreatorProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        CreatorConfig.DATABASE_URL = f"sqlite:///{Path(self.temp.name) / 'creator.sqlite'}"
        self.app = create_app(CreatorConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def register(self, email="artist@example.com"):
        return self.client.post("/api/v1/creator/register", json={
            "email": email, "password": "long-secret-phrase", "remember": True,
        })

    def post(self, path, csrf, data=None):
        return self.client.post(path, json=data or {}, headers={"X-CSRF-Token": csrf})

    def test_site_launcher_and_catalogue_are_honest(self):
        site = self.client.get("/")
        launcher = self.client.get("/launcher")
        self.assertEqual(site.status_code, 200)
        self.assertIn(b"Le live entre", site.data)
        self.assertIn(b"Tarifs", site.data)
        self.assertIn(b"aria-roledescription=\"diapositive\"", launcher.data)
        self.assertIn(b"id=\"back-library\"", launcher.data)
        for title in (b"Dark", b"Marble", b"Slot", b"Fight"):
            self.assertIn(title, launcher.data)
        self.assertIn(b"BIENT", launcher.data)
        self.assertNotIn(b"Creator Pro", launcher.data)
        self.assertEqual(self.client.get("/demo").status_code, 404)

    def test_registration_login_csrf_logout_and_revocation(self):
        self.assertEqual(self.client.post("/api/v1/creator/register", json={
            "email": "bad", "password": "short",
        }).status_code, 400)
        created = self.register()
        self.assertEqual(created.status_code, 201)
        body = created.get_json()
        self.assertEqual(body["email"], "artist@example.com")
        self.assertEqual(body["entitled_games"], [])
        self.assertTrue(body["csrf_token"])
        self.assertIn("HttpOnly", created.headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", created.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/api/v1/creator/me").status_code, 200)
        self.assertEqual(self.register().status_code, 409)
        self.assertEqual(self.client.post("/api/v1/creator/logout").status_code, 401)
        self.assertEqual(self.post("/api/v1/creator/logout", "wrong").status_code, 401)
        self.assertEqual(self.post("/api/v1/creator/logout", body["csrf_token"]).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/creator/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/creator/login", json={
            "email": "artist@example.com", "password": "wrong-password",
        }).status_code, 401)
        signed_in = self.client.post("/api/v1/creator/login", json={
            "email": "ARTIST@example.com", "password": "long-secret-phrase",
        })
        self.assertEqual(signed_in.status_code, 200)
        self.assertEqual(signed_in.get_json()["email"], "artist@example.com")
        self.assertEqual(self.client.post("/api/v1/creator/login", json={
            "email": "artist@example.com", "password": "long-secret-phrase",
        }, headers={"Origin": "https://unrelated.example"}).status_code, 403)

    def test_test_journey_and_live_entitlement_are_isolated(self):
        csrf = self.register().get_json()["csrf_token"]
        self.assertEqual(self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "marble", "mode": "test",
        }).status_code, 400)
        self.assertEqual(self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "live",
        }).status_code, 403)
        created = self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "test",
        })
        self.assertEqual(created.status_code, 201)
        session = created.get_json()
        session_id = session["session_id"]
        game_headers = {"Authorization": f"Bearer {session['token']}"}
        socket = socketio.test_client(self.app, auth={"token": session["token"]})
        self.assertTrue(socket.is_connected())
        self.assertEqual(self.client.post(
            f"/api/v1/sessions/{session_id}/games/dark/start", headers=game_headers,
        ).status_code, 201)
        self.assertEqual(self.post(f"/api/v1/creator/sessions/{session_id}/actions", "wrong", {
            "action_type": "LIGHT_BOOST",
        }).status_code, 401)
        action = self.post(f"/api/v1/creator/sessions/{session_id}/actions", csrf, {
            "action_type": "LIGHT_BOOST", "actor_username": "Alex",
        })
        self.assertEqual(action.status_code, 202)
        self.assertEqual(action.get_json()["source_platform"], "test")
        self.assertTrue(any(event["name"] == "ia:action" for event in socket.get_received()))
        self.assertEqual(self.client.get(f"/api/v1/creator/sessions/{session_id}").get_json()["mode"], "test")
        self.assertEqual(self.post(f"/api/v1/creator/sessions/{session_id}/end", csrf).status_code, 200)
        self.assertEqual(self.app.extensions["database"].session(session_id)["status"], "ended")
        self.assertEqual(self.post(f"/api/v1/creator/sessions/{session_id}/actions", csrf, {
            "action_type": "LIGHT_BOOST",
        }).status_code, 409)
        socket.disconnect()

    def test_tiktok_configuration_and_real_license_gate(self):
        account = self.register().get_json()
        csrf = account["csrf_token"]
        self.assertEqual(self.post("/api/v1/creator/platforms/tiktok", csrf, {
            "username": "bad user!",
        }).status_code, 400)
        self.assertEqual(self.post("/api/v1/creator/platforms/tiktok", csrf, {
            "username": "@MyCreator",
        }).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/creator/me").get_json()["platforms"][0]["source_account_id"],
                         "mycreator")
        self.assertEqual(self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "live",
        }).status_code, 403)
        database = self.app.extensions["database"]
        database.upsert_license("dark-license", account["tenant_id"], "PRIVATE-KEY", ["dark"])
        created = self.post("/api/v1/creator/sessions", csrf, {"game_id": "dark", "mode": "live"})
        self.assertEqual(created.status_code, 201)
        session_id = created.get_json()["session_id"]
        status = self.client.get(f"/api/v1/creator/sessions/{session_id}").get_json()
        self.assertEqual(status["sources"][0]["platform"], "tiktok")
        self.assertEqual(status["sources"][0]["status"], "starting")
        self.assertEqual(self.post(f"/api/v1/creator/sessions/{session_id}/actions", csrf, {
            "action_type": "LIGHT_BOOST",
        }).status_code, 409)
        self.assertEqual(self.post(f"/api/v1/creator/sessions/{session_id}/end", csrf).status_code, 200)

    def test_double_launch_restores_one_test_session_and_ends_cleanly(self):
        csrf = self.register().get_json()["csrf_token"]
        body = {"game_id": "dark", "mode": "test"}
        first = self.post("/api/v1/creator/sessions", csrf, body)
        second = self.post("/api/v1/creator/sessions", csrf, body)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        session_id = first.get_json()["session_id"]
        self.assertEqual(second.get_json()["session_id"], session_id)
        restored = self.client.get("/api/v1/creator/sessions/active").get_json()["session"]
        self.assertEqual(restored["session_id"], session_id)
        self.assertTrue(restored["token"])
        self.assertEqual(self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "live",
        }).get_json()["error"], "session_already_active")
        self.assertEqual(self.post(f"/api/v1/creator/sessions/{session_id}/end", csrf).status_code, 200)
        self.assertIsNone(self.client.get("/api/v1/creator/sessions/active").get_json()["session"])
        self.assertEqual(len(self.app.extensions["database"].live_sources(session_id)), 0)

    def test_live_worker_states_stop_and_new_session_binding(self):
        account = self.register().get_json()
        csrf = account["csrf_token"]
        self.post("/api/v1/creator/platforms/tiktok", csrf, {"username": "@MyCreator"})
        database = self.app.extensions["database"]
        database.upsert_license("dark-license", account["tenant_id"], "PRIVATE-KEY", ["dark"])

        class FakeTikTokWorker:
            def __init__(self, binding, _emit, _key, on_stopped, on_status, trace):
                self.binding = binding
                self.on_stopped = on_stopped
                self.on_status = on_status
                self.should_run = True

            def start(self):
                self.on_status("offline")

            def stop(self):
                self.should_run = False
                self.on_stopped()

        with patch("interarcade.worker.service.TikTokWorker", FakeTikTokWorker):
            service = WorkerService(CreatorConfig)
            first = self.post("/api/v1/creator/sessions", csrf, {
                "game_id": "dark", "mode": "live",
            }).get_json()["session_id"]
            service.run_once()
            source = database.live_sources(first)[0]
            self.assertEqual(source["status"], "offline")
            worker = service.workers[source["id"]]
            worker.on_status("reconnecting")
            self.assertEqual(self.client.get(f"/api/v1/creator/sessions/{first}").get_json()
                             ["sources"][0]["status"], "reconnecting")
            worker.on_status("connected")
            self.assertEqual(database.live_sources(first)[0]["status"], "connected")
            self.assertEqual(self.post("/api/v1/creator/sessions", csrf, {
                "game_id": "dark", "mode": "live",
            }).get_json()["session_id"], first)
            self.post(f"/api/v1/creator/sessions/{first}/end", csrf)
            worker.on_status("connected")  # A late callback cannot revive an ended source.
            service.run_once()
            self.assertEqual(database.live_sources(first)[0]["status"], "stopped")
            self.assertFalse(service.workers)
            second = self.post("/api/v1/creator/sessions", csrf, {
                "game_id": "dark", "mode": "live",
            }).get_json()["session_id"]
            service.run_once()
            self.assertNotEqual(first, second)
            self.assertEqual({item.binding.session_id for item in service.workers.values()}, {second})

    def test_abandoned_creator_session_expires_and_stops_source(self):
        account = self.register().get_json()
        csrf = account["csrf_token"]
        self.post("/api/v1/creator/platforms/tiktok", csrf, {"username": "@MyCreator"})
        database = self.app.extensions["database"]
        database.upsert_license("dark-license", account["tenant_id"], "PRIVATE-KEY", ["dark"])
        session_id = self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "live",
        }).get_json()["session_id"]
        database.execute("UPDATE live_sessions SET last_seen_at = ? WHERE id = ?",
                         ("2000-01-01T00:00:00+00:00", session_id))
        self.assertEqual(database.expire_abandoned_sessions(120), [session_id])
        self.assertEqual(database.session(session_id)["status"], "ended")
        self.assertEqual(database.live_sources(session_id)[0]["status"], "stopping")
        self.assertEqual(self.client.get("/api/v1/creator/sessions/active").get_json()["session"], None)

    def test_creator_session_has_hard_expiry_even_with_recent_heartbeat(self):
        csrf = self.register().get_json()["csrf_token"]
        session_id = self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "test",
        }).get_json()["session_id"]
        database = self.app.extensions["database"]
        database.execute("UPDATE live_sessions SET started_at = ? WHERE id = ?",
                         ("2000-01-01T00:00:00+00:00", session_id))
        self.assertEqual(database.expire_abandoned_sessions(120), [session_id])
        self.assertEqual(database.session(session_id)["status"], "ended")

    def test_creator_sees_lost_listener_without_internal_error_details(self):
        account = self.register().get_json()
        csrf = account["csrf_token"]
        self.post("/api/v1/creator/platforms/tiktok", csrf, {"username": "@MyCreator"})
        database = self.app.extensions["database"]
        database.upsert_license("dark-license", account["tenant_id"], "PRIVATE-KEY", ["dark"])
        session_id = self.post("/api/v1/creator/sessions", csrf, {
            "game_id": "dark", "mode": "live",
        }).get_json()["session_id"]
        source = database.live_sources(session_id)[0]
        database.update_live_source(source["id"], "running", "internal stacktrace marker")
        with patch.object(CreatorConfig, "REQUIRE_WORKER_HEARTBEAT", True):
            result = self.client.get(f"/api/v1/creator/sessions/{session_id}").get_json()
        self.assertEqual(result["sources"][0]["status"], "lost")
        self.assertNotIn("last_error", result["sources"][0])
        self.assertNotIn("internal stacktrace marker", str(result))

    def test_second_account_cannot_control_first_accounts_session(self):
        first = self.register().get_json()
        first_session = self.post("/api/v1/creator/sessions", first["csrf_token"], {
            "game_id": "dark", "mode": "test",
        }).get_json()["session_id"]
        other_client = self.app.test_client()
        other = other_client.post("/api/v1/creator/register", json={
            "email": "other@example.com", "password": "another-long-secret",
        }).get_json()
        self.assertEqual(other_client.get(f"/api/v1/creator/sessions/{first_session}").status_code, 404)
        self.assertEqual(other_client.post(
            f"/api/v1/creator/sessions/{first_session}/end",
            headers={"X-CSRF-Token": other["csrf_token"]},
        ).status_code, 404)
        self.assertEqual(self.app.extensions["database"].session(first_session)["status"], "active")

    def test_additive_mode_migration_preserves_existing_session(self):
        path = Path(self.temp.name) / "legacy.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE live_sessions (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, "
                               "game_id TEXT, status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT)")
            connection.execute("INSERT INTO live_sessions VALUES ('old', 'tenant', 'dark', 'active', 'start', NULL)")
        database = Database(f"sqlite:///{path}")
        database.initialize()
        self.assertEqual(database.session("old")["mode"], "live")


if __name__ == "__main__":
    unittest.main()
