import json
import tempfile
import unittest
from pathlib import Path

from interarcade.database import Database
from interarcade.migrate_licenses import migrate


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

    def test_migrates_legacy_license_file(self):
        source = Path(self.temp_dir.name) / "licenses.json"
        source.write_text(
            json.dumps({"creator": {"key": "KEY", "games": ["slot"]}}),
            encoding="utf-8",
        )
        count = migrate(f"sqlite:///{self.db_path}", str(source))
        self.assertEqual(count, 1)
        self.assertEqual(self.db.license_for("creator", "KEY")["games"], ["slot"])


if __name__ == "__main__":
    unittest.main()
