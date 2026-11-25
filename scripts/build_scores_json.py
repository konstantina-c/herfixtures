#!/usr/bin/env python3
"""Build scores.json for the homepage Scores Strip from our own published feeds.

One source of truth: the strip shows exactly the games in the .ics files fans
subscribe to (feeds/manifest.json), never a separate ESPN call. Rules (agreed
with Konstantina, Nov 24 2026):

  1. Every competition in feeds/manifest.json appears automatically when it has
     games in the windows below; frozen feeds never do.
  2. Per competition (dropdown choice): results from the last 3 days, games in the
     next 7 days, up to 10 each. Every competition with a game still to play is listed;
     with nothing in the windows it carries next_date ("Next games Wed 16 Dec").
  3. "All competitions" (default): results from the last 3 days, at most 3 per
     competition; games in the next 3 days, at most 2 per competition; 12 cards
     max per section. Most recent results first, soonest games first.
     The page computes this view itself from (2) so it is always relative to "now";
     the same mix is also written to the legacy "competitions" block below.
  4. No "Live" section: data refreshes twice a day, too slow to be truthful.
  5. Team order: away team on top for US competitions (feeds/strip.json
     "away_first"), home team on top everywhere else.
  6. Nothing is invented: a game without a confirmed time is marked "tbc";
     a missing crest stays empty (the page shows the team's initial).

Short names + crests: feeds/strip/<league>.json (written by fetch_espn_feeds.py,
keyed by event UID), else feeds/strip.json "teams" (keyed by .ics team name),
else the .ics name with no crest.

Output (version 2):
  {"updated", "version": 2, "rules": {...},
   "leagues": [{"id", "name" (dropdown), "short" (cards), "sport", "results": [game], "upcoming": [game]}],
   "competitions": {"all": {... legacy shape for the pre-dropdown page ...}}}
  game = {"kickoff": ISO-UTC | null, "date": "YYYY-MM-DD", "tbc": bool,
          "top": {"name", "logo", "score"?}, "bottom": {...}, "winner": "top"|"bottom"|"draw"|null}

Usage: python3 scripts/build_scores_json.py [--now 2026-11-22T12:00:00Z] [--out scores.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar

ROOT = Path(__file__).resolve().parent.parent
RULES = {
    "results_days": 3, "upcoming_days": 7, "per_league_max": 10,
    "all_results_per_league": 3, "all_upcoming_days": 3, "all_upcoming_per_league": 2, "all_max": 12,
}
SCORE = re.compile(r"\s*\((\d+)\s*[–-]\s*(\d+)\)$")
TAG = re.compile(r"\s*\((time TBC|postponed|cancelled|canceled|abandoned|suspended)\)$", re.I)
SKIP_TAGS = {"postponed", "cancelled", "canceled", "abandoned", "suspended"}


def parse_summary(summary: str) -> dict | None:
    """'⚽ A vs B (2–1)' / '🏀 A @ B (time TBC)' -> teams, scores, flags. None = not a game."""
    s = summary.strip()
    sport = "basketball" if s.startswith("🏀") else "football"
    s = re.sub(r"^\S+\s+", "", s) if s[:1] in "⚽🏀" else s
    score, tags = None, set()
    while True:
        m = SCORE.search(s)
        if m and score is None:
            score = (int(m.group(1)), int(m.group(2)))
            s = s[: m.start()]
            continue
        t = TAG.search(s)
        if t:
            tags.add(t.group(1).lower())
            s = s[: t.start()]
            continue
        break
    if tags & SKIP_TAGS:
        return None
    for sep, home_first in ((" vs ", True), (" @ ", False)):
        if sep in s:
            first, second = (x.strip() for x in s.split(sep, 1))
            home, away = (first, second) if home_first else (second, first)
            s_home = s_away = None
            if score:
                s_home, s_away = score if home_first else (score[1], score[0])
            return {"sport": sport, "home": home, "away": away, "s_home": s_home, "s_away": s_away}
    return None


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def team(name: str, side: str, uid: str, engine: dict, static: dict) -> dict:
    e = (engine.get(uid) or {}).get(side) or {}
    st = static.get(name) or static.get(e.get("name", "")) or {}
    return {"name": e.get("name") or st.get("name", name), "logo": e.get("logo") or st.get("logo", "")}


def league_games(feed: dict, cfg: dict, now: datetime) -> dict | None:
    path = ROOT / feed["ics"]
    try:
        cal = Calendar.from_ical(path.read_bytes())
    except (OSError, ValueError) as e:
        print(f"  ⚠️  {feed['id']}: cannot read {feed['ics']} ({e}) — skipped")
        return None
    engine = load_json(ROOT / "feeds" / "strip" / f"{feed['id']}.json", {})
    static = cfg.get("teams", {}).get(feed["id"], {})
    away_first = feed["id"] in cfg.get("away_first", [])
    r_from = now - timedelta(days=RULES["results_days"])
    u_to = now + timedelta(days=RULES["upcoming_days"])
    results, upcoming, sport = [], [], None
    next_date = None   # first unplayed game after now (any distance): "Next games Wed 16 Dec"

    for ev in cal.walk("VEVENT"):
        g = parse_summary(str(ev.get("summary", "")))
        dt = ev.get("dtstart")
        if not g or dt is None:
            continue
        sport = sport or g["sport"]
        start = dt.dt
        tbc = not isinstance(start, datetime)
        if tbc:  # all-day = kick-off not confirmed; compare by day
            day = start
            when = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        else:
            when = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
            when = when.astimezone(timezone.utc)
            day = when.date()
        uid = str(ev.get("uid", ""))
        home = team(g["home"], "home", uid, engine, static)
        away = team(g["away"], "away", uid, engine, static)
        top, bottom = (away, home) if away_first else (home, away)
        game = {"kickoff": None if tbc else when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "date": day.isoformat(), "tbc": tbc, "top": top, "bottom": bottom, "winner": None}

        if g["s_home"] is not None:
            if r_from <= when <= now:
                s_top, s_bot = (g["s_away"], g["s_home"]) if away_first else (g["s_home"], g["s_away"])
                top["score"], bottom["score"] = s_top, s_bot
                game["winner"] = "top" if s_top > s_bot else "bottom" if s_bot > s_top else "draw"
                results.append(game)
        elif (when >= now if not tbc else day >= now.date()):
            next_date = min(next_date, day.isoformat()) if next_date else day.isoformat()
            if when <= u_to:
                upcoming.append(game)

    results.sort(key=lambda x: (x["kickoff"] or x["date"]), reverse=True)
    upcoming.sort(key=lambda x: (x["date"], x["tbc"], x["kickoff"] or ""))
    n = RULES["per_league_max"]
    name = cfg.get("labels", {}).get(feed["id"], feed["name"])
    return {"id": feed["id"], "name": name, "short": cfg.get("short", {}).get(feed["id"], name),
            "sport": sport or "football", "results": results[:n], "upcoming": upcoming[:n], "next_date": next_date}


def all_mix(leagues: list[dict], now: datetime) -> tuple[list, list]:
    """The default 'All competitions' view (rule 3)."""
    res, up = [], []
    u_to = (now + timedelta(days=RULES["all_upcoming_days"]))
    for lg in leagues:
        res += [dict(g, league=lg["short"]) for g in lg["results"][: RULES["all_results_per_league"]]]
        soon = [g for g in lg["upcoming"] if g["date"] <= u_to.date().isoformat()
                and (g["tbc"] or g["kickoff"] <= u_to.strftime("%Y-%m-%dT%H:%M:%SZ"))]
        up += [dict(g, league=lg["short"]) for g in soon[: RULES["all_upcoming_per_league"]]]
    res.sort(key=lambda x: (x["kickoff"] or x["date"]), reverse=True)
    up.sort(key=lambda x: (x["date"], x["tbc"], x["kickoff"] or ""))
    return res[: RULES["all_max"]], up[: RULES["all_max"]]


def legacy_card(g: dict) -> dict:
    """Shape read by the pre-dropdown homepage (home slot = top card row)."""
    c = {"league": g["league"], "home": dict(g["top"]), "away": dict(g["bottom"])}
    if g["winner"]:
        c["winner"] = {"top": "home", "bottom": "away"}.get(g["winner"], "draw")
    if g["kickoff"]:
        c["kickoff"] = g["kickoff"]
    else:
        c["kickoff_label"] = datetime.fromisoformat(g["date"]).strftime("%a %-d %b") + " · time TBC"
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="pretend now is this ISO time (testing)")
    ap.add_argument("--out", default=str(ROOT / "scores.json"))
    args = ap.parse_args()
    now = (datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now
           else datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)

    manifest = load_json(ROOT / "feeds" / "manifest.json", None)
    cfg = load_json(ROOT / "feeds" / "strip.json", None)
    if not manifest or cfg is None:
        sys.exit("feeds/manifest.json or feeds/strip.json missing or unreadable")
    feeds = {f["id"]: f for f in manifest["feeds"] if f.get("source") != "frozen"}
    order = [i for i in cfg.get("order", []) if i in feeds] + [i for i in feeds if i not in cfg.get("order", [])]

    leagues = []
    for fid in order:
        lg = league_games(feeds[fid], cfg, now)
        # Listed when it has games in the windows, or is mid-season with a next game later
        # (e.g. UCL between matchdays): the dropdown then shows "Next games <date>".
        if lg and (lg["results"] or lg["upcoming"] or lg["next_date"]):
            leagues.append(lg)
        print(f"  {fid}: {len(lg['results']) if lg else 0} results, {len(lg['upcoming']) if lg else 0} upcoming")

    res, up = all_mix(leagues, now)
    out = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": 2,
        "rules": RULES,
        "leagues": leagues,
        # Legacy block for the homepage before the dropdown ships: the "All competitions" mix.
        "competitions": {"all": {"name": "All competitions", "sport": "mixed", "slug": "all",
                                 "postgame": [legacy_card(g) for g in res], "livegame": [],
                                 "pregame": [legacy_card(g) for g in up]}},
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  → {args.out}: {len(leagues)} competitions; All view: {len(res)} results, {len(up)} upcoming")


if __name__ == "__main__":
    main()
