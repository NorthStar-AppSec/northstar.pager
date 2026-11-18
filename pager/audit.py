"""Reading auth_audit lines: the LeadBot backend's one-line-per-request audit trail."""
import json
import re

from .clock import parse_time

ID = r"(\d+|[A-Z0-9]{8}|[0-9a-f-]{36})"  # numeric pk, public id, or uuid
ID_IN_PATH = re.compile(rf"/{ID}(?=/|$)")


def audit_lines(rows):
    """(time, request) for each Better Stack row that holds an auth_audit line, oldest first."""
    found = []

    for row in rows:
        request = parse_request(row.get("raw"))
        time = parse_time(f"{row.get('dt')}+00:00")  # Better Stack's dt is UTC

        if request and time:
            found.append((time, request))

    return sorted(found, key=lambda pair: pair[0])


def parse_request(raw):
    """The auth_audit dict inside a log line, whichever way the pipeline left `message`."""
    try:
        message = json.loads(raw).get("message")
        if isinstance(message, str):
            message = json.loads(message)
    except (TypeError, ValueError, AttributeError):
        return None

    if isinstance(message, dict) and message.get("event") == "auth_audit":
        return message
    return None


def actor_of(request):
    """Who made this request: ('user', '1838'), else the API key, else the IP."""
    for field in ("user", "api_key", "ip"):
        if request.get(field):
            return field, str(request[field])
    return None


def was_answered(request):
    """2xx or 3xx: the server let it through, with or without a credential."""
    return 200 <= int(request.get("status") or 0) < 400


def logged_in(request):
    """Answered with an accepted credential."""
    return was_answered(request) and not request.get("anonymous")


def public_page(request):
    """Answered without any credential, like the login form or a redirect to it."""
    return was_answered(request) and bool(request.get("anonymous"))


def response(request):
    """'404', or '401 invalid_token' when the outcome says more than the status."""
    status, outcome = request.get("status"), request.get("outcome")

    if outcome in ("ok", f"http_{status}"):
        return f"{status}"
    return f"{status} {outcome}"


def target(request):
    """'GET /api/organizations/{id}/': ids collapsed, so one endpoint counts once."""
    path = str(request.get("path", "")).split("?")[0]
    return f"{request.get('method')} {ID_IN_PATH.sub('/{id}', path)}"
