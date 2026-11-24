#!/usr/bin/env python3
"""List the women's football leagues API-Football has for the current season.

One request (counts against the daily quota). Reads the key from APIFOOTBALL_KEY
or ~/.config/herfixtures/apifootball_key, never prints it.

Usage: python3 scripts/list_apifootball_womens_leagues.py
"""

import json
import os
import sys
from pathlib import Path

import requests

key = os.environ.get("APIFOOTBALL_KEY") or ""
if not key:
    p = Path.home() / ".config" / "herfixtures" / "apifootball_key"
    key = p.read_text().strip() if p.exists() else ""
if not key:
    sys.exit("No API-Football key found (APIFOOTBALL_KEY or ~/.config/herfixtures/apifootball_key)")

r = requests.get("https://v3.football.api-sports.io/leagues",
                 params={"current": "true", "type": "league"},
                 headers={"x-apisports-key": key}, timeout=30)
r.raise_for_status()
data = r.json()
if data.get("errors"):
    sys.exit(f"API error: {data['errors']}")

rows = []
for item in data.get("response", []):
    name = item["league"]["name"]
    if "women" not in name.lower() and "femin" not in name.lower() and "frauen" not in name.lower() and "damallsvenskan" not in name.lower():
        continue
    s = next((x for x in item["seasons"] if x.get("current")), item["seasons"][-1])
    rows.append({"id": item["league"]["id"], "league": name, "country": item["country"]["name"],
                 "season": s["year"], "start": s["start"], "end": s["end"]})

rows.sort(key=lambda x: (x["country"], x["league"]))
print(f"{len(rows)} women's leagues with a current season (requests left today: {r.headers.get('x-ratelimit-requests-remaining', '?')})\n")
for x in rows:
    print(f"{x['id']:>5}  {x['country']:<16} {x['league']:<40} {x['start']} → {x['end']}")
print("\nJSON:", json.dumps(rows, ensure_ascii=False))
