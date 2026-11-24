#!/usr/bin/env python3
"""Probe API-Football before adding or moving a competition (about 5 requests).

Prints, for Serie A Women (139) and the UEFA Women's Champions League:
the team list with ids and crests (for feeds/espn_leagues.json), the number of
fixtures, how many are finished / scheduled, and the next few games. For the
UCL it also compares the fixture count with our live womens_ucl.ics (ESPN).

Reads the key from APIFOOTBALL_KEY or ~/.config/herfixtures/apifootball_key and
never prints it.

Usage: python3 scripts/apifootball_probe.py
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
key = os.environ.get("APIFOOTBALL_KEY") or ""
if not key:
    p = Path.home() / ".config" / "herfixtures" / "apifootball_key"
    key = p.read_text().strip() if p.exists() else ""
if not key:
    sys.exit("No API-Football key found (APIFOOTBALL_KEY or ~/.config/herfixtures/apifootball_key)")


def get(path, **params):
    r = requests.get(f"https://v3.football.api-sports.io/{path}", params=params,
                     headers={"x-apisports-key": key}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d.get("errors"):
        sys.exit(f"API error on {path}: {d['errors']}")
    return d.get("response", [])


def fixtures_summary(league_id, season, label):
    fx = get("fixtures", league=league_id, season=season)
    status = Counter(f["fixture"]["status"]["short"] for f in fx)
    upcoming = sorted((f for f in fx if f["fixture"]["status"]["short"] in ("NS", "TBD")),
                      key=lambda f: f["fixture"]["date"])
    print(f"\n== {label}: {len(fx)} fixtures, status {dict(status)}")
    rounds = Counter(f["league"]["round"] for f in fx)
    print("   rounds:", dict(rounds))
    for f in upcoming[:6]:
        print(f"   next: {f['fixture']['date']}  {f['teams']['home']['name']} v {f['teams']['away']['name']}"
              f"  [{f['fixture']['status']['short']}]  {f['league']['round']}")
    return fx


# 1. Serie A Women: fixtures per team (spot duplicate clubs) + kick-off times per round
fx = fixtures_summary(139, 2026, "Serie A Women 2026/27")
per_team = Counter()
for f in fx:
    for side in ("home", "away"):
        per_team[(f["teams"][side]["id"], f["teams"][side]["name"])] += 1
print("   games per team:", {f"{n} ({i})": c for (i, n), c in sorted(per_team.items(), key=lambda x: x[0][1])})
by_round = {}
for f in fx:
    if f["fixture"]["status"]["short"] in ("NS", "TBD"):
        by_round.setdefault(f["league"]["round"], []).append(f["fixture"]["date"][:16])
for rnd, times in sorted(by_round.items(), key=lambda x: int(x[0].split("-")[-1])):
    c = Counter(t[11:] for t in times)
    print(f"   {rnd}: dates {sorted(set(t[:10] for t in times))}  times {dict(c)}")
teams = [{"team": {"id": i, "name": n}} for (i, n) in per_team]

# 2. UEFA Women's Champions League: find it, then compare with our live feed
cups = [l for l in get("leagues", search="Champions League")
        if "women" in l["league"]["name"].lower()]
print("\n== Women's Champions League in API-Football:")
for l in cups:
    cur = next((s for s in l["seasons"] if s.get("current")), l["seasons"][-1])
    print(f"   id {l['league']['id']}  {l['league']['name']}  season {cur['year']}  {cur['start']} → {cur['end']}")
if cups:
    ucl = cups[0]
    cur = next((s for s in ucl["seasons"] if s.get("current")), ucl["seasons"][-1])
    fx = fixtures_summary(ucl["league"]["id"], cur["year"], f"{ucl['league']['name']} {cur['year']}")
    ours = (ROOT / "womens_ucl.ics").read_text(encoding="utf-8")
    n_ours = ours.count("BEGIN:VEVENT")
    print(f"\n   our womens_ucl.ics (ESPN): {n_ours} events · API-Football: {len(fx)} fixtures")
    print("   API-Football fixtures from Sep 2026:",
          sum(1 for f in fx if f["fixture"]["date"] >= "2026-09-01"))

print("\nJSON teams:", json.dumps({str(t["team"]["id"]): t["team"]["name"] for t in teams}, ensure_ascii=False))
if cups:
    print("UCL fixtures sample:", json.dumps([[f["fixture"]["date"][:16], f["teams"]["home"]["name"], f["teams"]["away"]["name"], f["fixture"]["status"]["short"], f["league"]["round"]] for f in sorted(fx, key=lambda f: f["fixture"]["date"]) if f["fixture"]["date"] >= "2026-09-01"], ensure_ascii=False))
