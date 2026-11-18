"""The 🔎 block: what one subject did, in the order a reader decides on it.

    🔎 Logs for IP 152.32.213.37
    ⚪ Stopped · last request 21:45
    418 requests since 21:42 · 0 logged in · 114 public pages, no credential
    Responses: 304× 404; 57× 200; 57× 302
    Most hit: GET /backoffice/login/ (57); GET /backoffice/ (57); GET /api/ (12)
    Agent: Mozilla/5.0 … (36)
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from .audit import actor_of, audit_lines, logged_in, public_page, response, target
from .betterstack import LOG_LIMIT
from .clock import TZ

ACTIVE = timedelta(minutes=5)  # ponytail: log forwarding lags ~1 min; quiet for 5 = stopped

NAME = {"user": "user", "api_key": "API key", "ip": "IP", "org_id": "org", "partner_id": "partner", "leadbot_id": "leadbot"}

# The other sides of the same requests: who else, from where, against which tenant.
RELATED = {"user": "Users", "api_key": "API keys", "ip": "IPs", "org_id": "Orgs", "partner_id": "Partners"}


def summarize(rows, field, value, since, at=None, named=True):
    """One 🔎 block for the subject (field, value), from the log rows fetched for it."""
    hits = [(time, r) for time, r in audit_lines(rows) if str(r.get(field)) == value]
    if not hits:
        return f"🔎 Logs: no auth_audit lines for {NAME[field]} {value} since {clock_time(since)}"

    times = [time for time, _ in hits]
    requests = [r for _, r in hits]
    truncated = len(rows) >= LOG_LIMIT

    lines = [
        heading(field, value, named),
        activity(last=times[-1], at=at or datetime.now(timezone.utc)),
        totals(requests, since=times[0], truncated=truncated),
        *warnings(requests),
        "Responses: " + most_common(map(response, requests), 4, "{n}× {item}"),
        "Most hit: " + most_common(map(target, requests), 3),
        *related(requests, field),
        "Agent: " + most_common((r.get("user_agent") or "(none)" for r in requests), 2),
    ]
    return "\n".join(lines)


def heading(field, value, named):
    suffix = "" if named else " (top failing actor in the logs)"
    return f"🔎 Logs for {NAME[field]} {value}{suffix}"


def activity(last, at):
    state = "🔴 Still active" if at - last < ACTIVE else "⚪ Stopped"
    return f"{state} · last request {clock_time(last)}"


def totals(requests, since, truncated):
    """'418 requests since 21:42 · 0 logged in · 114 public pages, no credential'"""
    count = f"{len(requests)}{'+' if truncated else ''}"
    logins = sum(map(logged_in, requests))
    public = sum(map(public_page, requests))

    line = f"{count} requests since {clock_time(since)} · "
    line += f"⚠️ {logins} LOGGED IN" if logins else "0 logged in"
    if public:
        line += f" · {public} public pages, no credential"
    return line


def warnings(requests):
    """The lines that mean act now: what got through, and staff powers used."""
    found = []

    got_through = [r for r in requests if logged_in(r)]
    if got_through:
        found.append("Got through: " + most_common(map(target, got_through), 3))

    overrides = [r for r in requests if r.get("access_via")]
    if overrides:
        found.append("⚠️ Staff override used: " + most_common(map(target, overrides), 2))

    return found


def related(requests, field):
    """'IPs: 9.9.9.9 (5)', 'Orgs: …': every other side of these requests, except the subject's own."""
    found = []

    for other, label in RELATED.items():
        values = [str(r[other]) for r in requests if r.get(other)]
        if other != field and values:
            found.append(f"{label}: {most_common(values, 3)}")

    return found


def top_actors(rows, n):
    """The n actors with the most lines in these rows: [('user', '1838'), ('ip', '1.2.3.4')]."""
    actors = Counter(actor_of(r) for _, r in audit_lines(rows))
    actors.pop(None, None)
    return [actor for actor, _ in actors.most_common(n)]


def most_common(items, n, fmt="{item} ({n})"):
    """'a (3); b (1)': the n most common items, each cut to 60 characters."""
    counted = Counter(items).most_common(n)
    return "; ".join(fmt.format(item=str(item)[:60], n=count) for item, count in counted)


def clock_time(t):
    return f"{t.astimezone(TZ):%H:%M}"
