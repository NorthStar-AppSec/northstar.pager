"""Better Stack: incidents from the Uptime API, auth_audit lines from the logs query endpoint."""
import base64
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from .net import http_json

LOG_LIMIT = 5000
LOGS_ENV = ["BETTERSTACK_LOGS_URL", "BETTERSTACK_LOGS_USER", "BETTERSTACK_LOGS_PASSWORD", "BETTERSTACK_LOGS_TABLE"]

# The failures the security alerts count (LeadBot docs/LOGGING.md): not ok, not billing, not anonymous scanning.
FAILED = ("position(raw, '\"outcome\":\"ok\"') = 0"
          " AND position(raw, '\"outcome\":\"subscription_locked\"') = 0"
          " AND position(raw, '\"anonymous\":true') = 0")

# A line holding exactly this value: followed by , or } so user 18 never matches user 1838.
EXACT_MATCH = "(position(raw, {next:String}) > 0 OR position(raw, {last:String}) > 0)"


# --- incidents


def fetch_incidents():
    # ponytail: first page only; 50 incidents in 2 days means bigger problems than pagination
    since = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    url = f"https://uptime.betterstack.com/api/v2/incidents?from={since}&per_page=50"
    return http_json(url, {"Authorization": f"Bearer {os.environ['BETTERSTACK_TOKEN']}"})["data"]


# --- logs


def logs_configured():
    return all(os.environ.get(k) for k in LOGS_ENV)


def fetch_audit(since, match=None):
    """auth_audit lines since `since`, newest first: those with `match` = (field, value),
    or, without a match, the failures the security alerts count.

    Values travel as ClickHouse query parameters ({name:Type} in the SQL, param_name in the URL),
    never as SQL text.
    """
    params = {"since": int(since.timestamp())}
    if match:
        params |= exact_match_params(*match)

    sql = audit_sql(log_table(), EXACT_MATCH if match else FAILED)
    return run_query(sql, params)


def exact_match_params(field, value):
    """The two spellings of `"field":value` a log line can hold: mid-object and last in it."""
    written = value if field == "user" else json.dumps(value)  # user 1838, but ip "1.2.3.4"
    return {"next": f'"{field}":{written},', "last": f'"{field}":{written}}}'}


def log_table():
    """The source's table name. It can't be a query parameter inside remote()/s3Cluster();
    it is operator config, not alert input, and is held to a strict shape."""
    table = os.environ["BETTERSTACK_LOGS_TABLE"]
    if not re.fullmatch(r"t\d+_[a-z0-9_]+", table):
        raise ValueError("BETTERSTACK_LOGS_TABLE should look like t123456_production")
    return table


def audit_sql(table, where):
    # remote() holds the last ~30 min, s3Cluster the rest
    return f"""SELECT dt, raw FROM (
  SELECT dt, raw FROM remote({table}_logs)
  UNION ALL
  SELECT dt, raw FROM s3Cluster(primary, {table}_s3) WHERE _row_type = 1)
WHERE dt >= toDateTime({{since:UInt32}}, 'UTC')
  AND position(raw, '"event":"auth_audit"') > 0
  AND {where}
ORDER BY dt DESC LIMIT {LOG_LIMIT} FORMAT JSONEachRow"""


def run_query(sql, params):
    headers = {
        "Authorization": f"Basic {logs_credentials()}",
        "Content-Type": "text/plain",  # urllib's default form type makes ClickHouse see an empty query
    }
    return http_json(query_url(params), headers, sql.encode(), ndjson=True)


def query_url(params):
    url = os.environ["BETTERSTACK_LOGS_URL"]
    if "://" not in url:
        url = f"https://{url}"  # Better Stack shows the bare host

    separator = "&" if "?" in url else "?"
    return url + separator + urllib.parse.urlencode({f"param_{k}": v for k, v in params.items()})


def logs_credentials():
    pair = f"{os.environ['BETTERSTACK_LOGS_USER']}:{os.environ['BETTERSTACK_LOGS_PASSWORD']}"
    return base64.b64encode(pair.encode()).decode()
