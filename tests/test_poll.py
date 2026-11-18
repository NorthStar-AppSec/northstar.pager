import logging
import unittest

from pager.poll import process
from pager.store import open_db
from tests.helpers import incident


class PollTest(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)  # failures below are expected
        self.db = open_db(":memory:")
        self.sent, self.histories = [], []

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def triage(self, attrs, history, findings=""):
        self.histories.append(history)
        return "P1 because test"

    def run_poll(self, *incidents, triage=None, send=None, investigate=lambda a: ""):
        process(self.db, list(incidents), triage or self.triage, send or self.sent.append, investigate)

    def test_new_incident_is_triaged_and_sent_once(self):
        self.run_poll(incident("1", "API"))
        self.run_poll(incident("1", "API"))
        self.assertEqual(len(self.histories), 1)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("P1 because test", self.sent[0])

    def test_resolution_sends_one_resolved_message(self):
        self.run_poll(incident("1", "API"))
        self.run_poll(incident("1", "API", "2026-01-01T01"))
        self.run_poll(incident("1", "API", "2026-01-01T01"))
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self.sent[1].startswith("✅"))

    def test_already_resolved_on_first_sight_is_ignored(self):
        self.run_poll(incident("9", "Old", "2026-01-01"))
        self.assertEqual(self.sent, [])

    def test_telegram_down_retries_without_triaging_again(self):
        self.run_poll(incident("1", "API"))

        def down(message):
            raise OSError("down")

        self.run_poll(incident("2", "API"), send=down)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("2026-01-01", self.histories[-1])  # history holds the earlier incident
        self.run_poll(incident("2", "API"))
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(len(self.histories), 2)

    def test_triage_crash_still_pages(self):
        self.run_poll(incident("3", "DB"), triage=lambda a, h, f: 1 / 0)
        self.assertIn("triage failed", self.sent[-1])

    def test_findings_go_to_claude_and_under_the_verdict(self):
        got = []
        self.run_poll(incident("4", "API"), triage=lambda a, h, f: got.append(f) or "P3 · noise",
                      investigate=lambda a: "🔎 Logs for x")
        self.assertEqual(got, ["🔎 Logs for x"])
        self.assertEqual(self.sent[-1].split("\n\n")[1:3], ["P3 · noise", "🔎 Logs for x"])


if __name__ == "__main__":
    unittest.main()
