"""Better Stack: incidents from the Uptime API, log lines from the ClickHouse query endpoint."""
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
FAILED = ("position(raw, '\"outcome\":\"ok\"') = 0 AND position(raw, '\"outcome\":\"subscription_locked\"') = 0"
          " AND position(raw, '\"anonymous\":true') = 0")


def fetch_incidents():
    # ponytail: first page only; 50 incidents in 2 days means bigger problems than pagination
    since = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    url = f"https://uptime.betterstack.com/api/v2/incidents?from={since}&per_page=50"
    return http_json(url, {"Authorization": f"Bearer {os.environ['BETTERSTACK_TOKEN']}"})["data"]


def logs_configured():
    return all(os.environ.get(k) for k in LOGS_ENV)


def fetch_audit(since, match=None):
    """auth_audit log lines since `since`, newest first: where `match` = (field, value) holds exactly,
    or, without a match, the failures the security alerts count.

    Every value travels as a ClickHouse query parameter ({name:Type} in the SQL, param_name in the URL),
    never as SQL text. The table name can't be a parameter inside remote()/s3Cluster(); it is operator
    config, not alert input, and is held to a strict shape.
    """
    table = os.environ["BETTERSTACK_LOGS_TABLE"]
    if not re.fullmatch(r"t\d+_[a-z0-9_]+", table):
        raise ValueError("BETTERSTACK_LOGS_TABLE should look like t123456_production")
    params = {"since": int(since.timestamp())}
    if match:
        field, value = match
        v = value if field == "user" else json.dumps(value)  # as the log line writes it: user 1838, ip "1.2.3.4"
        # followed by , or } so user 18 never matches 1838
        params |= {"next": f'"{field}":{v},', "last": f'"{field}":{v}}}'}
        where = "(position(raw, {next:String}) > 0 OR position(raw, {last:String}) > 0)"
    else:
        where = FAILED
    # remote() holds the last ~30 min, s3Cluster the rest.
    sql = f"""SELECT dt, raw FROM (
  SELECT dt, raw FROM remote({table}_logs)
  UNION ALL
  SELECT dt, raw FROM s3Cluster(primary, {table}_s3) WHERE _row_type = 1)
WHERE dt >= toDateTime({{since:UInt32}}, 'UTC') AND position(raw, '"event":"auth_audit"') > 0 AND {where}
ORDER BY dt DESC LIMIT {LOG_LIMIT} FORMAT JSONEachRow"""
    auth = base64.b64encode(f"{os.environ['BETTERSTACK_LOGS_USER']}:{os.environ['BETTERSTACK_LOGS_PASSWORD']}".encode()).decode()
    url = os.environ["BETTERSTACK_LOGS_URL"]
    url = url if "://" in url else f"https://{url}"  # Better Stack shows the bare host
    url += ("&" if "?" in url else "?") + urllib.parse.urlencode({f"param_{k}": v for k, v in params.items()})
    # text/plain: urllib's default form type makes ClickHouse see an empty query
    return http_json(url, {"Authorization": f"Basic {auth}", "Content-Type": "text/plain"}, sql.encode(), ndjson=True)
