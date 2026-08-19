#!/usr/bin/env python3
"""
HerFixtures — Spanish Liga F individual team feed generator
Uses ESPN public API (no key required) to generate per-team .ics feeds.

Strategy: fetches the full season once via date range scoreboard, then filters
events per team in Python. Avoids 16 individual API calls (team schedule
endpoint returns no data for this league before fixtures are confirmed).
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

BASE_URL     = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.w.1"
HEADERS      = {}  # requests default (python-requests/<version>) passes ESPN WAF; Mozilla/5.0 does not
SEASON_START = "20260801"
SEASON_END   = "20270701"

# ESPN team ID → (display name, output slug)
LIGA_F_TEAMS = {
    "21378":  ("Alavés",          "alaves"),
    "21372":  ("Athletic Club",   "athletic_club"),
    "20093":  ("Atlético Madrid", "atletico_madrid"),
    "20091":  ("Barcelona",       "barcelona"),
    "131393": ("CD Tenerife",     "tenerife"),
    "21145":  ("Deportivo",       "deportivo"),
    "21175":  ("Dux Logroño",     "dux_logrono"),
    "21376":  ("Eibar",           "eibar"),
    "21154":  ("Espanyol",        "espanyol"),
    "21149":  ("FC Badalona",     "badalona"),
    "21140":  ("Granada",         "granada"),
    "21425":  ("Madrid CFF",      "madrid_cff"),
    "21128":  ("Real Madrid",     "real_madrid"),
    "21428":  ("Real Sociedad",   "real_sociedad"),
    "21424":  ("Sevilla",         "sevilla"),
    "21374":  ("Valencia",        "valencia"),
}


def fetch_all_games():
    games = {}
    session = requests.Session()
    session.headers.update(HEADERS)

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
        print(f"  ⚠️  Season range scoreboard error: {e}")

    try:
        r = session.get(f"{BASE_URL}/scoreboard", timeout=10)
        r.raise_for_status()
        for event in r.json().get("events", []):
            eid = event.get("id")
            if eid:
                games[eid] = event
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Default scoreboard error: {e}")

    return list(games.values())


def events_for_team(all_events, team_id):
    result = []
    for event in all_events:
        comp = event["competitions"][0]
        ids = [c["team"].get("id", "") for c in comp["competitors"]]
        if team_id in ids:
            result.append(event)
    return result


def _score_str(competitor):
    s = competitor.get("score")
    if s is None or s == "":
        return None
    if isinstance(s, dict):
        return s.get("displayValue")
    return s


def parse_event(event, display_name):
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

        summary = f"⚽ {away_name} @ {home_name}{score}"

        desc_lines = [
            f"Spanish Liga F 2026/27",
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


def build_calendar(events, display_name):
    cal = Calendar()
    cal.add("prodid",  f"-//HerFixtures//Liga F 2026-27 {display_name}//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method",  "PUBLISH")
    cal.add("x-wr-calname",  f"{display_name} — Liga F 2026/27 — HerFixtures")
    cal.add("x-wr-caldesc",  f"{display_name} Liga F 2026/27 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    now = datetime.now(timezone.utc)
    for ev in events:
        parsed = parse_event(ev, display_name)
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
    print("Fetching full Liga F 2026/27 season from ESPN...")
    all_events = fetch_all_games()
    print(f"  → {len(all_events)} total events fetched")
    print()
    print("Generating Liga F team feeds...")

    success = 0
    for team_id, (display_name, output_slug) in LIGA_F_TEAMS.items():
        try:
            team_events = events_for_team(all_events, team_id)
            cal = build_calendar(team_events, display_name)
            output_file = f"liga_f_{output_slug}.ics"
            with open(output_file, "wb") as f:
                f.write(cal.to_ical())
            print(f"  ✓ {output_file:45} ({len(team_events)} events)")
            success += 1
        except Exception as e:
            print(f"  ✗ {display_name}: {e}")

    print()
    print(f"Done — {success}/{len(LIGA_F_TEAMS)} team feeds written.")


if __name__ == "__main__":
    main()
