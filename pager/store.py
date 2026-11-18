"""SQLite: every incident we saw, the text we paged, and whether it was sent.

A row with notified_at NULL is an outbox entry: it is retried every poll until Telegram takes it.
"""
import json
import sqlite3

from .clock import now

SCHEMA = """CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    name TEXT, url TEXT, cause TEXT,
    started_at TEXT, resolved_at TEXT,
    raw TEXT NOT NULL,
    triage TEXT,                -- the page text: verdict, then the 🔎 findings
    notified_at TEXT,           -- NULL = Telegram send still pending
    resolved_notified_at TEXT
)"""


def open_db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(SCHEMA)
    return db


# --- incidents


def is_known(db, incident_id):
    return db.execute("SELECT 1 FROM alerts WHERE id = ?", (incident_id,)).fetchone() is not None


def add_alert(db, incident_id, attrs, text):
    db.execute(
        "INSERT INTO alerts (id, name, url, cause, started_at, raw, triage) VALUES (?,?,?,?,?,?,?)",
        (incident_id, attrs.get("name"), attrs.get("url"), attrs.get("cause"), attrs.get("started_at"),
         json.dumps(attrs), text),
    )
    db.commit()


def mark_resolved(db, incident_id, resolved_at):
    db.execute("UPDATE alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL", (resolved_at, incident_id))
    db.commit()


def history_for(db, name, exclude_id):
    """The last five incidents of this monitor, one line each, for Claude to spot repeats."""
    rows = db.execute(
        "SELECT started_at, cause, triage FROM alerts WHERE name = ? AND id != ? ORDER BY started_at DESC LIMIT 5",
        (name, exclude_id),
    ).fetchall()
    return "\n".join(f"- {r['started_at']} cause={r['cause']} triage={(r['triage'] or '')[:200]!r}" for r in rows)


# --- outbox


def unsent_alerts(db):
    return db.execute("SELECT * FROM alerts WHERE notified_at IS NULL").fetchall()


def unsent_resolutions(db):
    """Resolved incidents whose alert went out but whose ✅ did not yet."""
    return db.execute(
        "SELECT * FROM alerts WHERE resolved_at IS NOT NULL AND notified_at IS NOT NULL AND resolved_notified_at IS NULL"
    ).fetchall()


def mark_alert_sent(db, incident_id):
    db.execute("UPDATE alerts SET notified_at = ? WHERE id = ?", (now(), incident_id))
    db.commit()


def mark_resolution_sent(db, incident_id):
    db.execute("UPDATE alerts SET resolved_notified_at = ? WHERE id = ?", (now(), incident_id))
    db.commit()
