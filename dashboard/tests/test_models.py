import unittest
from datetime import datetime, timezone

from dashboard_server.models import normalize_event, choose_display_status


class ModelTests(unittest.TestCase):
    def test_normalize_event_uses_score_when_status_missing(self):
        event = normalize_event({"score": 0.9}, {"scanning_score_threshold": 0.85})
        self.assertEqual(event["status"], "scanning")
        self.assertEqual(event["score"], 0.9)

    def test_normalize_event_clamps_score(self):
        event = normalize_event({"status": "warning", "score": 5})
        self.assertEqual(event["status"], "warning")
        self.assertEqual(event["score"], 1.0)

    def test_choose_display_status_prefers_scanning(self):
        now = datetime.now(timezone.utc).timestamp()
        events = [
            {"status": "warning", "score": 0.7, "received_at_epoch": now},
            {"status": "scanning", "score": 0.9, "received_at_epoch": now},
        ]
        result = choose_display_status(events, {"hold_seconds": 30})
        self.assertEqual(result["status"], "scanning")

    def test_choose_display_status_uses_latest_status_when_no_recent_hold_match(self):
        old = datetime.now(timezone.utc).timestamp() - 120
        events = [{"status": "scanning", "score": 0.92, "received_at_epoch": old}]
        result = choose_display_status(events, {"hold_seconds": 30})
        self.assertEqual(result["status"], "scanning")


if __name__ == "__main__":
    unittest.main()
