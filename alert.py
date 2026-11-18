"""Poll Better Stack for incidents, triage new ones with Claude, ping Telegram. Runs forever.

Env (required): BETTERSTACK_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CLAUDE_CODE_OAUTH_TOKEN
Env (optional): CLAUDE_MODEL (default claude-opus-5-5), ALERT_TZ (default Europe/Amsterdam),
                ALERT_DB (default ./alerts.db), POLL_SECONDS (default 60),
                HEARTBEAT_URL (Better Stack heartbeat, pinged after each good poll),
                BETTERSTACK_LOGS_URL, BETTERSTACK_LOGS_USER, BETTERSTACK_LOGS_PASSWORD, BETTERSTACK_LOGS_TABLE
                  (Better Stack "Connect remotely" query access: enables the auth_audit lookup)
Run: python3 alert.py
Test: python3 -m unittest
"""
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

from pager.betterstack import LOGS_ENV, fetch_incidents
from pager.poll import process
from pager.store import open_db

REQUIRED_ENV = ["BETTERSTACK_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CLAUDE_CODE_OAUTH_TOKEN"]
MAX_WAIT = 600  # seconds between polls while Better Stack or the network is down

log = logging.getLogger("alert")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    check_env()

    db = open_db(os.environ.get("ALERT_DB", str(Path(__file__).with_name("alerts.db"))))
    poll_seconds = int(os.environ.get("POLL_SECONDS", "60"))
    log.info("started, polling every %ss", poll_seconds)

    run_forever(db, poll_seconds, os.environ.get("HEARTBEAT_URL"))


def check_env():
    """Exit when a required setting is missing; warn when the log lookup is only half set up."""
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")

    log_missing = [k for k in LOGS_ENV if not os.environ.get(k)]
    if 0 < len(log_missing) < len(LOGS_ENV):
        log.warning("log lookup off: %s not set", ", ".join(log_missing))


def run_forever(db, poll_seconds, heartbeat):
    failures = 0
    while True:
        try:
            process(db, fetch_incidents())
            failures = 0
            if heartbeat:
                urllib.request.urlopen(heartbeat, timeout=10).close()
        except Exception:
            failures += 1
            log.exception("poll failed (%d in a row)", failures)

        time.sleep(wait_before_next_poll(poll_seconds, failures))


def wait_before_next_poll(poll_seconds, failures):
    """The normal interval, doubling with each failure in a row, up to MAX_WAIT."""
    if not failures:
        return poll_seconds
    return min(poll_seconds * 2 ** min(failures, 4), MAX_WAIT)


if __name__ == "__main__":
    main()
