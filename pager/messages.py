"""The Telegram texts, in skim order: what, when, verdict and action, then the detail."""
from .clock import duration, parse_time, when


def fire_message(row, at=None):
    """🚨 name, 🕒 when, then the stored page text (verdict + 🔎 findings), then any detail."""
    lines = [
        f"🚨 {row['name'] or 'Incident'}",
        f"🕒 {when(row['started_at'], at)}",
        "",
        row["triage"],
    ]
    extra = detail(row)
    if extra:
        lines += ["", *extra]
    return "\n".join(lines)


def detail(row):
    """The monitor's own text only when Claude couldn't read it for us; the link always."""
    found = []

    triage_failed = (row["triage"] or "").startswith("(triage failed")
    cause = (row["cause"] or "").strip()
    if triage_failed and cause:
        found.append(f"Monitor: {cause[:400]}")

    if row["url"]:
        found.append(row["url"])

    return found


def resolved_message(row):
    """✅ name, then '21:09 → 21:21, 12 min'."""
    start, end = parse_time(row["started_at"]), parse_time(row["resolved_at"])

    if start and end:
        span = f"{start:%H:%M} → {end:%H:%M}, {duration((end - start).total_seconds())}"
    else:
        span = f"started {row['started_at']}"

    return f"✅ Resolved: {row['name'] or 'Incident'}\n🕒 {span}"
