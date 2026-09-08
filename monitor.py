"""
Venue program-page monitor.

Fetches one or more venue "program" pages, extracts the list of currently
listed events (by their unique event-page URL), compares it against the
state saved from the last run, and sends a notification for anything new.

Add more venues later by adding entries to VENUES below — no other code
needs to change as long as the venue's event links follow a simple
"link containing MARKER text" pattern, which covers most WordPress-style
venue sites (Forum Karlín, and many others use this same layout).
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

STATE_FILE = "state.json"

# ntfy.sh needs no account: pick a hard-to-guess topic name and subscribe
# to it in the ntfy app (iOS/Android) or at https://ntfy.sh/<topic> in a
# browser. Treat the topic name like a shared secret — anyone who knows
# it can read your notifications, since public ntfy.sh topics aren't
# access-controlled.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "kxtof_forum67_karlin_new"

VENUES = [
    {
        "name": "Forum Karlín",
        "url": "https://www.forumkarlin.cz/program/",
        # Matches: <a href="https://www.forumkarlin.cz/udalost/some-slug" ... title="Event Name">
        "link_pattern": re.compile(
            r'href="https://www\.forumkarlin\.cz/udalost/([a-z0-9\-]+)"[^>]*title="([^"]*)"'
        ),
        "event_url_template": "https://www.forumkarlin.cz/udalost/{slug}",
    },
    {
        "name": "O2 universum",
        # Same page also lists O2 arena events (separate entry below) --
        # fetched twice, once per venue, which is one extra request, not
        # worth optimizing away for a once-an-hour check.
        "url": "https://www.o2universum.cz/en/events/",
        "link_pattern": re.compile(
            r'href="https://www\.o2universum\.cz/en/events/([a-z0-9\-]+)/"[^>]*title="([^"]*)"'
        ),
        "event_url_template": "https://www.o2universum.cz/en/events/{slug}/",
    },
    {
        "name": "O2 arena",
        "url": "https://www.o2universum.cz/en/events/",
        "link_pattern": re.compile(
            r'href="https://www\.o2arena\.cz/events/([a-z0-9\-]+)/"[^>]*title="([^"]*)"'
        ),
        "event_url_template": "https://www.o2arena.cz/events/{slug}/",
    },
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_events(html: str, pattern: re.Pattern) -> dict:
    """Return {slug: title} for every event link found on the page."""
    events = {}
    for slug, title in pattern.findall(html):
        title = title.strip()
        if title:
            events[slug] = title
    return events


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def notify(title: str, message: str) -> None:
    if NTFY_TOPIC.endswith("CHANGE-ME"):
        print("[skip notify] NTFY_TOPIC not configured — printing instead:")
        print(title, "-", message)
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title.encode("utf-8"), "Priority": "default"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Notification failed: {e}", file=sys.stderr)


def main() -> None:
    state = load_state()
    changed = False

    for venue in VENUES:
        seen = state.get(venue["name"], {})
        try:
            html = fetch(venue["url"])
        except Exception as e:
            print(f"Failed to fetch {venue['name']}: {e}", file=sys.stderr)
            continue

        current = extract_events(html, venue["link_pattern"])
        new_slugs = set(current) - set(seen)

        for slug in new_slugs:
            title = current[slug]
            event_url = venue["event_url_template"].format(slug=slug)
            print(f"NEW: {venue['name']} — {title} ({event_url})")
            notify(
                title=f"New listing: {venue['name']}",
                message=f"{title}\n{event_url}",
            )
            changed = True

        state[venue["name"]] = current

    # Always update this, even when nothing changed, so the workflow always
    # has something to commit. GitHub auto-disables scheduled workflows on
    # repos that go 60 days without a push -- this keeps the repo "active"
    # even during a stretch with no new listings.
    state["_last_checked"] = datetime.now(timezone.utc).isoformat()

    save_state(state)
    if not changed:
        print("No new events found.")


if __name__ == "__main__":
    main()