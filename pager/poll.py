"""One poll: store new incidents with their page text, then send whatever is still unsent.

The *_fn arguments are the outside world (Claude, the logs, Telegram), passed in so tests can replace them.
"""
import logging

from . import store
from .investigate import investigate
from .messages import fire_message, resolved_message
from .telegram import send
from .triage import triage

log = logging.getLogger(__name__)


def process(db, incidents, triage_fn=triage, send_fn=send, investigate_fn=investigate):
    for incident in incidents:
        record(db, incident, triage_fn, investigate_fn)

    send_new_alerts(db, send_fn)
    send_resolutions(db, send_fn)


def record(db, incident, triage_fn, investigate_fn):
    """Remember a new open incident with its page text; note when a known one resolves."""
    incident_id, attrs = incident["id"], incident["attributes"]
    resolved_at = attrs.get("resolved_at")

    if store.is_known(db, incident_id):
        if resolved_at:
            store.mark_resolved(db, incident_id, resolved_at)
    elif not resolved_at:  # resolved before we ever saw it: nothing to page about
        text = page_text(db, incident_id, attrs, triage_fn, investigate_fn)
        store.add_alert(db, incident_id, attrs, text)


def page_text(db, incident_id, attrs, triage_fn, investigate_fn):
    """Claude's verdict, then the 🔎 log findings it was based on."""
    findings = investigate_fn(attrs)
    history = store.history_for(db, attrs.get("name"), incident_id)
    verdict = safe_triage(triage_fn, attrs, history, findings, incident_id)

    return f"{verdict}\n\n{findings}" if findings else verdict


def safe_triage(triage_fn, attrs, history, findings, incident_id):
    try:
        return triage_fn(attrs, history, findings)
    except Exception as e:  # never let Claude being down swallow the page
        log.exception("triage failed for %s", incident_id)
        return f"(triage failed: {e})"


def send_new_alerts(db, send_fn):
    for row in store.unsent_alerts(db):
        if try_send(send_fn, fire_message(row), row["id"]):
            store.mark_alert_sent(db, row["id"])


def send_resolutions(db, send_fn):
    for row in store.unsent_resolutions(db):
        if try_send(send_fn, resolved_message(row), row["id"]):
            store.mark_resolution_sent(db, row["id"])


def try_send(send_fn, text, incident_id):
    """True when sent. A failure is logged and left in the outbox for the next poll."""
    try:
        send_fn(text)
        return True
    except Exception as e:
        log.error("telegram send failed for %s, will retry: %s", incident_id, e)
        return False
