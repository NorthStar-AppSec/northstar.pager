"""The one HTTP helper every API client here shares."""
import json
import urllib.error
import urllib.request


def http_json(url, headers=None, data=None, ndjson=False):
    """GET (or POST when `data` is given) and parse the JSON reply; ndjson = one document per line."""
    request = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return parse_json(response.read().decode(), ndjson)
    except urllib.error.HTTPError as e:
        # never put the URL in the error: it holds the Telegram token
        raise RuntimeError(f"HTTP {e.code}: {error_reason(e)[:300]}") from None


def parse_json(body, ndjson):
    if ndjson:
        return [json.loads(line) for line in body.splitlines() if line.strip()]
    return json.loads(body)


def error_reason(error):
    """The API's own words, like Telegram's "Forbidden: bot can't initiate conversation"."""
    body = error.read().decode(errors="replace")
    try:
        return json.loads(body).get("description") or body
    except (ValueError, AttributeError):
        return body
