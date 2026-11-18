import unittest
from datetime import datetime, timezone

from pager.messages import fire_message, resolved_message

ROW = {"name": "API", "started_at": "2026-11-18T16:55:00Z", "resolved_at": "2026-11-18T17:20:00Z",
       "triage": "P2 · thing\n→ do x", "cause": "Status 502", "url": None}


class MessagesTest(unittest.TestCase):
    def test_skim_order_name_time_verdict(self):
        lines = fire_message(ROW, at=datetime(2026, 11, 18, 17, 7, tzinfo=timezone.utc)).splitlines()
        self.assertEqual(lines[0], "🚨 API")
        self.assertTrue(lines[1].startswith("🕒 ") and "(12 min ago)" in lines[1], lines)
        self.assertTrue(lines[3].startswith("P2"))

    def test_monitor_text_only_when_triage_failed(self):
        self.assertNotIn("Monitor", fire_message(ROW))
        self.assertTrue(fire_message({**ROW, "triage": "(triage failed: x)"}).endswith("Monitor: Status 502"))

    def test_resolved_shows_the_span(self):
        msg = resolved_message(ROW)
        self.assertIn("→", msg)
        self.assertIn("25 min", msg)


if __name__ == "__main__":
    unittest.main()
