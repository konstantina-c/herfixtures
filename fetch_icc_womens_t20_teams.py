#!/usr/bin/env python3
"""
HerFixtures — ICC Women's T20 World Cup 2026 per-team feed generator
Uses ESPN public API (no key required). League slug: cricket/8634.

Fetches all 33 fixtures once, filters in memory per national team.
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

BASE_URL    = "https://site.api.espn.com/apis/site/v2/sports/cricket/8634"
HEADERS     = {"User-Agent": "Mozilla/5.0"}
SEASON_YEAR = 2026

# Team display name (as returned by ESPN) → output file slug
ICC_TEAMS = {
    "Australia":    "icc_womens_t20_australia",
    "Bangladesh":   "icc_womens_t20_bangladesh",
    "England":      "icc_womens_t20_england",
    "India":        "icc_womens_t20_india",
    "Ireland":      "icc_womens_t20_ireland",
    "Netherlands":  "icc_womens_t20_netherlands",
    "New Zealand":  "icc_womens_t20_new_zealand",
    "Pakistan":     "icc_womens_t20_pakistan",
    "Scotland":     "icc_womens_t20_scotland",
    "South Africa": "icc_womens_t20_south_africa",
    "Sri Lanka":    "icc_womens_t20_sri_lanka",
    "West Indies":  "icc_womens_t20_west_indies",
}


def fetch_all_fixtures():
    session = requests.Session()
    session.headers.update(HEADERS)
    games = {}

    try:
        r = session.get(
            f"{BASE_URL}/scoreboard",
            params={"season": SEASON_YEAR, "limit": 100},
            timeout=10,
        )
        r.raise_for_status()
        for event in r.json().get("events", []):
            eid = event.get("id")
            if not eid:
                continue
            games[eid] = event
    except requests.exceptions.HTTPError as e:
        print(f"  ⚠️  Season scoreboard HTTP error, skipping: {e}")

    # Current matchday overwrites — ensures live/today scores are fresh
    try:
        r = session.get(f"{BASE_URL}/scoreboard", timeout=10)
        r.raise_for_status()
        for event in r.json().get("events", []):
            eid = event.get("id")
            if not eid:
                continue
            games[eid] = event
    except requests.exceptions.HTTPError as e:
        print(f"  ⚠️  Current scoreboard HTTP error, skipping: {e}")

    return list(games.values())


def team_in_event(team_name, event):
    comp = event["competitions"][0]
    for competitor in comp["competitors"]:
        display = competitor["team"].get("displayName", "")
        if team_name.lower() in display.lower():
            return True
    return False


def parse_event(event, team_name):
    comp = event["competitions"][0]
    home = next((t for t in comp["competitors"] if t["homeAway"] == "home"), None)
    away = next((t for t in comp["competitors"] if t["homeAway"] == "away"), None)
    if not home or not away:
        return None

    home_name = home["team"]["displayName"] or home["team"].get("name", "")
    away_name = away["team"]["displayName"] or away["team"].get("name", "")

    if "TBA" in home_name and "TBA" in away_name:
        return None

    date_str = event.get("date", "")
    try:
        game_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    status_type  = event["status"]["type"]
    status_desc  = status_type["description"]
    status_state = status_type.get("state", "pre")
    completed    = status_state == "post"

    score = ""
    if completed:
        h_score = home.get("score") or "?"
        a_score = away.get("score") or "?"
        score = f" ({h_score} / {a_score})"

    broadcasts = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]

    summary = f"🏏 {home_name} v {away_name}{score}"

    desc_lines = [
        f"ICC Women's T20 World Cup 2026 · {team_name}",
        f"{home_name} v {away_name}",
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
        "uid":         f"espn-icc-womens-t20-{event['id']}@herfixtures.com",
        "summary":     summary,
        "description": "\n".join(desc_lines),
        "dtstart":     game_dt,
        "dtend":       game_dt + timedelta(hours=4),
        "url":         url,
    }


def build_calendar(events, team_name, slug):
    cal = Calendar()
    cal.add("prodid",  f"-//HerFixtures//ICC Women's T20 WC 2026 {team_name}//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method",  "PUBLISH")
    cal.add("x-wr-calname",  f"{team_name} — ICC Women's T20 WC 2026 — HerFixtures")
    cal.add("x-wr-caldesc",  f"{team_name} ICC Women's T20 World Cup 2026 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    now = datetime.now(timezone.utc)
    count = 0
    for ev in events:
        if not team_in_event(team_name, ev):
            continue
        parsed = parse_event(ev, team_name)
        if not parsed:
            continue
        event = Event()
        event.add("uid",         parsed["uid"])
        event.add("summary",     parsed["summary"])
        event.add("description", parsed["description"])
        event.add("dtstart",     parsed["dtstart"])
        event.add("dtend",       parsed["dtend"])
        event.add("dtstamp",     now)
        event.add("url",         parsed["url"])
        cal.add_component(event)
        count += 1

    return cal, count


def main():
    print("Fetching ICC Women's T20 World Cup 2026 fixtures from ESPN...")
    all_events = fetch_all_fixtures()
    print(f"  → {len(all_events)} raw events fetched")

    if not all_events:
        print("  ⚠️  No events returned — skipping write to preserve existing files")
        return

    print()
    success = 0
    for team_name, slug in ICC_TEAMS.items():
        try:
            cal, count = build_calendar(all_events, team_name, slug)
            output_file = f"{slug}.ics"
            with open(output_file, "wb") as f:
                f.write(cal.to_ical())
            print(f"  ✓ {output_file:50} ({count} fixtures)")
            success += 1
        except Exception as e:
            print(f"  ✗ {team_name}: {e}")

    print()
    print(f"Done — {success}/{len(ICC_TEAMS)} team feeds written.")


if __name__ == "__main__":
    main()
