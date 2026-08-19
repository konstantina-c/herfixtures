#!/usr/bin/env python3
"""
HerFixtures — Spanish Liga F competition feed generator
Uses ESPN public API (no key required) to fetch fixtures and write liga_f.ics.

Strategy: scoreboard accepts date ranges for this league, so a single call
with the full season window fetches all 240 fixtures. The default scoreboard
(no date param) catches any live matchday event not yet in the range window.

Display convention: away_first (Away @ Home) — confirmed from ESPN shortName
e.g. "SEV @ DEP" = Sevilla away at Deportivo.
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

OUTPUT_FILE = "liga_f.ics"
BASE_URL    = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.w.1"
SEASON_YEAR = 2026  # ESPN start-year convention: 2026 = 2026/27 season
HEADERS     = {}    # requests default (python-requests/<version>) passes ESPN WAF; Mozilla/5.0 does not

# Full 2026/27 season window
SEASON_START = "20260801"
SEASON_END   = "20270701"


def fetch_games():
    session = requests.Session()
    session.headers.update(HEADERS)
    games = {}

    # Full season via date range (Liga F scoreboard accepts ranges, unlike NWSL/UCL)
    try:
        r = session.get(
            f"{BASE_URL}/scoreboard",
            params={"dates": f"{SEASON_START}-{SEASON_END}", "limit": 300},
            timeout=15,
        )
        r.raise_for_status()
        for event in r.json().get("events", []):
            eid = event.get("id")
            if eid:
                games[eid] = event
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Season range scoreboard error, skipping: {e}")

    # Default scoreboard — catches any live matchday not yet in the range response
    try:
        r = session.get(f"{BASE_URL}/scoreboard", timeout=10)
        r.raise_for_status()
        for event in r.json().get("events", []):
            eid = event.get("id")
            if eid:
                games[eid] = event
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Default scoreboard error, skipping: {e}")

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

        status_type  = comp["status"]["type"]
        status_desc  = status_type["description"]
        status_state = status_type.get("state", "pre")
        completed    = status_state == "post"

        score = ""
        if completed:
            a_score = _score_str(away) or "?"
            h_score = _score_str(home) or "?"
            score = f" ({a_score}–{h_score})"

        broadcasts = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]

        # Away @ Home convention (confirmed from ESPN shortName e.g. "SEV @ DEP")
        summary = f"⚽ {away_name} @ {home_name}{score}"

        desc_lines = [
            "Spanish Liga F 2026/27",
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
            "uid":         f"espn-liga-f-{event['id']}@herfixtures.com",
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
    cal.add("prodid",                    "-//HerFixtures//Liga F 2026-27//EN")
    cal.add("version",                   "2.0")
    cal.add("calscale",                  "GREGORIAN")
    cal.add("method",                    "PUBLISH")
    cal.add("x-wr-calname",              "Spanish Liga F 2026/27 — HerFixtures")
    cal.add("x-wr-caldesc",              "Spanish Liga F 2026/27 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone",             "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl",           "PT12H")

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
    print(f"Fetching Liga F 2026/27 games from ESPN (date range + live scoreboard)...")
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
