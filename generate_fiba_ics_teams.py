#!/usr/bin/env python3
"""Generate per-team FIBA WWC 2026 .ics feeds from fixtures.json."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "feeds" / "fiba-wwc-2026" / "fixtures.json"
DTSTAMP = "20260820T060000Z"

# (name as it appears in fixtures.json, output slug)
FIBA_TEAMS = [
    ("Japan",       "japan"),
    ("Mali",        "mali"),
    ("Spain",       "spain"),
    ("Germany",     "germany"),
    ("Korea",       "korea"),
    ("Nigeria",     "nigeria"),
    ("Hungary",     "hungary"),
    ("France",      "france"),
    ("Australia",   "australia"),
    ("Puerto Rico", "puerto_rico"),
    ("Belgium",     "belgium"),
    ("Türkiye",     "turkiye"),
    ("USA",         "usa"),
    ("China",       "china"),
    ("Czechia",     "czechia"),
    ("Italy",       "italy"),
]


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> list[str]:
    """Fold an iCalendar content line at 75 UTF-8 octets (RFC 5545)."""
    parts: list[str] = []
    current = ""
    limit = 75
    for char in line:
        if len((current + char).encode("utf-8")) > limit:
            parts.append(current)
            current = " " + char
            limit = 75
        else:
            current += char
    parts.append(current)
    return parts


def stage_label(fixture: dict) -> str:
    stage = fixture["stage"]
    if stage == "group":
        return f"Group {fixture['group']}"
    return {
        "qualification": "Qualification to Quarter-Finals",
        "quarter-final": "Quarter-Final",
        "semi-final":    "Semi-Final",
        "third-place":   "Third Place Game",
        "final":         "Final",
    }[stage]


def ticket_product_key(fixture: dict) -> str:
    if fixture.get("ticket_product"):
        return fixture["ticket_product"]
    if fixture["stage"] == "group":
        return f"{fixture['venue']}-sessions"
    return "berlin-arena-final-phase"


def build_team(data: dict, team_name: str, slug: str) -> tuple[str, int]:
    competition = data["competition"]
    tz = ZoneInfo(competition["timezone"])
    duration = timedelta(minutes=competition["default_duration_minutes"])

    lines = [
        "BEGIN:VCALENDAR",
        f"PRODID:-//HerFixtures//FIBA Women's Basketball World Cup 2026 {team_name}//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{team_name} — FIBA WWC 2026 — HerFixtures",
        f"X-WR-CALDESC:{team_name} FIBA Women's Basketball World Cup 2026 fixtures."
        " Updated automatically by HerFixtures.com.",
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    count = 0
    for fixture in data["fixtures"]:
        if team_name not in (fixture["home"], fixture["away"]):
            continue
        if fixture["time"] is None:
            continue

        start_local = datetime.fromisoformat(
            f"{fixture['date']}T{fixture['time']}:00"
        ).replace(tzinfo=tz)
        end_local = start_local + duration
        start = start_local.astimezone(timezone.utc)
        end = end_local.astimezone(timezone.utc)

        resolved = not any(
            token in fixture["home"] + fixture["away"]
            for token in ("Winner", "Loser", "Group")
        )
        label = stage_label(fixture)
        tickets = data["ticket_products"][ticket_product_key(fixture)]
        summary = f"\U0001f3c0 {fixture['home']} vs {fixture['away']}"
        description = (
            f"FIBA Women's Basketball World Cup 2026\\n{escape(label)} - Game {fixture['game']}\\n"
            f"{escape(fixture['home'])} vs {escape(fixture['away'])}\\n"
            f"{escape(tickets['label'])}: {escape(tickets['url'])}\\n"
            f"Source: {escape(competition['source_url'])}\\n\\n"
            "Fixtures by HerFixtures.com - Women's Sports on Your Calendar"
        )
        event = [
            "BEGIN:VEVENT",
            f"UID:fiba-wwc-2026-{fixture['game']:03d}@herfixtures.com",
            f"DTSTAMP:{DTSTAMP}",
            f"SEQUENCE:{fixture.get('sequence', 0)}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{escape(data['venues'][fixture['venue']])}",
            f"URL:{competition['source_url']}",
            f"STATUS:{'CONFIRMED' if resolved else 'TENTATIVE'}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
        lines.extend(event)
        count += 1

    lines.append("END:VCALENDAR")
    calendar = "\r\n".join(part for line in lines for part in fold(line)) + "\r\n"
    return calendar, count


def main() -> None:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    print("Generating FIBA WWC 2026 team feeds...")
    success = 0
    for team_name, slug in FIBA_TEAMS:
        output_file = ROOT / f"fiba_wwc_{slug}.ics"
        calendar, count = build_team(data, team_name, slug)
        output_file.write_text(calendar, encoding="utf-8", newline="")
        print(f"  ✓ fiba_wwc_{slug}.ics  ({count} events)")
        success += 1
    print(f"\nDone — {success}/{len(FIBA_TEAMS)} team feeds written.")


if __name__ == "__main__":
    main()
