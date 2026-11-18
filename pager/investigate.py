"""Dig in the auth_audit logs before paging, so the reader can act or dismiss without opening them.

For a security alert, looks up who or what it names (user, API key, IP, org, partner, leadbot);
if it names nobody, looks up the top failing actors instead. Each summary answers:
still going? did anyone log in? what was hit, by whom, from where?
"""
import ipaddress
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from .betterstack import LOG_LIMIT, fetch_audit, logs_configured
from .clock import TZ, parse_time

log = logging.getLogger(__name__)

# ponytail: keyword guess at "this is a security alert"; widen it when an auth alert slips past
SECURITY_ALERT = re.compile(r"(?i)auth|secur|denied|privilege|escalat|login|token|tenant|staff|admin|4xx|401|403|brute|probe")

ID = r"(\d+|[A-Z0-9]{8}|[0-9a-f-]{36})"  # numeric pk, public id, or uuid
ID_IN_PATH = re.compile(rf"/{ID}(?=/|$)")

# What an alert can name, keyed by the auth_audit field. Actors first: they are who to act on.
SUBJECT_PATTERNS = {
    "user": re.compile(r"(?i:\buser(?:_id)?)\W{0,3}#?(\d+)\b"),
    "api_key": re.compile(r"\b(los_[A-Za-z0-9]{1,8})"),
    "ip": re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})\b"),
    "org_id": re.compile(rf"(?i:\borg(?:anization)?(?:_id)?)\W{{0,3}}{ID}\b"),
    "partner_id": re.compile(rf"(?i:\bpartner(?:_id)?)\W{{0,3}}{ID}\b"),
    "leadbot_id": re.compile(rf"(?i:\bleadbot(?:_id)?)\W{{0,3}}{ID}\b"),
}
NAME = {"user": "user", "api_key": "API key", "ip": "IP", "org_id": "org", "partner_id": "partner", "leadbot_id": "leadbot"}
# The other sides of the same requests, shown under each summary.
RELATED = {"user": "Users", "api_key": "API keys", "ip": "IPs", "org_id": "Orgs", "partner_id": "Partners"}

MAX_SUBJECTS = 2  # ponytail: two blocks keep the page readable; the rest is one query away
LOOKBACK = timedelta(minutes=15)  # before the incident started, to catch the run-up
ACTIVE = timedelta(minutes=5)  # ponytail: log forwarding lags ~1 min; quiet for 5 = stopped


def investigate(attrs, fetch=fetch_audit, at=None):
    """The 🔎 blocks for this incident, or "" when there is nothing to look up."""
    text = f"{attrs.get('name')} {attrs.get('cause')}"
    if not logs_configured() or not SECURITY_ALERT.search(text):
        return ""  # a 502 or a slow page has no actor to look for
    since = (parse_time(attrs.get("started_at")) or datetime.now(TZ)) - LOOKBACK
    try:
        subjects = named_subjects(text)
        named = bool(subjects)
        if not named:
            subjects = top_failing_actors(fetch(since))
        return "\n\n".join(summarize(fetch(since, s), *s, since, at, named) for s in subjects)
    except Exception as e:  # a broken lookup must not block the page
        log.exception("log lookup failed")
        return f"🔎 Log lookup failed: {e}"[:300]


def named_subjects(text):
    """(field, value) for what the alert names: the first of each kind, actors first, at most two."""
    # ponytail: first of each kind only; monitor descriptions list the culprit before older ones
    found = []
    for field, pattern in SUBJECT_PATTERNS.items():
        for value in pattern.findall(text or ""):
            if field == "ip" and not is_ip(value):
                continue
            found.append((field, value))
            break
    return found[:MAX_SUBJECTS]


def top_failing_actors(rows):
    actors = Counter(actor_of(m) for _, m in audit_lines(rows))
    actors.pop(None, None)
    return [actor for actor, _ in actors.most_common(MAX_SUBJECTS)]


def summarize(rows, field, value, since, at=None, named=True):
    """One 🔎 block: what this subject did since `since`."""
    at = at or datetime.now(timezone.utc)
    who = f"{NAME[field]} {value}"
    hits = [(t, m) for t, m in audit_lines(rows) if str(m.get(field)) == value]
    if not hits:
        return f"🔎 Logs: no auth_audit lines for {who} since {local(since)}"
    first, last = hits[0][0], hits[-1][0]
    lines = [m for _, m in hits]

    passed = [m for m in lines if 0 < status(m) < 400]
    logged_in = [m for m in passed if not m.get("anonymous")]  # anonymous 200/302: a public page
    public = len(passed) - len(logged_in)
    overrides = [m for m in lines if m.get("access_via")]
    more = "+" if len(rows) >= LOG_LIMIT else ""

    out = [
        f"🔎 Logs for {who}" + ("" if named else " (top failing actor in the logs)"),
        ("🔴 Still active" if at - last < ACTIVE else "⚪ Stopped") + f" · last request {local(last)}",
        f"{len(lines)}{more} requests since {local(first)} · "
        + (f"⚠️ {len(logged_in)} LOGGED IN" if logged_in else "0 logged in")
        + (f" · {public} public pages, no credential" if public else ""),
    ]
    if logged_in:
        out.append("Got through: " + top(map(path, logged_in), 3))
    if overrides:
        out.append("⚠️ Staff override used: " + top(map(path, overrides), 2))
    out.append("Responses: " + top(map(response, lines), 4, "{n}× {key}"))
    out.append("Most hit: " + top(map(path, lines), 3))
    for other, label in RELATED.items():
        values = [str(m[other]) for m in lines if m.get(other)]
        if other != field and values:
            out.append(f"{label}: {top(values, 3)}")
    out.append("Agent: " + top((m.get("user_agent") or "(none)" for m in lines), 2))
    return "\n".join(out)


# --- reading log lines


def audit_lines(rows):
    """(time, auth_audit dict) for each row that holds one, oldest first."""
    found = []
    for row in rows:
        m, t = audit_message(row.get("raw")), parse_time(f"{row.get('dt')}+00:00")  # dt is UTC
        if m and t:
            found.append((t, m))
    return sorted(found, key=lambda pair: pair[0])


def audit_message(raw):
    """The auth_audit dict inside a log line, whichever way the pipeline left `message`."""
    try:
        msg = json.loads(raw).get("message")
        msg = json.loads(msg) if isinstance(msg, str) else msg
    except (TypeError, ValueError, AttributeError):
        return None
    return msg if isinstance(msg, dict) and msg.get("event") == "auth_audit" else None


def actor_of(m):
    """Who made this request: the user if known, else the API key, else the IP."""
    for field in ("user", "api_key", "ip"):
        if m.get(field):
            return field, str(m[field])
    return None


def status(m):
    return int(m.get("status") or 0)


def response(m):
    """'404', or '401 invalid_token' when the outcome says more than the status."""
    plain = m.get("outcome") in ("ok", f"http_{m.get('status')}")
    return f"{m.get('status')}" if plain else f"{m.get('status')} {m.get('outcome')}"


def path(m):
    """'GET /api/organizations/{id}/': ids collapsed so one target counts once."""
    return f"{m.get('method')} {ID_IN_PATH.sub('/{id}', str(m.get('path', '')).split('?')[0])}"


# --- formatting


def top(items, n, fmt="{key} ({n})"):
    """The n most common items: 'a (3); b (1)'."""
    return "; ".join(fmt.format(key=str(key)[:60], n=count) for key, count in Counter(items).most_common(n))


def local(t):
    return f"{t.astimezone(TZ):%H:%M}"


def is_ip(text):
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False
