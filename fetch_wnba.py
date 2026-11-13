#!/usr/bin/env python3
"""
HerFixtures — WNBA feed generator
Uses ESPN public API (no key required) to fetch fixtures and write wnba.ics.
"""

from datetime import datetime, timezone, timedelta, date
from icalendar import Calendar, Event

from espn_common import fetch_days, is_placeholder, safe_write_ics

OUTPUT_FILE = "wnba.ics"
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

# 2026 season incl. playoffs/Finals (Game 7 was Oct 31). ESPN rejects date
# ranges since 2026-09-15, so the season is fetched one day at a time
# (cached per run, shared with fetch_wnba_teams.py).
SEASON_START = date(2026, 5, 8)
SEASON_END = date(2026, 11, 5)


def fetch_games():
    games = fetch_days(f"{BASE_URL}/scoreboard", SEASON_START, SEASON_END)
    return [ev for ev in games.values() if not is_placeholder(ev)]


def parse_event(event):
    comp = event["competitions"][0]
    home = next((t for t in comp["competitors"] if t["homeAway"] == "home"), None)
    away = next((t for t in comp["competitors"] if t["homeAway"] == "away"), None)
    if not home or not away:
        return None

    home_name = home["team"]["displayName"] or home["team"].get("name", "")
    away_name = away["team"]["displayName"] or away["team"].get("name", "")

    date_str = event.get("date", "")
    try:
        game_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    status_type = event["status"]["type"]
    status_name = status_type["name"]
    status_desc = status_type["description"]
    status_state = status_type.get("state", "pre")
    completed = status_state == "post"

    score = ""
    if completed:
        score = f" ({away.get('score', '?')}–{home.get('score', '?')})"

    broadcasts = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]

    summary = f"🏀 {away_name} @ {home_name}{score}"

    desc_lines = [
        "WNBA 2026 · Season Game",
        f"{away_name} at {home_name}",
        f"Status: {status_desc}",
    ]
    venue = comp.get("venue", {})
    venue_name = venue.get("fullName", "")
    venue_city = venue.get("address", {}).get("city", "")
    if venue_name:
        desc_lines.append(f"Venue: {venue_name}{', ' + venue_city if venue_city else ''}")
    if broadcasts:
        desc_lines.append(f"TV: {', '.join(broadcasts)}")
    desc_lines.append("\nFixtures by HerFixtures.com — Women's Sports on Your Calendar")

    links = event.get("links", [])
    url = links[0].get("href", "https://herfixtures.com") if links else "https://herfixtures.com"

    return {
        "uid": f"espn-wnba-{event['id']}@herfixtures.com",
        "summary": summary,
        "description": "\n".join(desc_lines),
        "dtstart": game_dt,
        "dtend": game_dt + timedelta(hours=2, minutes=30),
        "url": url,
    }


def build_calendar(events):
    cal = Calendar()
    cal.add("prodid", "-//HerFixtures//WNBA 2026//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "WNBA 2026 — HerFixtures")
    cal.add("x-wr-caldesc", "WNBA 2026 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    now = datetime.now(timezone.utc)
    for ev in events:
        parsed = parse_event(ev)
        if not parsed:
            continue
        event = Event()
        event.add("uid", parsed["uid"])
        event.add("summary", parsed["summary"])
        event.add("description", parsed["description"])
        event.add("dtstart", parsed["dtstart"])
        event.add("dtend", parsed["dtend"])
        event.add("dtstamp", now)
        event.add("url", parsed["url"])
        cal.add_component(event)

    return cal


def main():
    print(f"Fetching WNBA 2026 games from {SEASON_START} to {SEASON_END} (one request per day)...")
    try:
        events = fetch_games()
    except RuntimeError as e:
        print(f"  ⚠️  {e} — keeping existing {OUTPUT_FILE}")
        return
    print(f"  → {len(events)} games fetched")

    if not events:
        print("  ⚠️  No events returned — skipping write to preserve existing file")
        return

    cal = build_calendar(events)
    if safe_write_ics(OUTPUT_FILE, cal.to_ical()):
        print(f"  → {OUTPUT_FILE} written successfully")


if __name__ == "__main__":
    main()
