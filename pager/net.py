"""The one HTTP helper every API client here shares."""
import json
import urllib.error
import urllib.request


def http_json(url, headers=None, data=None, ndjson=False):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
            return [json.loads(l) for l in body.splitlines() if l.strip()] if ndjson else json.loads(body)
    except urllib.error.HTTPError as e:
        # surface the API's own reason (Telegram: "Forbidden: bot can't initiate conversation…");
        # never the URL, which holds the Telegram token
        body = e.read().decode(errors="replace")
        try:
            body = json.loads(body).get("description") or body
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from None
