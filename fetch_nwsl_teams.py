#!/usr/bin/env python3
"""
HerFixtures — NWSL individual team feed generator
Uses ESPN public API (no key required) to generate per-team .ics feeds.
Uses the team schedule endpoint (soccer scoreboard does not support date ranges).
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.nwsl"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ESPN team ID → (display name, output slug)
NWSL_TEAMS = {
    "21422":  ("Angel City FC",       "angel_city"),
    "22187":  ("Bay FC",              "bay_fc"),
    "131562": ("Boston Legacy FC",    "boston_legacy"),
    "15360":  ("Chicago Stars FC",    "chicago_red_stars"),
    "131563": ("Denver Summit FC",    "denver_summit"),
    "15364":  ("Gotham FC",           "gotham_fc"),
    "17346":  ("Houston Dash",        "houston_dash"),
    "20907":  ("Kansas City Current", "kansas_city"),
    "15366":  ("NC Courage",          "north_carolina_courage"),
    "18206":  ("Orlando Pride",       "orlando_pride"),
    "15362":  ("Portland Thorns",     "portland_thorns"),
    "20905":  ("Racing Louisville",   "racing_louisville"),
    "21423":  ("San Diego Wave",      "san_diego_wave"),
    "15363":  ("Seattle Reign",       "seattle_reign"),
    "19141":  ("Utah Royals",         "utah_royals"),
    "15365":  ("Washington Spirit",   "washington_spirit"),
}


def fetch_team_games(team_id):
    r = requests.get(
        f"{BASE_URL}/teams/{team_id}/schedule",
        params={"season": 2026},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("events", [])


def _score_str(competitor):
    s = competitor.get("score")
    if s is None or s == "":
        return None
    if isinstance(s, dict):
        return s.get("displayValue")
    return s


def parse_event(event, display_name):
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
        f"NWSL 2026 · {display_name}",
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


def build_calendar(events, display_name):
    cal = Calendar()
    cal.add("prodid", f"-//HerFixtures//NWSL 2026 {display_name}//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"{display_name} 2026 — HerFixtures")
    cal.add("x-wr-caldesc", f"{display_name} 2026 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    now = datetime.now(timezone.utc)
    for ev in events:
        parsed = parse_event(ev, display_name)
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
    print("Generating NWSL 2026 team feeds from ESPN API...")
    print()

    success = 0
    for team_id, (display_name, output_slug) in NWSL_TEAMS.items():
        try:
            events = fetch_team_games(team_id)
            cal = build_calendar(events, display_name)
            output_file = f"nwsl_{output_slug}.ics"
            with open(output_file, "wb") as f:
                f.write(cal.to_ical())
            print(f"  ✓ {output_file:45} ({len(events)} events)")
            success += 1
        except Exception as e:
            print(f"  ✗ {display_name}: {e}")

    print()
    print(f"Done — {success}/{len(NWSL_TEAMS)} team feeds written.")


if __name__ == "__main__":
    main()
