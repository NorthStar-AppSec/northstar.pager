import json


def incident(i, name, resolved=None):
    return {"id": i, "attributes": {"name": name, "url": "https://x", "cause": "Timeout",
                                    "started_at": f"2026-01-0{i}", "resolved_at": resolved}}


def audit(dt, ip, status, path, outcome, user=None, **kw):
    """One Better Stack row holding an auth_audit line, as the query endpoint returns it."""
    m = {"event": "auth_audit", "outcome": outcome, "method": "GET", "path": path, "status": status,
         "ip": ip, "user_agent": "curl/8", **({"user": user} if user else {}), **kw}
    return {"dt": f"2026-11-18 {dt}.123456", "raw": json.dumps({"logger": "security.audit", "message": m})}
