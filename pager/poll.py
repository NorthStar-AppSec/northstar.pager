"""One poll: store new incidents, investigate and triage them, send anything not yet sent."""
import json
import logging

from .clock import now
from .investigate import investigate
from .messages import fire_message, resolved_message
from .store import history_for
from .telegram import send
from .triage import triage

log = logging.getLogger(__name__)


def process(db, incidents, triage_fn=triage, send_fn=send, investigate_fn=investigate):
    """Store new incidents with their findings and verdict, then send whatever is unsent.
    The three *_fn are the outside world, passed in so tests can replace them."""
    for inc in incidents:
        a = inc["attributes"]
        exists = db.execute("SELECT 1 FROM alerts WHERE id = ?", (inc["id"],)).fetchone()
        if not exists:
            if a.get("resolved_at"):
                continue  # resolved before we ever saw it: nothing to page about
            findings = investigate_fn(a)
            try:
                verdict = triage_fn(a, history_for(db, a.get("name"), inc["id"]), findings)
            except Exception as e:  # never let Claude being down swallow the page
                log.exception("triage failed for %s", inc["id"])
                verdict = f"(triage failed: {e})"
            text = f"{verdict}\n\n{findings}" if findings else verdict
            db.execute(
                "INSERT INTO alerts (id, name, url, cause, started_at, raw, triage) VALUES (?,?,?,?,?,?,?)",
                (inc["id"], a.get("name"), a.get("url"), a.get("cause"), a.get("started_at"), json.dumps(a), text),
            )
        elif a.get("resolved_at"):
            db.execute("UPDATE alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL", (a["resolved_at"], inc["id"]))
        db.commit()

    # Outbox: anything unsent (incl. failures from earlier polls) gets retried here.
    for row in db.execute("SELECT * FROM alerts WHERE notified_at IS NULL").fetchall():
        try:
            send_fn(fire_message(row))
            db.execute("UPDATE alerts SET notified_at = ? WHERE id = ?", (now(), row["id"]))
            db.commit()
        except Exception as e:
            log.error("telegram send failed for %s, will retry: %s", row["id"], e)
    for row in db.execute(
        "SELECT * FROM alerts WHERE resolved_at IS NOT NULL AND notified_at IS NOT NULL AND resolved_notified_at IS NULL"
    ).fetchall():
        try:
            send_fn(resolved_message(row))
            db.execute("UPDATE alerts SET resolved_notified_at = ? WHERE id = ?", (now(), row["id"]))
            db.commit()
        except Exception as e:
            log.error("telegram resolve send failed for %s, will retry: %s", row["id"], e)
