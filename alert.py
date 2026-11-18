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
log = logging.getLogger("alert")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")
    poll = int(os.environ.get("POLL_SECONDS", "60"))
    heartbeat = os.environ.get("HEARTBEAT_URL")
    db = open_db(os.environ.get("ALERT_DB", str(Path(__file__).with_name("alerts.db"))))
    log_missing = [k for k in LOGS_ENV if not os.environ.get(k)]
    if 0 < len(log_missing) < len(LOGS_ENV):
        log.warning("log lookup off: %s not set", ", ".join(log_missing))
    log.info("started, polling every %ss", poll)

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
        # back off up to 10 min while Better Stack / network is down
        time.sleep(min(poll * 2 ** min(failures, 4), 600) if failures else poll)


if __name__ == "__main__":
    main()
