#!/usr/bin/env python3
"""
HerFixtures — Frauen-Bundesliga per-team feed generator
Uses OpenLigaDB public API (no key required, ODbL license) to generate
one .ics feed per team for the 2026/27 season.

All 182 fixtures are fetched once; each team's feed is filtered from that
single response — no per-team API calls needed.
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

API_URL = "https://api.openligadb.de/getmatchdata/ffb1/2026"
HEADERS = {"User-Agent": "HerFixtures/1.0"}

# OpenLigaDB team ID → (display name, output slug)
FRAUEN_BL_TEAMS = {
    6063: ("FC Bayern München Frauen",  "frauen_bl_bayern"),
    6062: ("SC Freiburg Frauen",        "frauen_bl_freiburg"),
    6064: ("TSG Hoffenheim Frauen",     "frauen_bl_hoffenheim"),
    6068: ("1. FC Köln Frauen",         "frauen_bl_koeln"),
    6073: ("Eintracht Frankfurt Frauen","frauen_bl_frankfurt"),
    6070: ("VfL Wolfsburg Frauen",      "frauen_bl_wolfsburg"),
    6071: ("Bayer Leverkusen Frauen",   "frauen_bl_leverkusen"),
    6067: ("SV Werder Bremen Frauen",   "frauen_bl_bremen"),
    6066: ("1. FC Nürnberg Frauen",     "frauen_bl_nuernberg"),
    6069: ("RB Leipzig Frauen",         "frauen_bl_leipzig"),
    6447: ("1. FC Union Berlin Frauen", "frauen_bl_union_berlin"),
    6324: ("Hamburger SV Frauen",       "frauen_bl_hsv"),
    6978: ("VfB Stuttgart Frauen",      "frauen_bl_stuttgart"),
    6976: ("1. FSV Mainz 05 Frauen",    "frauen_bl_mainz"),
}

HOME_STADIUMS = {
    6063: ("FC Bayern Campus",              "München"),
    6062: ("Dreisamstadion",                "Freiburg"),
    6064: ("Dietmar-Hopp-Stadion",          "Hoffenheim"),
    6068: ("Franz-Kremer-Stadion",          "Köln"),
    6073: ("Stadion am Brentanobad",        "Frankfurt"),
    6070: ("AOK Stadion",                   "Wolfsburg"),
    6071: ("Ulrich-Haberland-Stadion",      "Leverkusen"),
    6067: ("Weserstadion - Platz 11",       "Bremen"),
    6066: ("Max-Morlock-Stadion",           "Nürnberg"),
    6069: ("Trainingszentrum Cottaweg",     "Leipzig"),
    6447: ("Alte Försterei",                "Berlin"),
    6324: ("Volksparkstadion",              "Hamburg"),
    6978: ("GAZi-Stadion auf der Waldau",   "Stuttgart"),
    6976: ("Bruchwegstadion",               "Mainz"),
}


def fetch_all_matches():
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def get_venue(match):
    loc     = match.get("location") or {}
    stadium = loc.get("locationStadium", "").strip()
    city    = loc.get("locationCity",    "").strip()
    if stadium:
        return f"{stadium}, {city}" if city else stadium
    home_id = (match.get("team1") or {}).get("teamId")
    if home_id and home_id in HOME_STADIUMS:
        s, c = HOME_STADIUMS[home_id]
        return f"{s}, {c}"
    return ""


def parse_match(match, team_display_name):
    raw_utc = match.get("matchDateTimeUTC", "")
    if not raw_utc or raw_utc.startswith("1970-01-01"):
        return None

    try:
        dt = datetime.fromisoformat(raw_utc.rstrip("Z") + "+00:00")
    except ValueError:
        return None

    team1 = match.get("team1") or {}
    team2 = match.get("team2") or {}
    home  = team1.get("teamName", "?")
    away  = team2.get("teamName", "?")

    is_finished = match.get("matchIsFinished", False)
    results     = match.get("matchResults") or []
    score       = ""
    if is_finished and results:
        final = next(
            (r for r in results if r.get("resultTypeID") == 2),
            results[-1],
        )
        h = final.get("pointsTeam1", "?")
        a = final.get("pointsTeam2", "?")
        score = f" ({h}–{a})"

    matchday  = (match.get("group") or {}).get("groupName", "")
    venue_str = get_venue(match)
    match_id  = match.get("matchID", "")

    summary = f"⚽ {home} vs {away}{score}"

    desc_lines = [
        f"Frauen-Bundesliga 2026/27{' · ' + matchday if matchday else ''}",
        f"{home} vs {away}",
    ]
    if is_finished:
        desc_lines.append(f"Result: {score.strip('() ')}")
    if venue_str:
        desc_lines.append(f"Venue: {venue_str}")
    desc_lines.append("")
    desc_lines.append("Data: openligadb.de (ODbL) · Fixtures by HerFixtures.com")

    return {
        "uid":         f"openligadb-ffb1-{match_id}@herfixtures.com",
        "summary":     summary,
        "description": "\n".join(desc_lines),
        "dtstart":     dt,
        "dtend":       dt + timedelta(hours=2),
        "location":    venue_str,
    }


def build_team_calendar(team_matches, display_name, slug):
    cal = Calendar()
    cal.add("prodid",    f"-//HerFixtures//Frauen-Bundesliga 2026-27 {display_name}//EN")
    cal.add("version",   "2.0")
    cal.add("calscale",  "GREGORIAN")
    cal.add("method",    "PUBLISH")
    cal.add("x-wr-calname",  f"{display_name} 2026/27 — HerFixtures")
    cal.add("x-wr-caldesc",  f"{display_name} Frauen-Bundesliga 2026/27 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    now = datetime.now(timezone.utc)
    for m in team_matches:
        parsed = parse_match(m, display_name)
        if not parsed:
            continue
        ev = Event()
        ev.add("uid",         parsed["uid"])
        ev.add("summary",     parsed["summary"])
        ev.add("description", parsed["description"])
        ev.add("dtstart",     parsed["dtstart"])
        ev.add("dtend",       parsed["dtend"])
        ev.add("dtstamp",     now)
        if parsed["location"]:
            ev.add("location", parsed["location"])
        cal.add_component(ev)

    return cal


def main():
    print("Fetching Frauen-Bundesliga 2026/27 fixtures from OpenLigaDB (single call)...")
    all_matches = fetch_all_matches()
    print(f"  → {len(all_matches)} total fixtures fetched")
    print()

    success = 0
    for team_id, (display_name, slug) in FRAUEN_BL_TEAMS.items():
        team_matches = [
            m for m in all_matches
            if (m.get("team1") or {}).get("teamId") == team_id
            or (m.get("team2") or {}).get("teamId") == team_id
        ]
        cal = build_team_calendar(team_matches, display_name, slug)
        output_file = f"{slug}.ics"
        with open(output_file, "wb") as f:
            f.write(cal.to_ical())
        written = sum(1 for _ in cal.walk("VEVENT"))
        print(f"  ✓ {output_file:<45} ({written} fixtures)")
        success += 1

    print()
    print(f"Done — {success}/{len(FRAUEN_BL_TEAMS)} team feeds written.")


if __name__ == "__main__":
    main()
