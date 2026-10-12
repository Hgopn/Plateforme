import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from interarcade.app import create_app, socketio
from interarcade.auth import issue_token, verify_token
from interarcade.config import Config
from interarcade.events import event_from_tiktok
from interarcade.worker.service import WorkerService
from interarcade.worker.tiktok import normalize_gift, normalize_like


class TestConfig(Config):
    SECRET_KEY = "test-secret"
    SESSION_SECRET = "test-session-secret"
    ADMIN_TOKEN = "test-admin"
    INTERNAL_EVENT_TOKEN = "test-internal"
    ALLOWED_ORIGINS = "http://localhost:5000"
    DATABASE_URL = "sqlite:////tmp/interarcade-foundation-test.sqlite"
    REQUIRE_WORKER_HEARTBEAT = False
    DEMO_MODE = False


class MarbleDemoConfig(TestConfig):
    DEMO_MODE = True
    DEMO_TENANT_ID = "demo-tenant"
    DEMO_USERNAME = "demo-user"


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        TestConfig.DATABASE_URL = f"sqlite:///{Path(self.temp_dir.name) / 'foundation.sqlite'}"

    def tearDown(self):
        self.temp_dir.cleanup()

    def app_with_license(self, config=TestConfig):
        app = create_app(config)
        database = app.extensions["database"]
        database.upsert_tenant("test-tenant", "test-creator")
        database.upsert_license(
            "test-license", "test-tenant", "TEST-LICENSE", ["slot", "dark", "marble", "fight"]
        )
        return app

    def test_signed_session_token(self):
        token = issue_token("secret", {"tenant_id": "tenant", "session_id": "session"})
        self.assertEqual(verify_token("secret", token)["tenant_id"], "tenant")
        self.assertIsNone(verify_token("wrong", token))
        self.assertIsNone(verify_token("secret", "not-base64.%%%"))

    def test_api_requires_session_secret(self):
        class MissingSecretConfig(TestConfig):
            SESSION_SECRET = ""

        with self.assertRaisesRegex(RuntimeError, "SESSION_SECRET"):
            create_app(MissingSecretConfig)

    def test_worker_requires_internal_event_token(self):
        class MissingTokenConfig(TestConfig):
            INTERNAL_EVENT_TOKEN = ""

        with self.assertRaisesRegex(RuntimeError, "INTERNAL_EVENT_TOKEN"):
            WorkerService(MissingTokenConfig)

    def test_event_contract(self):
        event = event_from_tiktok("tenant", "session", "gift", "viewer", gift="Rose", count=1)
        data = event.to_dict()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["payload"]["gift"], "Rose")

    def test_license_lookup_uses_persistent_database_only(self):
        app = self.app_with_license()
        database = app.extensions["database"]
        self.assertEqual(database.license_for("test-tenant", "TEST-LICENSE")["games"], ["slot", "dark", "marble", "fight"])
        self.assertIsNone(database.license_for("test-tenant", "wrong"))

    def test_api_protection_and_internal_events(self):
        app = self.app_with_license()
        client = app.test_client()
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.post("/api/v1/internal/events", json={}).status_code, 401)
        self.assertEqual(
            client.post(
                "/api/v1/listeners/start",
                json={"tenant_id": "test-tenant", "username": "test-creator", "session_id": "missing"},
            ).status_code,
            401,
        )
        session = client.post(
            "/api/v1/sessions",
            json={
                "tenant_id": "test-tenant",
                "username": "test-creator",
                "game_id": "dark",
                "license_key": "TEST-LICENSE",
            },
        ).get_json()
        response = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={
                "tenant_id": "test-tenant",
                "session_id": session["session_id"],
                "type": "gift",
                "actor": "viewer",
                "payload": {"gift": "Rose", "count": 1},
            },
        )
        self.assertEqual(response.status_code, 202)

        malformed = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"tenant_id": "test-tenant", "session_id": session["session_id"], "type": "gift", "actor": "viewer", "payload": []},
        )
        self.assertEqual(malformed.status_code, 400)

        unsupported = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"schema_version": 99, "tenant_id": "test-tenant", "session_id": session["session_id"], "type": "gift", "actor": "viewer"},
        )
        self.assertEqual(unsupported.status_code, 400)

        missing = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"tenant_id": "test-tenant", "session_id": "missing", "type": "like", "actor": "viewer", "payload": {"count": 1}},
        )
        self.assertEqual(missing.status_code, 404)
        wrong_tenant = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"tenant_id": "other", "session_id": session["session_id"], "type": "like", "actor": "viewer", "payload": {"count": 1}},
        )
        self.assertEqual(wrong_tenant.status_code, 409)
        invalid_count = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"tenant_id": "test-tenant", "session_id": session["session_id"], "type": "like", "actor": "viewer", "payload": {"count": "many"}},
        )
        self.assertEqual(invalid_count.status_code, 400)

    def test_session_and_detailed_health(self):
        app = self.app_with_license()
        client = app.test_client()
        response = client.post(
            "/api/v1/sessions",
            json={"tenant_id": "test-tenant", "username": "test-creator", "game_id": "fight", "license_key": "TEST-LICENSE"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.get_json())
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["checks"]["database"], True)
        started = client.post(
            "/api/v1/listeners/start",
            headers={"Authorization": "Bearer test-admin"},
            json={"tenant_id": "test-tenant", "username": "test-creator", "session_id": response.get_json()["session_id"]},
        )
        self.assertEqual(started.status_code, 202)
        stopped = client.post(
            "/api/v1/listeners/stop",
            headers={"Authorization": "Bearer test-admin"},
            json={"tenant_id": "test-tenant"},
        )
        self.assertEqual(stopped.status_code, 202)
        self.assertEqual(client.post("/start_listener").status_code, 404)
        self.assertEqual(client.post("/stop_listener").status_code, 404)

    def test_socket_requires_signed_session(self):
        app = self.app_with_license()
        anonymous = socketio.test_client(app, auth=None)
        self.assertFalse(anonymous.is_connected())
        invalid_token = issue_token(TestConfig.SESSION_SECRET, {"tenant_id": "test-tenant", "session_id": "missing"})
        self.assertFalse(socketio.test_client(app, auth={"token": invalid_token}).is_connected())
        database = app.extensions["database"]
        database.save_session("session-one", "test-tenant", "slot")
        database.save_session("session-two", "test-tenant", "dark")
        token = issue_token(TestConfig.SESSION_SECRET, {"tenant_id": "test-tenant", "session_id": "session-one"})
        authenticated = socketio.test_client(app, auth={"token": token})
        self.assertTrue(authenticated.is_connected())
        other_token = issue_token(TestConfig.SESSION_SECRET, {"tenant_id": "test-tenant", "session_id": "session-two"})
        other = socketio.test_client(app, auth={"token": other_token})
        authenticated.get_received()
        other.get_received()
        event = event_from_tiktok("test-tenant", "session-one", "gift", "viewer", gift="Rose", count=1)
        with app.test_request_context():
            socketio.emit("ia:event", event.to_dict(), to="session:session-one")
        self.assertEqual(len(authenticated.get_received()), 1)
        self.assertEqual(other.get_received(), [])
        database.end_session("session-one")
        ended = socketio.test_client(app, auth={"token": token})
        self.assertFalse(ended.is_connected())

    def test_ready_health_fails_when_broker_is_unavailable(self):
        app = self.app_with_license()
        app.extensions["broker"].ping = lambda: False
        response = app.test_client().get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["checks"]["broker"], False)

    def test_tiktok_event_normalizers_use_incremental_like_count(self):
        user = SimpleNamespace(unique_id="viewer")
        actor, like = normalize_like(SimpleNamespace(user=user, count=7, total_like_count=9000))
        self.assertEqual((actor, like), ("viewer", {"count": 7}))
        actor, gift = normalize_gift(
            SimpleNamespace(user=user, gift=SimpleNamespace(name="Rose"), repeat_count=3)
        )
        self.assertEqual((actor, gift), ("viewer", {"gift": "Rose", "count": 3}))

    def test_marble_round_api_controls_score_and_session_end(self):
        app = create_app(MarbleDemoConfig)
        client = app.test_client()
        session = client.post("/api/v1/demo/session", json={"game_id": "marble"}).get_json()
        headers = {"Authorization": f"Bearer {session['token']}"}
        started = client.post(
            f"/api/v1/sessions/{session['session_id']}/games/marble/start",
            headers=headers,
            json={"config": {"gift_target": 2}},
        )
        self.assertEqual(started.status_code, 201)
        event = client.post(
            "/api/v1/demo/events",
            json={"session_id": session["session_id"], "type": "gift", "actor": "viewer", "payload": {"gift": "Rose", "count": 2}},
        )
        self.assertEqual(event.status_code, 202)
        state = client.get(f"/api/v1/sessions/{session['session_id']}/games/marble/state", headers=headers).get_json()["state"]
        self.assertEqual(state["status"], "finished")
        self.assertEqual(state["winner"], "GIFTS")
        self.assertEqual(client.post(f"/api/v1/sessions/{session['session_id']}/end", headers=headers).status_code, 200)
        ended = client.get(f"/api/v1/sessions/{session['session_id']}/games/marble/state", headers=headers).get_json()["state"]
        self.assertEqual(ended["status"], "finished")
        self.assertEqual(
            client.post(
                "/api/v1/demo/events",
                json={"session_id": session["session_id"], "type": "gift", "actor": "late-viewer", "payload": {"count": 2}},
            ).status_code,
            409,
        )
        unchanged = client.get(f"/api/v1/sessions/{session['session_id']}/games/marble/state", headers=headers).get_json()["state"]
        self.assertEqual(unchanged["gift_score"], ended["gift_score"])


if __name__ == "__main__":
    unittest.main()
