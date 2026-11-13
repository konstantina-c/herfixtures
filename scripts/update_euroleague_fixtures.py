#!/usr/bin/env python3
"""Merge new EuroLeague Women games into fixtures.json, validate, regenerate the feed.

Used by the scheduled update runs (no human review), so it is deliberately strict:
it only ever ADDS games or corrects future ones, never deletes, and refuses to
write anything if a single check fails.

Input (stdin), JSON copied from FIBA's official schedule:
  {
    "source_checked_at": "2026-12-03T09:00:00+01:00",      # optional
    "teams":    {"CODE": {"fiba_id": 1, "name": "...", "timezone": "Europe/Paris", "venue": "..."}},  # optional, new teams only
    "fixtures": [{"fiba_game_id": 1, "round": "RS-SR", "group": "E", "local": "2026-12-16T19:00", "home": "CODE", "away": "CODE"}]
  }

Usage:
  python3 scripts/update_euroleague_fixtures.py --dry-run < new_games.json
  python3 scripts/update_euroleague_fixtures.py < new_games.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import generate_euroleague_women_ics as gen  # noqa: E402

SEASON_START = datetime(2026, 9, 1)
SEASON_END = datetime(2027, 4, 30)
MIN_REST = timedelta(hours=20)  # a team never plays twice within 20 hours
REQUIRED_TEAM_FIELDS = ("name", "timezone")


def fail(msg: str) -> None:
    sys.exit(f"REFUSED: {msg}\nNothing was written.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
    args = ap.parse_args()

    try:
        incoming = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        fail(f"input is not valid JSON ({e})")
    if not isinstance(incoming.get("fixtures"), list) or not incoming["fixtures"]:
        fail("input has no 'fixtures' list")

    data = json.loads(gen.DATA_FILE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    added, corrected, unchanged, new_teams = [], [], 0, []

    # New teams: add only, never overwrite an existing code.
    for code, team in (incoming.get("teams") or {}).items():
        if code in data["teams"]:
            continue
        for field in REQUIRED_TEAM_FIELDS:
            if not team.get(field):
                fail(f"new team {code} is missing '{field}'")
        try:
            ZoneInfo(team["timezone"])
        except Exception:
            fail(f"new team {code} has unknown timezone {team['timezone']!r}")
        data["teams"][code] = team
        new_teams.append(code)

    by_id = {f["fiba_game_id"]: f for f in data["fixtures"]}
    for f in incoming["fixtures"]:
        missing = [k for k in ("fiba_game_id", "round", "local", "home", "away") if k not in f]
        if missing:
            fail(f"game {f.get('fiba_game_id')} is missing {missing}")
        if not isinstance(f["fiba_game_id"], int):
            fail(f"fiba_game_id must be a number, got {f['fiba_game_id']!r}")
        try:
            local = datetime.strptime(f["local"], "%Y-%m-%dT%H:%M")
        except ValueError:
            fail(f"game {f['fiba_game_id']} has bad time {f['local']!r} (expected YYYY-MM-DDTHH:MM)")
        if not (SEASON_START <= local <= SEASON_END):
            fail(f"game {f['fiba_game_id']} on {f['local']} is outside the 2026/27 season")
        if not 9 <= local.hour <= 22:
            fail(f"game {f['fiba_game_id']} tips off at {local:%H:%M} local time, which is unrealistic")
        entry = {k: f.get(k) for k in ("fiba_game_id", "round", "group", "local", "home", "away")}

        old = by_id.get(f["fiba_game_id"])
        if old is None:
            entry["sequence"] = 0
            data["fixtures"].append(entry)
            by_id[entry["fiba_game_id"]] = entry
            added.append(entry)
            continue
        changed = {k: (old.get(k), entry[k]) for k in ("round", "group", "local", "home", "away") if old.get(k) != entry[k]}
        if not changed:
            unchanged += 1
            continue
        if datetime.strptime(old["local"], "%Y-%m-%dT%H:%M") < now.replace(tzinfo=None) - timedelta(days=1):
            fail(f"game {old['fiba_game_id']} was already played; refusing to change it ({changed})")
        old.update(entry)
        old["sequence"] = old.get("sequence", 0) + 1  # tells calendar apps the event changed
        corrected.append((old["fiba_game_id"], changed))

    # Structural checks (unknown rounds/teams, duplicate ids, team vs itself) from the generator.
    try:
        gen.validate(data)
    except ValueError as e:
        fail(str(e))

    # A team never plays twice within MIN_REST.
    games_by_team: dict[str, list[datetime]] = {}
    for f in data["fixtures"]:
        t = datetime.strptime(f["local"], "%Y-%m-%dT%H:%M")
        for side in ("home", "away"):
            games_by_team.setdefault(f[side], []).append(t)
    for team, times in games_by_team.items():
        times.sort()
        for a, b in zip(times, times[1:]):
            if b - a < MIN_REST:
                fail(f"{data['teams'][team]['name']} would play twice within {MIN_REST} ({a} and {b}): likely a copy error")

    print(f"New teams: {new_teams or 'none'}")
    print(f"Added {len(added)} games, corrected {len(corrected)}, unchanged {unchanged}. Total now {len(data['fixtures'])}.")
    for e in sorted(added, key=lambda e: e["local"]):
        print(f"  + {e['local']}  {data['teams'][e['home']]['name']} vs {data['teams'][e['away']]['name']}  ({e['round']}{' · ' + e['group'] if e.get('group') else ''})")
    for gid, ch in corrected:
        print(f"  ~ game {gid}: {ch}")

    if args.dry_run:
        print("Dry run: nothing written.")
        return
    if not added and not corrected and not new_teams:
        print("No changes: nothing written.")
        return

    data["competition"]["source_checked_at"] = incoming.get("source_checked_at") or now.isoformat(timespec="seconds")
    data["fixtures"].sort(key=lambda f: (f["local"], f["fiba_game_id"]))
    gen.DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    calendar, count = gen.build(data)
    if not gen.safe_write_ics(gen.OUTPUT_FILE, calendar):
        sys.exit("REFUSED: shrink guard blocked the .ics write (see message above).")
    print(f"Wrote fixtures.json and {gen.OUTPUT_FILE.name} ({count} events).")


if __name__ == "__main__":
    main()
