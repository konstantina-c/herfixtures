#!/usr/bin/env python3
"""
HerFixtures — NWSL feed generator
Uses ESPN public API (no key required) to fetch fixtures and write nwsl.ics.
"""

import requests
from datetime import datetime, timezone, timedelta, date
from icalendar import Calendar, Event

OUTPUT_FILE = "nwsl.ics"
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.nwsl"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TODAY = datetime.now(timezone.utc).date()
SEASON_START = date(2026, 3, 13)
DATE_TO = TODAY + timedelta(days=60)


def fetch_games():
    session = requests.Session()
    session.headers.update(HEADERS)
    games = {}

    # Future first: one wide call from today to DATE_TO (may lack scores)
    r = session.get(
        f"{BASE_URL}/scoreboard",
        params={"dates": f"{TODAY.strftime('%Y%m%d')}-{DATE_TO.strftime('%Y%m%d')}", "limit": 200},
        timeout=10,
    )
    r.raise_for_status()
    for event in r.json().get("events", []):
        games[event["id"]] = event

    # Past last: week by week from season start to yesterday — overwrites future
    # entries for any game that has since completed, ensuring scores are present
    yesterday = TODAY - timedelta(days=1)
    current = SEASON_START
    while current <= yesterday:
        week_end = min(current + timedelta(days=6), yesterday)
        r = session.get(
            f"{BASE_URL}/scoreboard",
            params={"dates": f"{current.strftime('%Y%m%d')}-{week_end.strftime('%Y%m%d')}", "limit": 50},
            timeout=10,
        )
        r.raise_for_status()
        for event in r.json().get("events", []):
            games[event["id"]] = event
        current += timedelta(days=7)

    return list(games.values())


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
    status_desc = status_type["description"]
    status_state = status_type.get("state", "pre")
    completed = status_state == "post"

    score = ""
    if completed:
        score = f" ({away.get('score', '?')}–{home.get('score', '?')})"

    broadcasts = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]

    summary = f"⚽ {away_name} @ {home_name}{score}"

    desc_lines = [
        "NWSL 2026 · Season Game",
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
        "uid": f"espn-nwsl-{event['id']}@herfixtures.com",
        "summary": summary,
        "description": "\n".join(desc_lines),
        "dtstart": game_dt,
        "dtend": game_dt + timedelta(hours=2),
        "url": url,
    }


def build_calendar(events):
    cal = Calendar()
    cal.add("prodid", "-//HerFixtures//NWSL 2026//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "NWSL 2026 — HerFixtures")
    cal.add("x-wr-caldesc", "NWSL 2026 fixtures. Updated automatically by HerFixtures.com")
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
    print(f"Fetching NWSL 2026 games from {SEASON_START} to {DATE_TO}...")
    events = fetch_games()
    print(f"  → {len(events)} games fetched")

    cal = build_calendar(events)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())

    print(f"  → {OUTPUT_FILE} written successfully")


if __name__ == "__main__":
    main()
