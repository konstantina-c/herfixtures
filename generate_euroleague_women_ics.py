#!/usr/bin/env python3
"""Generate euroleague_women.ics from the hand-maintained FIBA schedule.

Source: feeds/euroleague-women-2026-27/fixtures.json, copied from FIBA's
official EuroLeague Women schedule. There is no usable live API: ESPN has no
EuroLeague Women league, the old RapidAPI source is football-only, and
fiba.basketball blocks non-browser clients. Same manual pattern as the FIBA
Women's World Cup feed: edit fixtures.json, re-run this script, open a PR.

Not part of the refresh.yml cron.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "feeds" / "euroleague-women-2026-27" / "fixtures.json"
OUTPUT_FILE = ROOT / "euroleague_women.ics"  # public URL kept for existing subscribers
DTSTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> list[str]:
    """Fold an iCalendar content line at 75 UTF-8 octets (RFC 5545)."""
    parts: list[str] = []
    current = ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " " + char
        else:
            current += char
    parts.append(current)
    return parts


def validate(data: dict) -> None:
    seen = set()
    for f in data["fixtures"]:
        gid = f["fiba_game_id"]
        if gid in seen:
            raise ValueError(f"Duplicate FIBA game id {gid}")
        seen.add(gid)
        if f["round"] not in data["rounds"]:
            raise ValueError(f"Unknown round {f['round']} in game {gid}")
        for side in ("home", "away"):
            if f[side] not in data["teams"]:
                raise ValueError(f"Unknown team {f[side]} in game {gid}")
        if f["home"] == f["away"]:
            raise ValueError(f"Team plays itself in game {gid}")
        datetime.strptime(f["local"], "%Y-%m-%dT%H:%M")


def build(data: dict) -> tuple[str, int]:
    comp = data["competition"]
    teams = data["teams"]
    duration = timedelta(minutes=comp["default_duration_minutes"])
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//HerFixtures//EuroLeague Women 2026-27//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:EuroLeague Women 🏀",
        "X-WR-CALDESC:EuroLeague Women 2026/27 fixtures from FIBA's official schedule. Maintained by HerFixtures.com.",
        "X-WR-TIMEZONE:UTC",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    def utc_start(f: dict) -> datetime:
        tz = ZoneInfo(teams[f["home"]]["timezone"])  # games are played at the home team's venue
        return datetime.strptime(f["local"], "%Y-%m-%dT%H:%M").replace(tzinfo=tz).astimezone(timezone.utc)

    fixtures = sorted(data["fixtures"], key=lambda f: (utc_start(f), f["fiba_game_id"]))
    count = 0
    for f in fixtures:
        home, away = teams[f["home"]], teams[f["away"]]
        start = utc_start(f)
        end = start + duration
        stage = data["rounds"][f["round"]]
        if f.get("group"):
            stage += f" · Group {f['group']}"
        summary = f"🏀 {home['name']} vs {away['name']}"
        description = "\\n".join([
            escape(comp["name"]),
            escape(stage),
            escape(f"{home['name']} vs {away['name']}"),
            "",
            "Schedule source: FIBA (fiba.basketball)",
            "Fixtures by HerFixtures.com - Women's Sports on Your Calendar",
        ])
        event = [
            "BEGIN:VEVENT",
            f"UID:elw-2026-27-{f['fiba_game_id']}@herfixtures.com",
            f"DTSTAMP:{DTSTAMP}",
            f"SEQUENCE:{f.get('sequence', 0)}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{escape(summary)}",
            f"DESCRIPTION:{description}",
        ]
        if home.get("venue"):
            event.append(f"LOCATION:{escape(home['venue'])}")
        event += [
            f"URL:{comp['source_url']}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
        lines.extend(event)
        count += 1
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in fold(line)) + "\r\n", count


def main() -> None:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    validate(data)
    calendar, count = build(data)
    if count == 0:
        sys.exit("No fixtures - refusing to overwrite euroleague_women.ics")
    OUTPUT_FILE.write_bytes(calendar.encode("utf-8"))
    print(f"Wrote {OUTPUT_FILE.name}: {count} events")


if __name__ == "__main__":
    main()
