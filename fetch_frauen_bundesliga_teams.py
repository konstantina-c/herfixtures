#!/usr/bin/env python3
"""
HerFixtures — Frauen-Bundesliga per-team feed generator
Uses OpenLigaDB public API (no key required, ODbL license) to generate
one .ics feed per team for the 2026/27 season.

All 182 fixtures are fetched once; each team's feed is filtered from that
single response — no per-team API calls needed.

Parsing (venues, scores, time TBC for OpenLigaDB's Sunday 15:30 placeholder)
is shared with fetch_frauen_bundesliga.py, so both feeds always agree.
"""

from datetime import datetime, timezone
from icalendar import Calendar

from espn_common import safe_write_ics  # shrink guard: never overwrite a feed with <50% of its events
from fetch_frauen_bundesliga import fetch_matches, parse_match, to_vevent

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
        parsed = parse_match(m)
        if not parsed:
            continue
        cal.add_component(to_vevent(parsed, now))

    return cal


def main():
    print("Fetching Frauen-Bundesliga 2026/27 fixtures from OpenLigaDB (single call)...")
    all_matches = fetch_matches()
    print(f"  → {len(all_matches)} total fixtures fetched")

    if not all_matches:
        print("  ⚠️  No fixtures returned — skipping writes to preserve existing files")
        return

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
        if not safe_write_ics(output_file, cal.to_ical()):
            continue
        written = sum(1 for _ in cal.walk("VEVENT"))
        print(f"  ✓ {output_file:<45} ({written} fixtures)")
        success += 1

    print()
    print(f"Done — {success}/{len(FRAUEN_BL_TEAMS)} team feeds written.")


if __name__ == "__main__":
    main()
