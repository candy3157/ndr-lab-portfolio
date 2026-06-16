import tempfile
import time
import unittest
from pathlib import Path

from dashboard_server.models import normalize_event
from dashboard_server.store import EventStore


class StoreTests(unittest.TestCase):
    def test_insert_and_read_recent_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.sqlite3")
            saved = store.insert_event(normalize_event({"status": "warning", "score": 0.7, "src_ip": "10.0.0.1"}))
            events = store.recent_events(10)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], saved["id"])
            self.assertEqual(events[0]["status"], "warning")
            self.assertEqual(events[0]["src_ip"], "10.0.0.1")

    def test_status_keeps_latest_event_after_hold_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(Path(tmp) / "events.sqlite3", {"hold_seconds": 0.01})
            store.insert_event(normalize_event({"status": "normal", "score": 0.1, "src_ip": "10.0.0.2"}))
            time.sleep(0.02)
            status = store.status()
            self.assertEqual(status["status"], "normal")
            self.assertEqual(status["src_ip"], "10.0.0.2")


if __name__ == "__main__":
    unittest.main()
