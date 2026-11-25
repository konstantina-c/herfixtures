#!/usr/bin/env python3
"""Can API-Football replace ESPN for our remaining football leagues? (read-only, ~12 requests)

For Liga F, WSL, Première Ligue, A-League Women, Liga MX Femenil and NWSL:
finds the women's league in API-Football (by country), then compares its season
with our current ESPN-built .ics: game count, and how many of our games have a
game on the same day at the same kick-off time in API-Football.

Reads the key from APIFOOTBALL_KEY or ~/.config/herfixtures/apifootball_key and
never prints it. Usage: python3 scripts/apifootball_coverage.py
"""

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

OURS = {  # our feed, country in API-Football, words that identify the women's top flight
    "Liga F":          ("liga_f.ics",          "Spain",     ["liga f", "primera division women", "primera división women", "femenina", "liga f women"]),
    "WSL":             ("wsl.ics",             "England",   ["super league women", "wsl", "women's super league", "fa wsl"]),
    "Première Ligue":  ("premiere_ligue.ics",  "France",    ["feminine division 1", "première ligue", "premiere ligue", "d1 arkema"]),
    "A-League Women":  ("a_league_women.ics",  "Australia", ["a-league women"]),
    "Liga MX Femenil": ("liga_mx_femenil.ics", "Mexico",    ["liga mx femenil", "liga mx women", "femenil"]),
    "NWSL":            ("nwsl.ics",            "USA",       ["nwsl women"]),
}


def get(path, **params):
    r = requests.get(f"https://v3.football.api-sports.io/{path}", params=params,
                     headers={"x-apisports-key": key}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d.get("errors"):
        sys.exit(f"API error on {path}: {d['errors']}")
    return d.get("response", [])


def our_games(ics):
    text = (ROOT / ics).read_text(encoding="utf-8")
    out = []
    for ev in text.split("BEGIN:VEVENT")[1:]:
        m = re.search(r"DTSTART[^:]*:(\d{8})(?:T(\d{4}))?", ev)
        if m:
            out.append((m.group(1), m.group(2)))   # (YYYYMMDD, HHMM or None for TBC)
    return out


for label, (ics, country, words) in OURS.items():
    print(f"\n== {label}  (ours: {ics})")
    leagues = get("leagues", country=country, current="true")
    cands = [l for l in leagues if any(w in l["league"]["name"].lower() for w in words)
             and "cup" not in l["league"]["name"].lower() and "copa" not in l["league"]["name"].lower()]
    if not cands:
        names = sorted(l["league"]["name"] for l in leagues)
        print(f"   NOT FOUND in API-Football under {country}. Women-ish leagues there: {names[:12]}")
        continue
    lg = cands[0]
    cur = next((s for s in lg["seasons"] if s.get("current")), lg["seasons"][-1])
    print(f"   API-Football: id {lg['league']['id']} '{lg['league']['name']}' season {cur['year']} {cur['start']} → {cur['end']}"
          + (f"  (other matches: {[c['league']['name'] for c in cands[1:]]})" if len(cands) > 1 else ""))
    fx = get("fixtures", league=lg["league"]["id"], season=cur["year"])
    theirs = Counter((f["fixture"]["date"][:10].replace("-", ""), f["fixture"]["date"][11:16].replace(":", "")) for f in fx)
    their_days = Counter(d for d, _ in theirs.elements())
    ours = our_games(ics)
    same_time = sum(1 for d, t in ours if t and theirs.get((d, t)))
    same_day = sum(1 for d, t in ours if their_days.get(d))
    timed = sum(1 for _, t in ours if t)
    status = Counter(f["fixture"]["status"]["short"] for f in fx)
    print(f"   games: ours {len(ours)} · API-Football {len(fx)}  status {dict(status)}")
    print(f"   our games with an API-Football game the same day: {same_day}/{len(ours)}; "
          f"same day AND kick-off: {same_time}/{timed} of our timed games")
    # The games where the two sources disagree, to check on the league's official site.
    by_day = {}
    for f in fx:
        d = f["fixture"]["date"][:10].replace("-", "")
        by_day.setdefault(d, []).append((f["fixture"]["date"][11:16].replace(":", ""), f["teams"]["home"]["name"], f["teams"]["away"]["name"], f["fixture"]["status"]["short"]))
    text = (ROOT / ics).read_text(encoding="utf-8")
    shown = 0
    for ev in text.split("BEGIN:VEVENT")[1:]:
        m = re.search(r"DTSTART[^:]*:(\d{8})(?:T(\d{4}))?", ev)
        summ = re.search(r"SUMMARY:(.*)", ev).group(1).strip()
        if not m or not m.group(2) or theirs.get((m.group(1), m.group(2))):
            continue
        d, t = m.group(1), m.group(2)
        api = [f"{x[0][:2]}:{x[0][2:]} {x[1]} v {x[2]} [{x[3]}]" for x in by_day.get(d, [])]
        print(f"   ≠ {d} {t[:2]}:{t[2:]}Z ours: {summ[:60]}\n       API-Football that day: {'; '.join(api)[:220] or 'none'}")
        shown += 1
        if shown >= 15:
            print("   … (more)"); break
    extra = len(fx) - len(ours)
    if extra > 0:
        mine = {(d, t) for d, t in ours if t}
        rounds = Counter(f["league"]["round"] for f in fx
                         if (f["fixture"]["date"][:10].replace("-", ""), f["fixture"]["date"][11:16].replace(":", "")) not in mine)
        print(f"   API-Football has {extra} more games; rounds of its games we don't have at that time: {dict(rounds)}")
