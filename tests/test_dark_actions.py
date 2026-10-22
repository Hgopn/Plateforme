"""Dark action routing and source identity without real live connections."""

import json
import tempfile
import unittest
from pathlib import Path

from interarcade.app import create_app, socketio
from interarcade.config import Config
from interarcade.games.dark_actions import ACTION_DURATIONS_MS


class DarkActionConfig(Config):
    SECRET_KEY = "dark-actions-test-secret"
    SESSION_SECRET = "dark-actions-test-session"
    ADMIN_TOKEN = "dark-actions-test-admin"
    INTERNAL_EVENT_TOKEN = "dark-actions-test-internal"
    ALLOWED_ORIGINS = "http://localhost:5000"
    REQUIRE_WORKER_HEARTBEAT = False
    DEMO_MODE = True
    DEMO_TENANT_ID = "dark-actions-tenant"
    DEMO_USERNAME = "creator"


class DarkActionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        DarkActionConfig.DATABASE_URL = f"sqlite:///{Path(self.temp_dir.name) / 'actions.sqlite'}"
        self.app = create_app(DarkActionConfig)
        self.client = self.app.test_client()
        self.db = self.app.extensions["database"]
        self.tokens = {}

    def tearDown(self):
        self.temp_dir.cleanup()

    def session(self, game_id="dark", start=True):
        response = self.client.post("/api/v1/demo/session", json={"game_id": game_id})
        self.assertEqual(response.status_code, 201)
        session = response.get_json()
        self.tokens[session["session_id"]] = session["token"]
        if game_id == "dark" and start:
            started = self.client.post(
                f"/api/v1/sessions/{session['session_id']}/games/dark/start",
                headers={"Authorization": f"Bearer {session['token']}"},
            )
            self.assertEqual(started.status_code, 201)
        return session

    def action(self, session_id, action_type, platform="test", actor="Alex"):
        return self.client.post("/api/v1/demo/dark/actions", headers={
            "Authorization": f"Bearer {self.tokens[session_id]}"
        }, json={
            "session_id": session_id,
            "action_type": action_type,
            "source_platform": platform,
            "actor_username": actor,
        })

    def test_each_action_has_fixed_duration_and_complete_live_hub_metadata(self):
        session = self.session()
        socket = socketio.test_client(self.app, auth={"token": session["token"]})
        socket.get_received()
        for action_type, duration in ACTION_DURATIONS_MS.items():
            with self.subTest(action_type=action_type):
                response = self.action(session["session_id"], action_type)
                self.assertEqual(response.status_code, 202)
                action = response.get_json()
                self.assertEqual((action["action_type"], action["duration_ms"]), (action_type, duration))
                self.assertTrue({
                    "source_platform", "source_account_id", "source_username", "event_id",
                    "source_event_id", "timestamp", "session_id", "tenant_id", "actor_id",
                    "actor_platform_id", "actor_username",
                } <= set(action))
                self.assertEqual(action["source_platform"], "test")
                self.assertEqual(action["actor_id"], "test:Alex")
                messages = [entry["args"][0] for entry in socket.get_received() if entry["name"] == "ia:action"]
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["event_id"], action["event_id"])
                row = self.db.fetchone("SELECT envelope_json FROM event_outbox WHERE event_id = ?", (action["event_id"],))
                self.assertEqual(json.loads(row["envelope_json"])["payload"]["action_type"], action_type)
        socket.disconnect()

    def test_simulated_platforms_keep_same_name_distinct_and_are_session_isolated(self):
        session = self.session()
        other = self.session()
        socket = socketio.test_client(self.app, auth={"token": session["token"]})
        other_socket = socketio.test_client(self.app, auth={"token": other["token"]})
        socket.get_received()
        other_socket.get_received()
        first = self.action(session["session_id"], "LIGHT_BOOST", "tiktok")
        second = self.action(session["session_id"], "PLAYER_HELP", "twitch")
        self.assertEqual((first.status_code, second.status_code), (202, 202))
        first_action, second_action = first.get_json(), second.get_json()
        self.assertEqual(first_action["actor_username"], second_action["actor_username"])
        self.assertNotEqual(first_action["actor_id"], second_action["actor_id"])
        self.assertNotEqual(first_action["event_id"], second_action["event_id"])
        self.assertEqual({row["status"] for row in self.db.live_sources(session["session_id"])}, {"simulated"})
        self.assertEqual(len(self.db.live_sources(session["session_id"])), 2)
        delivered = [entry["args"][0] for entry in socket.get_received() if entry["name"] == "ia:action"]
        self.assertEqual({item["event_id"] for item in delivered},
                         {first_action["event_id"], second_action["event_id"]})
        self.assertFalse(any(entry["name"] == "ia:action" for entry in other_socket.get_received()))
        token = {"Authorization": f"Bearer {session['token']}"}
        self.client.post(f"/api/v1/sessions/{session['session_id']}/end", headers=token)
        self.assertEqual({row["status"] for row in self.db.live_sources(session["session_id"])}, {"stopped"})
        self.assertEqual(self.action(session["session_id"], "LIGHT_BOOST").status_code, 401)
        socket.disconnect()
        other_socket.disconnect()

    def test_internal_action_ingress_deduplicates_and_rejects_invalid_targets(self):
        session = self.session()
        other = self.session("marble")
        self.action(session["session_id"], "LIGHT_BOOST", "tiktok")
        internal = {"X-InterArcade-Internal-Token": DarkActionConfig.INTERNAL_EVENT_TOKEN}
        event = {
            "tenant_id": DarkActionConfig.DEMO_TENANT_ID,
            "session_id": session["session_id"],
            "source_platform": "tiktok",
            "source_account_id": "demo-tiktok",
            "source_username": "demo-tiktok",
            "event_type": "action",
            "actor_username": "Alex",
            "actor_platform_id": "viewer-99",
            "event_id": "raw-action-1",
            "payload": {"action_type": "REVEAL_MAP"},
        }
        accepted = self.client.post("/api/v1/internal/events", headers=internal, json=event)
        self.assertEqual(accepted.status_code, 202)
        retry = self.client.post("/api/v1/internal/events", headers=internal, json=event)
        self.assertEqual(retry.status_code, 200)
        self.assertFalse(retry.get_json()["accepted"])
        invalid = self.client.post("/api/v1/internal/events", headers=internal,
                                   json={**event, "event_id": "raw-action-2", "payload": {"action_type": "UNKNOWN"}})
        self.assertEqual(invalid.status_code, 400)
        attached = self.client.post(
            f"/api/v1/sessions/{other['session_id']}/sources",
            headers={"Authorization": f"Bearer {DarkActionConfig.ADMIN_TOKEN}"},
            json={
                "source_platform": "tiktok", "source_account_id": "demo-tiktok",
                "source_username": "demo-tiktok", "simulated": True,
            },
        )
        self.assertEqual(attached.status_code, 202)
        wrong_game = self.client.post("/api/v1/internal/events", headers=internal,
                                      json={**event, "session_id": other["session_id"]})
        self.assertEqual(wrong_game.status_code, 409)
        self.assertEqual(wrong_game.get_json()["error"], "action_requires_dark_session")

    def test_dark_without_actions_keeps_normal_movement_and_three_levels(self):
        session = self.session(start=False)
        token = {"Authorization": f"Bearer {session['token']}"}
        base = f"/api/v1/sessions/{session['session_id']}/games/dark"
        start = self.client.post(f"{base}/start", headers=token)
        self.assertEqual(start.status_code, 201)
        self.assertEqual(start.get_json()["state"]["level"], 1)
        move = self.client.post(f"{base}/move", headers=token, json={"direction": "right"})
        self.assertEqual(move.status_code, 200)
        self.assertTrue(move.get_json()["outcome"]["moved"])
        self.assertEqual(self.db.live_sources(session["session_id"]), [])
        self.assertEqual(self.db.fetchone("SELECT COUNT(*) AS count FROM event_outbox")["count"], 0)
        reset = self.client.post(f"{base}/reset", headers=token)
        self.assertEqual(reset.get_json()["state"]["level"], 1)
        self.assertEqual(reset.get_json()["state"]["level_count"], 3)

    def test_simulation_is_restricted_to_active_dark_demo_sessions(self):
        marble = self.session("marble")
        self.assertEqual(self.action(marble["session_id"], "LIGHT_BOOST").status_code, 401)
        dark = self.session()
        self.assertEqual(self.action(dark["session_id"], "INVALID").status_code, 400)
        self.assertEqual(self.client.post("/api/v1/demo/dark/actions", headers={
            "Authorization": f"Bearer {dark['token']}"
        }, json={
            "session_id": dark["session_id"], "action_type": [],
        }).status_code, 400)
        self.assertEqual(self.db.live_sources(dark["session_id"]), [])
        unstarted = self.session(start=False)
        self.assertEqual(self.action(unstarted["session_id"], "LIGHT_BOOST").status_code, 409)
        body = {"session_id": dark["session_id"], "action_type": "LIGHT_BOOST"}
        self.assertEqual(self.client.post("/api/v1/demo/dark/actions", json=body).status_code, 401)
        self.assertEqual(self.client.post(
            "/api/v1/demo/dark/actions",
            headers={"Authorization": f"Bearer {unstarted['token']}"}, json=body,
        ).status_code, 401)


if __name__ == "__main__":
    unittest.main()
