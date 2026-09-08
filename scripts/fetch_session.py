"""Download a full Oregon session's action history to ./cache/.

The OData service pages at 5,000 rows, so this walks $skip until a page comes
back empty. One session is ~27k rows / ~7 MB. No API key.

    python scripts/fetch_session.py 2025R1
    python scripts/fetch_session.py 2023R1
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.oregonlegislature.gov/odata/odataservice.svc"
PAGE = 5000
RETRIES = 5
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def get(url: str):
    """The service throws transient 503s under repeated pulls. Back off."""
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read())["value"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            wait = 2 ** attempt
            print(f"  {exc} — retry {attempt+1}/{RETRIES} in {wait}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"giving up after {RETRIES} attempts: {last}")


def fetch_session(session: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{session}.json")
    rows, skip = [], 0
    while True:
        params = {
            "$filter": f"SessionKey eq '{session}'",
            "$format": "json",
            "$top": str(PAGE),
            "$skip": str(skip),
        }
        url = f"{API}/MeasureHistoryActions?" + urllib.parse.urlencode(params)
        page = get(url)
        if not page:
            break
        rows.extend(page)
        print(f"  fetched {len(rows)} rows...", flush=True)
        skip += PAGE
        if len(page) < PAGE:
            break
    with open(out, "w") as f:
        json.dump(rows, f)
    measures = {(r["MeasurePrefix"], r["MeasureNumber"]) for r in rows}
    print(f"{session}: {len(rows)} action rows across {len(measures)} measures -> {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/fetch_session.py <SESSION>   e.g. 2025R1")
    for s in sys.argv[1:]:
        fetch_session(s)
