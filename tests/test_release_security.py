"""Release boundary checks for auth, tenant isolation and browser responses."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interarcade.app import create_app
from interarcade.auth import issue_token
from interarcade.config import Config
from interarcade.worker.service import WorkerService


class SecurityConfig(Config):
    SECRET_KEY = "release-test-secret"
    SESSION_SECRET = "release-test-session-secret"
    ADMIN_TOKEN = "release-test-admin"
    INTERNAL_EVENT_TOKEN = "release-test-internal"
    OBSERVER_TOKEN = "release-test-observer"
    ALLOWED_ORIGINS = "https://trusted.example"
    COOKIE_SECURE = True
    TRUST_PROXY_CLIENT_IP = False
    DEMO_MODE = False
    REQUIRE_WORKER_HEARTBEAT = False


class ReleaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        SecurityConfig.DATABASE_URL = f"sqlite:///{Path(self.temp.name) / 'security.sqlite'}"
        self.app = create_app(SecurityConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def register(client, email):
        return client.post("/api/v1/creator/register", json={
            "email": email, "password": "release-test-password", "remember": True,
        })

    def test_response_headers_cookies_and_cors(self):
        page = self.client.get("/launcher")
        self.assertEqual(page.headers["X-Frame-Options"], "DENY")
        self.assertIn("script-src 'self'", page.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        self.assertEqual(page.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("camera=()", page.headers["Permissions-Policy"])
        game = self.client.get("/games/dark/dark.html")
        self.assertEqual(game.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("frame-ancestors 'self'", game.headers["Content-Security-Policy"])
        game.close()
        cookie = self.register(self.client, "headers@example.com").headers["Set-Cookie"]
        for attribute in ("Secure", "HttpOnly", "SameSite=Strict"):
            self.assertIn(attribute, cookie)
        trusted = self.client.get("/api/v1/creator/me", headers={"Origin": "https://trusted.example"})
        untrusted = self.client.get("/api/v1/creator/me", headers={"Origin": "https://evil.example"})
        self.assertEqual(trusted.headers.get("Access-Control-Allow-Origin"), "https://trusted.example")
        self.assertIsNone(untrusted.headers.get("Access-Control-Allow-Origin"))
        insecure_origin = self.client.post("/api/v1/creator/register", json={
            "email": "origin@example.com", "password": "release-test-password",
        }, headers={"Origin": "http://localhost"})
        self.assertEqual(insecure_origin.status_code, 403)

    def test_rate_limit_ignores_untrusted_forwarded_ip(self):
        for attempt in range(10):
            response = self.client.post("/api/v1/creator/register", json={
                "email": "bad", "password": "short",
            }, headers={"X-InterArcade-Client-IP": f"203.0.113.{attempt + 1}"})
            self.assertEqual(response.status_code, 400)
        blocked = self.client.post("/api/v1/creator/register", json={
            "email": "bad", "password": "short",
        }, headers={"X-InterArcade-Client-IP": "203.0.113.200"})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers["Retry-After"], "900")

    def test_csrf_expired_cookie_and_invalid_payloads(self):
        registered = self.register(self.client, "csrf@example.com")
        csrf = registered.get_json()["csrf_token"]
        self.assertEqual(self.client.post("/api/v1/creator/platforms/tiktok", json={
            "username": "@validname",
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/creator/platforms/tiktok", json={
            "username": "invalid name!",
        }, headers={"X-CSRF-Token": csrf}).status_code, 400)
        invalid = self.client.post("/api/v1/internal/events", json={
            "tenant_id": "tenant", "session_id": "session", "event_type": "gift",
            "actor_username": "viewer", "payload": [],
        }, headers={"X-InterArcade-Internal-Token": SecurityConfig.INTERNAL_EVENT_TOKEN})
        self.assertEqual(invalid.status_code, 400)
        oversized = self.client.post("/api/v1/internal/events", data=b"x" * (65 * 1024),
                                     content_type="application/json",
                                     headers={"X-InterArcade-Internal-Token": SecurityConfig.INTERNAL_EVENT_TOKEN})
        self.assertEqual(oversized.status_code, 413)
        token = registered.headers["Set-Cookie"].split("ia_creator=", 1)[1].split(";", 1)[0]
        self.app.extensions["database"].execute(
            "UPDATE creator_logins SET expires_at = ? WHERE token_hash = ?",
            ("2000-01-01T00:00:00+00:00", hashlib.sha256(token.encode()).hexdigest()),
        )
        self.assertEqual(self.client.get("/api/v1/creator/me").status_code, 401)

    def test_login_is_generic_throttled_and_logins_revoke_independently(self):
        first = self.register(self.client, "account@example.com")
        first_csrf = first.get_json()["csrf_token"]
        other = self.app.test_client()
        second = other.post("/api/v1/creator/login", json={
            "email": "account@example.com", "password": "release-test-password",
        })
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/creator/me").status_code, 200)
        self.assertEqual(other.get("/api/v1/creator/me").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/creator/logout", headers={
            "X-CSRF-Token": first_csrf,
        }).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/creator/me").status_code, 401)
        self.assertEqual(other.get("/api/v1/creator/me").status_code, 200)
        for _ in range(10):
            denied = self.client.post("/api/v1/creator/login", json={
                "email": "unknown@example.com", "password": "incorrect-password",
            })
            self.assertEqual(denied.get_json()["error"], "invalid_credentials")
        blocked = self.client.post("/api/v1/creator/login", json={
            "email": "unknown@example.com", "password": "incorrect-password",
        })
        self.assertEqual(blocked.status_code, 429)

    def test_tenant_event_and_admin_boundaries(self):
        first = self.register(self.client, "first@example.com").get_json()
        second_client = self.app.test_client()
        second = self.register(second_client, "second@example.com").get_json()
        first_session = self.client.post("/api/v1/creator/sessions", json={
            "game_id": "dark", "mode": "test",
        }, headers={"X-CSRF-Token": first["csrf_token"]}).get_json()
        second_session = second_client.post("/api/v1/creator/sessions", json={
            "game_id": "dark", "mode": "test",
        }, headers={"X-CSRF-Token": second["csrf_token"]}).get_json()
        sid = second_session["session_id"]
        self.assertEqual(self.client.get(f"/api/v1/creator/sessions/{sid}").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/creator/sessions/{sid}/end", headers={
            "X-CSRF-Token": first["csrf_token"],
        }).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/sessions/{sid}/games/dark/start", headers={
            "Authorization": f"Bearer {first_session['token']}",
        }).status_code, 401)
        injected = self.client.post("/api/v1/internal/events", json={
            "tenant_id": first["tenant_id"], "session_id": sid,
            "event_type": "gift", "actor_username": "viewer", "payload": {"gift": "Rose"},
        }, headers={"X-InterArcade-Internal-Token": SecurityConfig.INTERNAL_EVENT_TOKEN})
        self.assertEqual(injected.status_code, 409)
        self.assertEqual(injected.get_json()["error"], "session_tenant_mismatch")
        for endpoint in ("/api/v1/listeners", "/api/v1/diagnostics"):
            self.assertEqual(self.client.get(endpoint).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/internal/events", json={}).status_code, 401)
        expired = issue_token(SecurityConfig.SESSION_SECRET, {
            "tenant_id": second["tenant_id"], "session_id": sid,
        }, ttl_seconds=-10)
        self.assertEqual(second_client.post(f"/api/v1/sessions/{sid}/games/dark/start", headers={
            "Authorization": f"Bearer {expired}",
        }).status_code, 401)

    def test_frontend_and_desktop_do_not_contain_server_credentials(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / "static/launcher.js", root / "desktop/main.js",
                     root / "desktop/preload.js", root / "desktop/server.json"):
            content = path.read_text()
            for name in ("INTERARCADE_ADMIN_TOKEN", "INTERARCADE_INTERNAL_EVENT_TOKEN",
                         "INTERARCADE_DB_PASSWORD", "EULER_API_KEY"):
                self.assertNotIn(name, content, f"{name} appears in {path.name}")

    def test_worker_exception_does_not_persist_secret(self):
        database = self.app.extensions["database"]
        database.upsert_tenant("worker-test-tenant", "worker-test-user")
        database.save_session("worker-test-session", "worker-test-tenant", "dark")
        database.save_live_source("worker-test-source", "worker-test-tenant", "worker-test-session",
                                  "tiktok", "worker-test-account", "worker-test-user", "starting")
        secret = "private-worker-test-token"
        with patch("interarcade.worker.service.TikTokWorker", side_effect=RuntimeError(secret)):
            WorkerService(SecurityConfig).run_once()
        source = database.live_source("worker-test-source")
        self.assertEqual(source["last_error"], "RuntimeError")
        self.assertNotIn(secret, str(database.recent_errors()))


if __name__ == "__main__":
    unittest.main()
