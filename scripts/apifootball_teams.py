#!/usr/bin/env python3
"""List API-Football team ids for leagues we're moving off ESPN (read-only, 1 request each).

Prints, per league, every team with its API-Football id and name, next to our
current team list (feeds/espn_leagues.json) so each team calendar keeps its slug
(subscriber URLs never change). Writes the result to /tmp/hf-af-teams.json for Claude.

Reads the key from APIFOOTBALL_KEY or ~/.config/herfixtures/apifootball_key and
never prints it.
Usage: python3 scripts/apifootball_teams.py liga-f:142:2026 liga-mx-femenil:673:2026 nwsl:254:2026
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
key = os.environ.get("APIFOOTBALL_KEY") or ""
if not key:
    p = Path.home() / ".config" / "herfixtures" / "apifootball_key"
    key = p.read_text().strip() if p.exists() else ""
if not key:
    sys.exit("No API-Football key found (APIFOOTBALL_KEY or ~/.config/herfixtures/apifootball_key)")

config = json.loads((ROOT / "feeds" / "espn_leagues.json").read_text(encoding="utf-8"))["leagues"]
out = {}
for arg in sys.argv[1:]:
    lid, league, season = arg.split(":")
    for attempt in range(4):   # retry dropped connections
        try:
            r = requests.get("https://v3.football.api-sports.io/teams", params={"league": league, "season": season},
                             headers={"x-apisports-key": key}, timeout=30)
            r.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            if attempt == 3:
                sys.exit(f"{lid}: request failed after 4 tries ({type(e).__name__})")
            time.sleep(3 * (attempt + 1))
    data = r.json()
    if data.get("errors"):
        sys.exit(f"API error: {data['errors']}")
    teams = [{"id": t["team"]["id"], "name": t["team"]["name"], "logo": t["team"]["logo"]} for t in data["response"]]
    out[lid] = teams
    ours = [v[0] for v in config.get(lid, {}).get("teams", {}).values()]
    print(f"\n== {lid} (API-Football {league}, season {season}): {len(teams)} teams · ours {len(ours)}")
    for t in sorted(teams, key=lambda t: t["name"]):
        print(f"   {t['id']:>6}  {t['name']}")
    print("   ours:", ", ".join(sorted(ours)))
Path("/tmp/hf-af-teams.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print("\nSaved /tmp/hf-af-teams.json")
