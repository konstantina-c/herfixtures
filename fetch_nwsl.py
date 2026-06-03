#!/usr/bin/env python3
"""
HerFixtures — NWSL feed generator
Uses ESPN public API (no key required) to fetch fixtures and write nwsl.ics.

Strategy: soccer scoreboard only accepts single dates (no ranges), so past
games are collected from all 16 team schedules; the current/upcoming matchday
comes from the default scoreboard (no date param).
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

OUTPUT_FILE = "nwsl.ics"
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.nwsl"
HEADERS = {"User-Agent": "Mozilla/5.0"}

TEAM_IDS = [
    "21422", "22187", "131562", "15360", "131563", "15364", "17346",
    "20907", "15366", "18206", "15362", "20905", "21423", "15363", "19141", "15365",
]


def fetch_games():
    session = requests.Session()
    session.headers.update(HEADERS)
    games = {}

    # Current/upcoming matchday — default scoreboard returns latest activity
    r = session.get(f"{BASE_URL}/scoreboard", timeout=10)
    r.raise_for_status()
    for event in r.json().get("events", []):
        games[event["id"]] = event

    # Full season history from all 16 team schedules, deduplicated by event ID
    for team_id in TEAM_IDS:
        r = session.get(
            f"{BASE_URL}/teams/{team_id}/schedule",
            params={"season": 2026},
            timeout=10,
        )
        r.raise_for_status()
        for event in r.json().get("events", []):
            games[event["id"]] = event

    return list(games.values())


def _score_str(competitor):
    s = competitor.get("score")
    if s is None or s == "":
        return None
    if isinstance(s, dict):
        return s.get("displayValue")
    return s


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

    # status lives at comp level in team-schedule events; also present there in scoreboard events
    status_type = comp["status"]["type"]
    status_desc = status_type["description"]
    status_state = status_type.get("state", "pre")
    completed = status_state == "post"

    score = ""
    if completed:
        a_score = _score_str(away) or "?"
        h_score = _score_str(home) or "?"
        score = f" ({a_score}–{h_score})"

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
    print("Fetching NWSL 2026 games from ESPN (team schedules + current scoreboard)...")
    events = fetch_games()
    print(f"  → {len(events)} games fetched")

    cal = build_calendar(events)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())

    print(f"  → {OUTPUT_FILE} written successfully")


if __name__ == "__main__":
    main()
