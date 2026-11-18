"""Times as the reader sees them: local (ALERT_TZ), short, with how long ago."""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("ALERT_TZ") or "Europe/Amsterdam")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(TZ)
    except (TypeError, ValueError):
        return None


def duration(seconds):
    m = max(int(seconds // 60), 0)
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60} min"


def when(iso, at=None):
    """'Tue 18 Nov 17:55 (12 min ago)' in ALERT_TZ."""
    t = parse_time(iso)
    if not t:
        return iso or "unknown time"
    ago = ((at or datetime.now(TZ)) - t).total_seconds()
    return f"{t:%a %d %b %H:%M}" + (f" ({duration(ago)} ago)" if ago >= 60 else "")
