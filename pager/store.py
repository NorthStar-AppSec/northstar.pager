"""SQLite: every incident we saw, its triage, and whether it was sent."""
import sqlite3

SCHEMA = """CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    name TEXT, url TEXT, cause TEXT,
    started_at TEXT, resolved_at TEXT,
    raw TEXT NOT NULL,
    triage TEXT,
    notified_at TEXT,          -- NULL = Telegram send still pending
    resolved_notified_at TEXT
)"""


def open_db(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(SCHEMA)
    return db


def history_for(db, name, exclude_id):
    rows = db.execute(
        "SELECT started_at, cause, triage FROM alerts WHERE name = ? AND id != ? ORDER BY started_at DESC LIMIT 5",
        (name, exclude_id),
    ).fetchall()
    return "\n".join(f"- {r['started_at']} cause={r['cause']} triage={(r['triage'] or '')[:200]!r}" for r in rows)
