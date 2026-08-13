#!/usr/bin/env python3
"""
HerFixtures — Frauen-Bundesliga competition feed generator
Uses OpenLigaDB public API (no key required, ODbL license) to fetch all
2026/27 season fixtures and write frauen_bundesliga.ics.

Shortcut: ffb1  Season: 2026  (OpenLigaDB uses start-year convention)
Skips any fixture with a 1970-01-01 epoch/null date (unconfirmed kickoff).
Venue: API location field where present; static home-stadium lookup otherwise.
Attribution: openligadb.de (ODbL) added to every event description.
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

API_URL     = "https://api.openligadb.de/getmatchdata/ffb1/2026"
OUTPUT_FILE = "frauen_bundesliga.ics"
HEADERS     = {"User-Agent": "HerFixtures/1.0"}

# Static home-stadium lookup — all 14 venues confirmed from OpenLigaDB 2026/27 data
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


def fetch_matches():
    r = requests.get(API_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def get_venue(match):
    """API location field first; static home-stadium lookup as fallback."""
    loc = match.get("location") or {}
    stadium = loc.get("locationStadium", "").strip()
    city    = loc.get("locationCity",    "").strip()
    if stadium:
        return f"{stadium}, {city}" if city else stadium
    home_id = (match.get("team1") or {}).get("teamId")
    if home_id and home_id in HOME_STADIUMS:
        s, c = HOME_STADIUMS[home_id]
        return f"{s}, {c}"
    return ""


def parse_match(match):
    # Skip unconfirmed kickoffs (epoch sentinel from OpenLigaDB)
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

    matchday    = (match.get("group") or {}).get("groupName", "")
    venue_str   = get_venue(match)
    match_id    = match.get("matchID", "")

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


def build_calendar(matches):
    cal = Calendar()
    cal.add("prodid",                    "-//HerFixtures//Frauen-Bundesliga 2026-27//EN")
    cal.add("version",                   "2.0")
    cal.add("calscale",                  "GREGORIAN")
    cal.add("method",                    "PUBLISH")
    cal.add("x-wr-calname",              "Frauen-Bundesliga 2026/27 — HerFixtures")
    cal.add("x-wr-caldesc",              "German Women's Bundesliga 2026/27 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone",             "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl",           "PT12H")

    now = datetime.now(timezone.utc)
    for m in matches:
        parsed = parse_match(m)
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
    print("Fetching Frauen-Bundesliga 2026/27 fixtures from OpenLigaDB...")
    matches = fetch_matches()
    print(f"  → {len(matches)} raw fixtures received")

    cal = build_calendar(matches)

    written = sum(1 for _ in cal.walk("VEVENT"))
    print(f"  → {written} fixtures written (epoch/TBD dates skipped)")

    if written == 0:
        print("  ⚠️  No events — skipping write to preserve existing file")
        return

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())

    print(f"  → {OUTPUT_FILE} written successfully")


if __name__ == "__main__":
    main()
