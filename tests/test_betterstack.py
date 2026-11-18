import os
import unittest
import urllib.parse
from datetime import datetime, timezone
from unittest import mock

from pager import betterstack

ENV = {"BETTERSTACK_LOGS_URL": "logs.example", "BETTERSTACK_LOGS_USER": "u", "BETTERSTACK_LOGS_PASSWORD": "p",
       "BETTERSTACK_LOGS_TABLE": "t1_production"}
SINCE = datetime(2026, 11, 18, 20, 19, tzinfo=timezone.utc)


@mock.patch.dict(os.environ, ENV)
class FetchAuditTest(unittest.TestCase):
    def request(self, match=None):
        with mock.patch.object(betterstack, "http_json", return_value=[]) as http:
            betterstack.fetch_audit(SINCE, match)
        url, headers, body = http.call_args.args
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        return url, {k: v[0] for k, v in query.items()}, body.decode()

    def test_values_travel_as_parameters_never_as_sql(self):
        hostile = "1.2.3.4') OR 1=1 --"
        url, params, sql = self.request(("ip", hostile))
        self.assertTrue(url.startswith("https://logs.example?"))
        self.assertNotIn(hostile, sql)
        self.assertNotIn("1.2.3.4", sql)
        self.assertIn("{next:String}", sql)
        self.assertEqual(params["param_next"], '"ip":"1.2.3.4\') OR 1=1 --",')
        self.assertEqual(params["param_since"], str(int(SINCE.timestamp())))

    def test_exact_value_match(self):
        _, params, _ = self.request(("user", "18"))
        self.assertEqual((params["param_next"], params["param_last"]), ('"user":18,', '"user":18}'))

    def test_without_match_reads_the_failures(self):
        _, params, sql = self.request()
        self.assertIn(betterstack.FAILED, sql)
        self.assertEqual(set(params), {"param_since"})

    @mock.patch.dict(os.environ, {"BETTERSTACK_LOGS_TABLE": "t1_x; DROP TABLE y"})
    def test_odd_table_name_is_refused(self):
        with self.assertRaises(ValueError):
            self.request()


if __name__ == "__main__":
    unittest.main()
