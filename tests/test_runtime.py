import tempfile
import unittest
from pathlib import Path

from interarcade.database import Database
from interarcade.games.marble import MarbleConfig, apply_event


class RuntimePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "runtime.sqlite"
        self.db = Database(f"sqlite:///{self.db_path}")
        self.db.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_persists_runtime_entities_and_is_idempotent_for_events(self):
        self.assertTrue(self.db.ping())
        self.db.upsert_tenant("tenant", "creator")
        self.db.upsert_user("owner:tenant", "tenant", "creator")
        self.db.upsert_license("license:tenant", "tenant", "KEY", ["slot"])
        self.assertEqual(self.db.license_for("tenant", "KEY")["games"], ["slot"])
        self.db.save_session("session", "tenant", "slot")
        self.db.save_listener("tenant", "creator", "session", "starting")
        self.assertEqual(self.db.listeners()[0]["status"], "starting")
        event = {
            "event_id": "event-1",
            "tenant_id": "tenant",
            "session_id": "session",
            "type": "gift",
            "payload": {"gift": "Rose", "count": 1},
        }
        self.assertEqual(self.db.record_event(event), 1)
        self.assertEqual(self.db.record_event(event), 0)

    def test_worker_heartbeat_and_session_summary_recover_after_stale_state(self):
        self.assertFalse(self.db.worker_heartbeat(15)["ok"])
        self.db.heartbeat_worker("worker-test", 123)
        heartbeat = self.db.worker_heartbeat(15)
        self.assertTrue(heartbeat["ok"])
        self.db.save_session("session", "tenant", "slot")
        self.assertEqual(self.db.session_summary(), {"active": 1})

    def test_marble_round_is_server_authoritative_and_duplicate_safe(self):
        self.db.upsert_tenant("tenant", "creator")
        self.db.save_session("marble-session", "tenant", "marble")
        config = MarbleConfig(gift_target=2, like_target=100).to_dict()
        self.db.start_marble_round("round-1", "marble-session", config)
        event = {
            "event_id": "marble-event-1", "tenant_id": "tenant", "session_id": "marble-session",
            "type": "gift", "actor": "viewer", "payload": {"gift": "Rose", "count": 2},
        }
        accepted, finished = self.db.apply_marble_event(event, config)
        self.assertTrue(accepted)
        self.assertEqual(finished["gift_score"], 2)
        self.assertEqual(finished["status"], "finished")
        accepted, duplicate = self.db.apply_marble_event(event, config)
        self.assertFalse(accepted)
        self.assertEqual(duplicate["gift_score"], 2)
        self.assertEqual(duplicate["winner"], "GIFTS")
        self.assertEqual(apply_event(finished, event, MarbleConfig.from_mapping(config)), finished)
        self.db.save_session("marble-session-reset", "tenant", "marble")
        self.db.start_marble_round("round-reset-1", "marble-session-reset", config)
        second = self.db.start_marble_round("round-reset-2", "marble-session-reset", config, reset=True)
        self.assertEqual(second["round_number"], 2)
        self.assertEqual(self.db.fetchone("SELECT status FROM marble_rounds WHERE id = ?", ("round-reset-1",))["status"], "ended")

if __name__ == "__main__":
    unittest.main()
