"""The Telegram texts, in skim order: what, when, verdict and action, then the detail."""
from .clock import duration, parse_time, when


def fire_message(row, at=None):
    cause = (row["cause"] or "").strip()
    lines = [
        f"🚨 {row['name'] or 'Incident'}",
        f"🕒 {when(row['started_at'], at)}",
        "",
        row["triage"],
    ]
    # Claude already read the monitor text; repeating it only adds noise (and UTC times)
    failed = (row["triage"] or "").startswith("(triage failed")
    detail = [f"Monitor: {cause[:400]}" if cause and failed else None, row["url"]]
    detail = [d for d in detail if d]
    return "\n".join(lines + ([""] + detail if detail else []))


def resolved_message(row):
    start, end = parse_time(row["started_at"]), parse_time(row["resolved_at"])
    span = f"{start:%H:%M} → {end:%H:%M}, {duration((end - start).total_seconds())}" if start and end else f"started {row['started_at']}"
    return f"✅ Resolved: {row['name'] or 'Incident'}\n🕒 {span}"
