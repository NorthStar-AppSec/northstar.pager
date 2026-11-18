import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from pager.investigate import investigate, named_subjects
from pager.summary import summarize
from pager.betterstack import LOGS_ENV
from tests.helpers import audit

AT = datetime(2026, 11, 18, 20, 45, tzinfo=timezone.utc)
SINCE = AT - timedelta(minutes=30)
# five failed logins, one real login, a different IP with the same prefix, a line that is not auth_audit
ROWS = [audit("20:30:00", "1.2.3.4", 401, "/api/auth/", "invalid_token") for _ in range(5)] + [
    audit("20:44:00", "1.2.3.4", 200, "/api/organizations/1945/", "ok", 1838),
    audit("20:44:30", "1.2.3.45", 200, "/api/x/", "ok"),
    {"dt": "2026-11-18 20:44:00", "raw": '{"message": "GET /api/ 200 1.2.3.4"}'},
]
# a user probing other tenants, then using a staff override
PROBE = [audit("20:40:00", "9.9.9.9", 404, f"/api/organizations/ORG0000{i}/", "org_denied", 1838, org_id=f"ORG0000{i}")
         for i in range(4)] + [audit("20:41:00", "9.9.9.9", 200, "/mothership/", "ok", 1838, access_via="staff_override")]


class FindingsTest(unittest.TestCase):
    def test_active_ip_that_logged_in(self):
        f = summarize(ROWS, "ip", "1.2.3.4", SINCE, AT)
        self.assertTrue(f.startswith("🔎 Logs for IP 1.2.3.4\n"), f)
        for part in ("Still active", "6 requests", "1 LOGGED IN", "GET /api/organizations/{id}/ (1)",
                     "Users: 1838 (1)", "5× 401 invalid_token"):
            self.assertIn(part, f)

    def test_stopped_ip_that_got_nowhere(self):
        f = summarize(ROWS[:5], "ip", "1.2.3.4", SINCE, AT)
        self.assertIn("Stopped", f)
        self.assertIn("0 logged in", f)
        self.assertNotIn("Got through", f)
        self.assertNotIn("Users", f)

    def test_public_pages_are_not_a_login(self):
        # the scanner of 18 Nov: login page and redirect, no credential
        page = [audit("20:44:00", "1.2.3.4", 200, "/backoffice/login/", "ok", anonymous=True)] * 3
        f = summarize(ROWS[:5] + page, "ip", "1.2.3.4", SINCE, AT)
        self.assertIn("0 logged in · 3 public pages, no credential", f)
        self.assertNotIn("Got through", f)

    def test_nothing_found(self):
        self.assertIn("no auth_audit lines for user 7", summarize([], "user", "7", AT, AT))

    def test_privilege_probing_user(self):
        f = summarize(PROBE, "user", "1838", SINCE, AT, named=False)
        for part in ("user 1838 (top failing actor", "4× 404 org_denied", "IPs: 9.9.9.9 (5)",
                     "Orgs: ORG00000 (1)", "Staff override used: GET /mothership/"):
            self.assertIn(part, f)


class SubjectsTest(unittest.TestCase):
    def test_first_of_each_kind_actors_first_at_most_two(self):
        self.assertEqual(named_subjects("Client IP 152.32.213.37 got 212; seen 130.110.17.77"), [("ip", "152.32.213.37")])
        self.assertEqual(named_subjects("User #1838 hit org MZQSX27V from 1.2.3.4"), [("user", "1838"), ("ip", "1.2.3.4")])
        self.assertEqual(named_subjects('"org_id":"MZQSX27V" by los_ab12cd34'),
                         [("api_key", "los_ab12cd34"), ("org_id", "MZQSX27V")])

    def test_names_nobody(self):
        self.assertEqual(named_subjects("Status 999.1.1.1 502, user agent curl, LeadBot backend"), [])


@mock.patch.dict(os.environ, {k: "x" for k in LOGS_ENV})
class InvestigateTest(unittest.TestCase):
    def setUp(self):
        self.queries = []

    def fetch(self, since, match=None):
        self.queries.append((since, match))
        return ROWS + PROBE

    def test_named_ip_is_looked_up_once_from_15_min_before(self):
        a = {"name": "4xx burst", "cause": "IP 1.2.3.4 got 212", "started_at": "2026-11-18T20:34:00Z"}
        self.assertTrue(investigate(a, self.fetch, AT).startswith("🔎 Logs for IP 1.2.3.4\n"))
        self.assertEqual(self.queries, [(datetime(2026, 11, 18, 20, 19, tzinfo=timezone.utc), ("ip", "1.2.3.4"))])

    def test_security_alert_naming_nobody_finds_top_actors(self):
        f = investigate({"name": "Tenant-boundary probing", "cause": "org_denied > 0"}, self.fetch, AT)
        # first the failures, then each top actor by its own match
        self.assertEqual([m for _, m in self.queries], [None, ("user", "1838"), ("ip", "1.2.3.4")])
        self.assertTrue(f.startswith("🔎 Logs for user 1838 (top failing"), f)
        self.assertIn("🔎 Logs for IP 1.2.3.4 (top failing", f)

    def test_broken_lookup_still_reports(self):
        with self.assertLogs("pager.investigate", "ERROR"):
            f = investigate({"cause": "4xx burst from IP 1.2.3.4"}, lambda since, match=None: 1 / 0, AT)
        self.assertTrue(f.startswith("🔎 Log lookup failed"))

    def test_non_security_alert_is_left_alone(self):
        # even when it mentions an IP: a host being down is not an auth question
        self.assertEqual(investigate({"cause": "Status 502"}, lambda since, match=None: 1 / 0, AT), "")
        self.assertEqual(investigate({"cause": "Timeout on 10.0.0.1"}, lambda since, match=None: 1 / 0, AT), "")

    @mock.patch.dict(os.environ, {"BETTERSTACK_LOGS_USER": ""})
    def test_off_unless_fully_configured(self):
        self.assertEqual(investigate({"cause": "4xx burst from IP 1.2.3.4"}, lambda since, match=None: 1 / 0, AT), "")


if __name__ == "__main__":
    unittest.main()
