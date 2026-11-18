"""Dig in the auth_audit logs before paging, so the reader can act or dismiss without opening them.

For a security alert: look up who or what it names (user, API key, IP, org, partner, leadbot),
or, when it names nobody, the actors failing most. See summary.py for what each block shows.
"""
import ipaddress
import logging
import re
from datetime import datetime, timedelta

from .audit import ID
from .betterstack import fetch_audit, logs_configured
from .clock import TZ, parse_time
from .summary import summarize, top_actors

log = logging.getLogger(__name__)

# ponytail: keyword guess at "this is a security alert"; widen it when an auth alert slips past
SECURITY_ALERT = re.compile(r"(?i)auth|secur|denied|privilege|escalat|login|token|tenant|staff|admin|4xx|401|403|brute|probe")

# What an alert can name, keyed by the auth_audit field. Actors first: they are who to act on.
SUBJECT_PATTERNS = {
    "user": re.compile(r"(?i:\buser(?:_id)?)\W{0,3}#?(\d+)\b"),
    "api_key": re.compile(r"\b(los_[A-Za-z0-9]{1,8})"),
    "ip": re.compile(r"\b((?:\d{1,3}\.){3}\d{1,3})\b"),
    "org_id": re.compile(rf"(?i:\borg(?:anization)?(?:_id)?)\W{{0,3}}{ID}\b"),
    "partner_id": re.compile(rf"(?i:\bpartner(?:_id)?)\W{{0,3}}{ID}\b"),
    "leadbot_id": re.compile(rf"(?i:\bleadbot(?:_id)?)\W{{0,3}}{ID}\b"),
}

MAX_SUBJECTS = 2  # ponytail: two blocks keep the page readable; the rest is one query away
LOOKBACK = timedelta(minutes=15)  # read from before the incident started, to catch the run-up


def investigate(attrs, fetch=fetch_audit, at=None):
    """The 🔎 blocks for this incident, or "" when there is nothing to look up."""
    text = f"{attrs.get('name')} {attrs.get('cause')}"
    if not logs_configured() or not SECURITY_ALERT.search(text):
        return ""  # a 502 or a slow page has no actor to look for

    since = start_of_window(attrs)
    try:
        return look_up(text, since, fetch, at)
    except Exception as e:  # a broken lookup must not block the page
        log.exception("log lookup failed")
        return f"🔎 Log lookup failed: {e}"[:300]


def look_up(text, since, fetch, at):
    subjects = named_subjects(text)
    named = bool(subjects)
    if not named:
        subjects = top_actors(fetch(since), MAX_SUBJECTS)

    blocks = [summarize(fetch(since, subject), *subject, since, at, named) for subject in subjects]
    return "\n\n".join(blocks)


def start_of_window(attrs):
    started = parse_time(attrs.get("started_at")) or datetime.now(TZ)
    return started - LOOKBACK


def named_subjects(text):
    """[(field, value)] for what the alert names: the first of each kind, actors first, at most two."""
    # ponytail: first of each kind only; monitor descriptions list the culprit before older ones
    found = []

    for field, pattern in SUBJECT_PATTERNS.items():
        value = first_match(field, pattern, text or "")
        if value:
            found.append((field, value))

    return found[:MAX_SUBJECTS]


def first_match(field, pattern, text):
    for value in pattern.findall(text):
        if field != "ip" or is_ip(value):
            return value
    return None


def is_ip(text):
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False
