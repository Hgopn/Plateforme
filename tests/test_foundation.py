import unittest

from interarcade.app import create_app, socketio
from interarcade.auth import issue_token, verify_token
from interarcade.config import Config
from interarcade.events import event_from_tiktok
from interarcade.licenses import LicenseStore


class TestConfig(Config):
    SECRET_KEY = "test-secret"
    SESSION_SECRET = "test-session-secret"
    ADMIN_TOKEN = "test-admin"
    INTERNAL_EVENT_TOKEN = "test-internal"
    ALLOWED_ORIGINS = "http://localhost:5000"
    DATABASE_URL = "sqlite:////tmp/interarcade-foundation-test.sqlite"
    REQUIRE_WORKER_HEARTBEAT = False


class FoundationTests(unittest.TestCase):
    def test_signed_session_token(self):
        token = issue_token("secret", {"tenant_id": "tenant", "session_id": "session"})
        self.assertEqual(verify_token("secret", token)["tenant_id"], "tenant")
        self.assertIsNone(verify_token("wrong", token))

    def test_event_contract(self):
        event = event_from_tiktok("tenant", "session", "gift", "viewer", gift="Rose", count=1)
        data = event.to_dict()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["payload"]["gift"], "Rose")

    def test_license_lookup(self):
        store = LicenseStore(Config.load_licenses())
        self.assertIsNotNone(store.authorize("songmicon", "IA-SONGMI-PRO", "fight"))
        self.assertIsNone(store.authorize("songmicon", "IA-SONGMI-PRO", "missing"))

    def test_api_protection_and_internal_events(self):
        app = create_app(TestConfig)
        client = app.test_client()
        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.post("/api/v1/internal/events", json={}).status_code, 401)
        self.assertEqual(
            client.post(
                "/api/v1/listeners/start",
                json={"username": "songmicon", "license_key": "IA-SONGMI-PRO"},
            ).status_code,
            401,
        )
        response = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={
                "tenant_id": "songmicon",
                "session_id": "session",
                "type": "gift",
                "actor": "viewer",
                "payload": {"gift": "Rose", "count": 1},
            },
        )
        self.assertEqual(response.status_code, 202)

        malformed = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"tenant_id": "songmicon", "session_id": "session", "type": "gift", "actor": "viewer", "payload": []},
        )
        self.assertEqual(malformed.status_code, 400)

        unsupported = client.post(
            "/api/v1/internal/events",
            headers={"X-InterArcade-Internal-Token": "test-internal"},
            json={"schema_version": 99, "tenant_id": "songmicon", "session_id": "session", "type": "gift", "actor": "viewer"},
        )
        self.assertEqual(unsupported.status_code, 400)

    def test_session_and_detailed_health(self):
        app = create_app(TestConfig)
        client = app.test_client()
        response = client.post(
            "/api/v1/sessions",
            json={"tenant_id": "songmicon", "username": "songmicon", "game_id": "fight", "license_key": "IA-SONGMI-PRO"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.get_json())
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["checks"]["database"], True)
        started = client.post(
            "/api/v1/listeners/start",
            headers={"Authorization": "Bearer test-admin"},
            json={"tenant_id": "songmicon", "username": "songmicon", "session_id": response.get_json()["session_id"]},
        )
        self.assertEqual(started.status_code, 202)
        stopped = client.post(
            "/api/v1/listeners/stop",
            headers={"Authorization": "Bearer test-admin"},
            json={"tenant_id": "songmicon"},
        )
        self.assertEqual(stopped.status_code, 202)

    def test_socket_requires_signed_session(self):
        app = create_app(TestConfig)
        anonymous = socketio.test_client(app, auth=None)
        self.assertFalse(anonymous.is_connected())
        token = issue_token(TestConfig.SESSION_SECRET, {"tenant_id": "tenant", "session_id": "session"})
        authenticated = socketio.test_client(app, auth={"token": token})
        self.assertTrue(authenticated.is_connected())


if __name__ == "__main__":
    unittest.main()
