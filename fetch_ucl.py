#!/usr/bin/env python3
"""
HerFixtures — UEFA Women's Champions League feed generator
Uses ESPN public API (no key required) to fetch fixtures and write womens_ucl.ics.

Strategy: soccer scoreboard only accepts single dates, so all 18 league-phase
team schedules are iterated (season=2026 = 2026/27 start-year convention);
deduplication by event ID. Scoreboard (no date param) catches the live matchday.

Display convention: home_first=True — Home vs Away, score as (Home–Away).
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

OUTPUT_FILE = "womens_ucl.ics"
BASE_URL    = "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.wchampions"
SEASON_YEAR = 2026  # ESPN uses the start year: 2026 = 2026/27 season
HEADERS     = {"User-Agent": "Mozilla/5.0"}

# All 18 league-phase team IDs (confirmed July 2026)
TEAM_IDS = [
    "19256",  # OL Lyonnes
    "19258",  # PSG
    "19970",  # Chelsea
    "19973",  # Arsenal
    "20061",  # Man United
    "20091",  # Barcelona
    "20092",  # Juventus
    "20093",  # Atlético Madrid
    "20103",  # Bayern Munich
    "20107",  # VfL Wolfsburg
    "20114",  # FC Twente
    "20115",  # St. Pölten
    "20830",  # Benfica
    "20836",  # Vålerenga
    "21128",  # Real Madrid
    "21640",  # Paris FC
    "21685",  # Roma
    "131423", # OH Leuven
]


def fetch_games():
    session = requests.Session()
    session.headers.update(HEADERS)
    games = {}

    # Current/upcoming matchday — default scoreboard returns latest activity
    try:
        r = session.get(f"{BASE_URL}/scoreboard", timeout=10)
        r.raise_for_status()
        for event in r.json().get("events", []):
            eid = event.get("id")
            if not eid:
                continue
            games[eid] = event
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Scoreboard fetch error, skipping: {e}")

    # Full season from all 18 team schedules, deduplicated by event ID
    for team_id in TEAM_IDS:
        try:
            r = session.get(
                f"{BASE_URL}/teams/{team_id}/schedule",
                params={"season": SEASON_YEAR},
                timeout=10,
            )
            r.raise_for_status()
            for event in r.json().get("events", []):
                eid = event.get("id")
                if not eid:
                    continue
                games[eid] = event
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  Team {team_id} schedule error, skipping: {e}")

    return list(games.values())


def _score_str(competitor):
    s = competitor.get("score")
    if s is None or s == "":
        return None
    if isinstance(s, dict):
        return s.get("displayValue")
    return s


def parse_event(event):
    try:
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
        status_type  = comp["status"]["type"]
        status_desc  = status_type["description"]
        status_state = status_type.get("state", "pre")
        completed    = status_state == "post"

        score = ""
        if completed:
            h_score = _score_str(home) or "?"
            a_score = _score_str(away) or "?"
            score = f" ({h_score}–{a_score})"

        broadcasts = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]

        # Home first: "Home vs Away (h_score–a_score)"
        summary = f"⚽ {home_name} vs {away_name}{score}"

        round_detail = event.get("season", {}).get("slug", "")
        desc_lines = [
            f"Women's Champions League 2026/27{' · ' + round_detail if round_detail else ''}",
            f"{home_name} vs {away_name}",
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
            "uid":         f"espn-ucl-women-{event['id']}@herfixtures.com",
            "summary":     summary,
            "description": "\n".join(desc_lines),
            "dtstart":     game_dt,
            "dtend":       game_dt + timedelta(hours=2),
            "url":         url,
        }
    except Exception as e:
        print(f"  ⚠️  Skipping malformed event {event.get('id', '?')}: {e}")
        return None


def build_calendar(events):
    cal = Calendar()
    cal.add("prodid", "-//HerFixtures//UCL Women 2026-27//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Women's Champions League 2026/27 — HerFixtures")
    cal.add("x-wr-caldesc", "UEFA Women's Champions League 2026/27 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    now = datetime.now(timezone.utc)
    for ev in events:
        parsed = parse_event(ev)
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

    return cal


def main():
    print(f"Fetching UCL Women 2026/27 games from ESPN (season={SEASON_YEAR}, all 18 teams)...")
    events = fetch_games()
    print(f"  → {len(events)} games fetched")

    if not events:
        print("  ⚠️  No events returned — skipping write to preserve existing file")
        return

    cal = build_calendar(events)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())

    print(f"  → {OUTPUT_FILE} written successfully")


if __name__ == "__main__":
    main()
