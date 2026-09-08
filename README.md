# Venue program-page monitor

Checks a venue's event listing page daily and notifies you when a new
event appears, using nothing but a free GitHub Actions cron job — no
agent, no server, no paid service.

## Setup (~5 minutes)

1. **Create a repo** on GitHub (can be private) and push these files to it
   (`monitor.py`, `.github/workflows/check.yml`, this README).

2. **Get a notification channel.** Easiest option, [ntfy.sh](https://ntfy.sh):
   - Pick a topic name only you would guess, e.g. `krystof-fk-alerts-x7q2`.
   - Install the ntfy app (iOS/Android) or open `https://ntfy.sh/<your-topic>`
     in a browser, and subscribe to that topic.
   - In your GitHub repo: **Settings → Secrets and variables → Actions →
     New repository secret**, name it `NTFY_TOPIC`, value = your topic name.
   - That's it — no account, no API key.
   - (Alternative: swap the `notify()` function in `monitor.py` for a
     Telegram bot, Pushover, or email if you'd rather use one of those.)

3. **Turn it on.** The workflow runs automatically once a day (08:00 UTC —
   edit the `cron:` line in `check.yml` to change that). You can also
   trigger it manually any time from the repo's **Actions** tab →
   "Check venue listings" → **Run workflow**.

4. **First run note:** the very first run has no prior state, so
   everything currently listed will look "new" and you'll get one
   notification burst. After that, only genuinely new events trigger a
   notification.

## Adding more venues

Add another entry to the `VENUES` list in `monitor.py`:

```python
{
    "name": "Some Other Venue",
    "url": "https://example.cz/program/",
    "link_pattern": re.compile(r'href="https://example\.cz/event/([a-z0-9\-]+)"[^>]*>\s*([^<]*)</a>'),
},
```

The pattern needs adjusting per site since every venue's HTML is a little
different — send me the page and I can write the matching pattern.

## Why not an agent for this

This page is static, server-rendered HTML — extracting "what's listed"
and diffing it against yesterday is a deterministic string operation,
not something that benefits from a language model's judgment. An agent
would cost more, run slower, and risk misreading the page occasionally
for zero upside here. Where an agent *would* earn its keep: cross-referencing
new listings against your own watchlist of specific artists, filtering by
your buy criteria, or writing results into your ticket tracker — that's
judgment work, not diffing.
