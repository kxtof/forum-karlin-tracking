"""
Cinema City "new Dune screening" watcher — Praha Flora, 70mm/IMAX.

The booking page (cinemacity.cz/cinemas/flora/1052#/buy-tickets-by-cinema...)
is a client-rendered SPA -- the URL fragment after # is a JS route, not
something a static fetch will ever see content for. So this doesn't scrape
HTML at all: it calls Cinema City's own public JSON API, the same one the
booking widget itself calls. No key or login required.

Deliberately a separate script/state file from monitor.py: different site,
different data shape (an API, not HTML links), different failure modes.
Keeping them apart means a change to one can't silently break or get
confused with the other.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

STATE_FILE = "dune_state.json"

SITE_ID = "10101"  # cinemacity.cz Czech tenant
BASE = f"https://www.cinemacity.cz/cz/data-api-service/v1/quickbook/{SITE_ID}"
LANG = "cs_CZ"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

CINEMA_ID = os.environ.get("CINEMA_ID", "1052")  # Praha Flora
FILM_PATTERN = os.environ.get("FILM_PATTERN", "duna").lower()
# "70-mm" is the attribute Flora's true 70mm/IMAX VOLVO hall carries on its
# screenings -- matches the "filtered=70-mm" in the URL you gave.
REQUIRED_ATTR = os.environ.get("REQUIRED_ATTR", "70-mm")
HORIZON_DAYS = int(os.environ.get("HORIZON_DAYS", "180"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "0.25"))

# Falls back to the same topic as the venue monitor if you don't set a
# separate one -- set NTFY_TOPIC_DUNE if you'd rather keep them apart.
NTFY_TOPIC = (
    os.environ.get("NTFY_TOPIC_DUNE")
    or os.environ.get("NTFY_TOPIC")
    or "kxtof_dune_flora_alerts"
)


def api(path: str) -> dict:
    """GET against the data-api-service, with retries. Returns the "body" dict."""
    url = f"{BASE}{path}"
    last_err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))["body"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2**attempt)
    raise RuntimeError(f"Cinema City API failed after 4 attempts: {url}\n{last_err}")


def horizon() -> str:
    return (date.today() + timedelta(days=HORIZON_DAYS)).isoformat()


def relevant_dates() -> list:
    """Dates that actually have a matching-attribute screening -- one request,
    much cheaper than probing every day in the horizon individually."""
    body = api(f"/dates/in-cinema/{CINEMA_ID}/until/{horizon()}?attr={REQUIRED_ATTR}&lang={LANG}")
    return body.get("dates", [])


def screenings_on(day: str) -> dict:
    """Return {event_id: record} for screenings on this date matching both
    the film-name pattern and the required attribute."""
    time.sleep(REQUEST_DELAY)
    body = api(f"/film-events/in-cinema/{CINEMA_ID}/at-date/{day}?attr={REQUIRED_ATTR}&lang={LANG}")
    films = {f["id"]: f for f in body.get("films", [])}
    found = {}
    for e in body.get("events", []):
        film = films.get(e.get("filmId"), {})
        if FILM_PATTERN not in film.get("name", "").lower():
            continue
        # attr= on the API is applied server-side but ORs multiple values
        # loosely, so double-check locally that this specific screening
        # actually carries the attribute rather than trusting the filter.
        if REQUIRED_ATTR and REQUIRED_ATTR not in (e.get("attributeIds") or []):
            continue
        found[e["id"]] = {
            "film": film.get("name", e.get("filmId")),
            "datetime": e.get("eventDateTime"),
            "auditorium": e.get("auditorium"),
            "soldOut": bool(e.get("soldOut")),
            # bookingLink and bookingRouterLaunchLink both dead-end (a 404,
            # and a self-submitting POST form respectively); this order-page
            # URL is what actually works as a plain GET link.
            "booking": f"https://tickets.cinemacity.cz/order/{e.get('presentationCode') or e['id']}",
        }
    return found


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def notify(title: str, message: str) -> None:
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title.encode("utf-8"), "Priority": "high"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Notification failed: {e}", file=sys.stderr)


def main() -> None:
    state = load_state()
    seen = state.get("events", {})
    current = {}

    try:
        dates = relevant_dates()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return

    for day in dates:
        current.update(screenings_on(day))

    new_ids = set(current) - set(seen)
    for eid in new_ids:
        s = current[eid]
        print(f"NEW SCREENING: {s['film']} — {s['datetime']} ({s['auditorium']})")
        notify(
            title=f"New screening: {s['film']}",
            message=f"{s['datetime']} in {s['auditorium']}\n{s['booking']}",
        )

    state["events"] = current
    state["_last_checked"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    if not new_ids:
        print(f"No new screenings. Currently tracking {len(current)} matching screening(s).")


if __name__ == "__main__":
    main()
