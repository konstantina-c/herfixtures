#!/usr/bin/env python3
"""HerFixtures shared feed engine for ESPN-sourced competitions.

Every league is a config entry in feeds/espn_leagues.json, so adding a
competition is configuration, not another copy of a fetch script. For each
league this writes the competition feed and one feed per configured team.

Safeguards (all leagues get them automatically):
  - Polite fetching: leagues run one after another, 2 parallel requests max,
    one request per day (ESPN rejects date ranges). Games older than
    PAST_REFETCH_DAYS are kept from the existing file instead of re-fetched,
    so a mid-season run touches only the last week + the rest of the season.
    Set HERFIXTURES_FULL_REFETCH=1 (or delete the file) to rebuild everything.
  - Time TBC: ESPN marks unconfirmed kick-offs with timeValid=false and a
    placeholder time (18:00/20:00 UTC). Those become all-day events titled
    "(time TBC)"; they turn into timed events once ESPN confirms the time
    (same UID, so calendar apps update in place).
  - Placeholder ("TBD") games dropped; shrink guard on every write;
    a partial fetch never produces a feed (fetch_days refuses).
  - Second source: a league with "source": "api-football" is fetched from
    API-Football (licensed, key in APIFOOTBALL_KEY) via apifootball.py, with the
    same calendar building, team feeds and shrink guard.

Usage:
  python3 fetch_espn_feeds.py                 # all leagues
  python3 fetch_espn_feeds.py liga-f          # one league
  python3 fetch_espn_feeds.py --out-dir /tmp/x liga-f   # write elsewhere (testing)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from icalendar import Calendar, Event

import apifootball
from espn_common import fetch_days, is_placeholder, safe_write_ics

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "feeds" / "espn_leagues.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports"
PAST_REFETCH_DAYS = 7
STRIP_DAYS_BACK, STRIP_DAYS_AHEAD = 4, 8   # strip team data kept around today (see write_strip_teams)
FOOTER = "\nFixtures by HerFixtures.com — Women's Sports on Your Calendar"


# ── Parsing ───────────────────────────────────────────────────────────────────

def _score(c: dict) -> str | None:
    s = c.get("score")
    if s in (None, ""):
        return None
    return s.get("displayValue") if isinstance(s, dict) else str(s)


def parse(event: dict, league: dict, first_line: str | None = None) -> dict | None:
    """ESPN event -> plain dict used to build calendar events.

    first_line: description line 1 (default league["title"]; team feeds may pass
    league["team_title"] with {team} filled). Optional league["title_round"]
    appends ESPN's stage slug, e.g. "Women's Champions League 2026/27 · league-phase".
    """
    try:
        comp = event["competitions"][0]
        home = next((c for c in comp["competitors"] if c["homeAway"] == "home"), None)
        away = next((c for c in comp["competitors"] if c["homeAway"] == "away"), None)
        if not home or not away:
            return None
        # ESPN sometimes pads names ("Western Sydney "), so trim and collapse spaces.
        # Optional per league: team_name "location" ("Duke" instead of "Duke Blue Devils"),
        # show_rank (prefix "#5" for teams ranked 1-25 at game time).
        def name_of(c: dict) -> str:
            t = c["team"]
            raw = (t.get("location") if league.get("team_name") == "location" else None) or t.get("displayName") or t.get("name", "")
            n = " ".join(raw.split())
            rank = (c.get("curatedRank") or {}).get("current", 99)
            return f"#{rank} {n}" if league.get("show_rank") and rank <= 25 else n
        h_name, a_name = name_of(home), name_of(away)

        # Short name + crest for the homepage Scores Strip (feeds/strip/<league>.json).
        def strip_team(c: dict) -> dict:
            t = c["team"]
            short = t.get("location") if league.get("team_name") == "location" else t.get("shortDisplayName")
            short = " ".join((short or t.get("displayName") or "").split())
            rank = (c.get("curatedRank") or {}).get("current", 99)
            if league.get("show_rank") and rank <= 25:
                short = f"#{rank} {short}"
            return {"name": short, "logo": t.get("logo", "")}
        start = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        status = comp["status"]["type"]
        done = status.get("state") == "post"
        time_tbc = comp.get("timeValid") is False and not done

        if league["order"] == "home_vs_away":
            score = f" ({_score(home) or '?'}–{_score(away) or '?'})" if done else ""
            title = f"{h_name} vs {a_name}"
            line2 = f"{h_name} vs {a_name}"
        else:
            score = f" ({_score(away) or '?'}–{_score(home) or '?'})" if done else ""
            title = f"{a_name} @ {h_name}"
            line2 = f"{a_name} at {h_name}"
        summary = f"{league['emoji']} {title}{score}" + (" (time TBC)" if time_tbc else "")

        line1 = first_line or league["title"]
        stage = (event.get("season") or {}).get("slug", "")
        if league.get("title_round") and stage:
            line1 += f" · {stage}"
        desc = [line1, line2, f"Status: {status.get('description', '')}"]
        if time_tbc:
            desc.append("Kick-off time not confirmed yet. Your calendar updates automatically once it is.")
        venue = comp.get("venue", {}) or {}
        if venue.get("fullName"):
            city = (venue.get("address") or {}).get("city", "")
            desc.append(f"Venue: {venue['fullName']}{', ' + city if city else ''}")
        tv = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]
        if tv:
            desc.append(f"TV: {', '.join(tv)}")
        desc.append(FOOTER)

        links = event.get("links", [])
        return {
            "uid": f"{league['uid_prefix']}-{event['id']}@herfixtures.com",
            "summary": summary,
            "description": "\n".join(desc),
            "start": start,
            "minutes": league.get("match_minutes", 120),
            "time_tbc": time_tbc,
            "url": links[0].get("href", "https://herfixtures.com") if links else "https://herfixtures.com",
            "team_ids": {str(home["team"].get("id", "")), str(away["team"].get("id", ""))},
            "strip": {"home": strip_team(home), "away": strip_team(away)},
        }
    except (KeyError, IndexError, TypeError, ValueError) as e:
        print(f"  ⚠️  Skipping malformed event {event.get('id', '?')}: {e}")
        return None


# ── Calendar building ─────────────────────────────────────────────────────────

def to_vevent(g: dict, now: datetime) -> Event:
    ev = Event()
    ev.add("uid", g["uid"])
    ev.add("summary", g["summary"])
    ev.add("description", g["description"])
    if g["time_tbc"]:
        day = g["start"].date()
        ev.add("dtstart", day)
        ev.add("dtend", day + timedelta(days=1))
    else:
        ev.add("dtstart", g["start"])
        ev.add("dtend", g["start"] + timedelta(minutes=g["minutes"]))
    ev.add("dtstamp", now)
    ev.add("url", g["url"])
    return ev


def _event_day(component) -> date | None:
    v = component.get("dtstart")
    if v is None:
        return None
    v = v.dt
    return v.date() if isinstance(v, datetime) else v


def kept_past_events(path: Path, cutoff: date) -> list:
    """Events older than cutoff from the existing file (not re-fetched)."""
    if not path.exists():
        return []
    try:
        cal = Calendar.from_ical(path.read_bytes())
    except ValueError:
        return []
    return [c for c in cal.walk("VEVENT") if (_event_day(c) or cutoff) < cutoff]


def build_calendar(prodid: str, name: str, desc: str, kept: list, games: list[dict], now: datetime) -> Calendar:
    cal = Calendar()
    cal.add("prodid", prodid)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-caldesc", desc)
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")
    by_uid = {str(c.get("uid")): c for c in kept}
    for g in games:
        by_uid[g["uid"]] = to_vevent(g, now)  # fresh data wins over kept
    for comp in sorted(by_uid.values(), key=lambda c: (str(_event_day(c)), str(c.get("uid")))):
        cal.add_component(comp)
    return cal


def team_schedule(league: dict, team_id: str) -> list | None:
    """All games of one team from ESPN's team schedule endpoint (past + scheduled)."""
    url = f"{ESPN}/{league['espn']}/teams/{team_id}/schedule"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                return r.json().get("events", [])
        except requests.exceptions.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def write_strip_teams(lid: str, games: list[dict], out_dir: Path, today: date) -> None:
    """Short team names + crests for games around today, keyed by event UID.

    scripts/build_scores_json.py joins these onto the published .ics events, so the
    Scores Strip shows exactly the games fans subscribe to, with compact names.
    """
    lo, hi = today - timedelta(days=STRIP_DAYS_BACK), today + timedelta(days=STRIP_DAYS_AHEAD)
    teams = {g["uid"]: g["strip"] for g in games if "strip" in g and lo <= g["start"].date() <= hi}
    path = out_dir / "feeds" / "strip" / f"{lid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(teams, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# ── One league ────────────────────────────────────────────────────────────────

def run_league(lid: str, league: dict, out_dir: Path, today: date) -> bool:
    season_start = date.fromisoformat(league["season"]["start"])
    season_end = date.fromisoformat(league["season"]["end"])
    main_file = out_dir / league["output"]
    full = os.environ.get("HERFIXTURES_FULL_REFETCH") == "1" or not main_file.exists()
    cutoff = season_start if full else max(season_start, today - timedelta(days=PAST_REFETCH_DAYS))
    fetch_from = cutoff
    fetch_to = season_end

    print(f"{league['name']}: fetching {fetch_from} → {fetch_to} ({'full rebuild' if full else f'older games kept from {main_file.name}'})")
    if fetch_from > fetch_to:
        print("  season over and fully stored — nothing to fetch")
        return True
    if league.get("source") == "api-football":
        return run_api_football(lid, league, out_dir, main_file, full, cutoff)
    try:
        raw = fetch_days(f"{ESPN}/{league['espn']}/scoreboard", fetch_from, fetch_to, workers=2)
    except RuntimeError as e:
        print(f"  ⚠️  {e} — keeping existing {league['name']} feeds")
        return False
    events = [e for e in raw.values() if not is_placeholder(e)]
    if league.get("rank_filter"):  # e.g. NCAA: only games involving a team ranked 1..N at game time
        limit = league["rank_filter"]
        events = [e for e in events if any((c.get("curatedRank") or {}).get("current", 99) <= limit
                                           for c in e["competitions"][0]["competitors"])]
    games = [g for g in (parse(e, league) for e in events) if g]
    tbc = sum(g["time_tbc"] for g in games)
    now = datetime.now(timezone.utc)

    kept = [] if full else kept_past_events(main_file, cutoff)
    cal = build_calendar(league["prodid"], league["cal_name"], league["cal_desc"], kept, games, now)
    total = len(cal.walk("VEVENT"))
    print(f"  → {len(games)} fetched ({tbc} time TBC) + {len(kept)} kept = {total} events")
    if total == 0:
        print("  ⚠️  No events — keeping existing file")
        return False
    ok = safe_write_ics(main_file, cal.to_ical())
    write_strip_teams(lid, games, out_dir, today)

    for team_id, (team, slug) in league.get("teams", {}).items():
        path = out_dir / f"{league['team_prefix']}{slug}.ics"
        # Optional league["team_title"]: team-specific description line 1, e.g. "NWSL 2026 · {team}"
        t_line = league["team_title"].format(team=team) if league.get("team_title") else None
        if league.get("team_source") == "schedule":
            # Team feed from the team's own schedule (all its games, ranked opponent or not).
            t_raw = team_schedule(league, team_id)
            if t_raw is None:
                print(f"  ⚠️  {team}: schedule fetch failed — keeping existing {path.name}")
                continue
            t_games = [g for g in (parse(e, league, t_line) for e in t_raw if not is_placeholder(e)) if g]
        elif t_line:
            t_events = [e for e in events if team_id in {str(c["team"].get("id", "")) for c in e["competitions"][0]["competitors"]}]
            t_games = [g for g in (parse(e, league, t_line) for e in t_events) if g]
        else:
            t_games = [g for g in games if team_id in g["team_ids"]]
        t_kept = [] if full else kept_past_events(path, cutoff)
        fmt = lambda s: s.format(team=team)
        t_cal = build_calendar(fmt(league["team_prodid"]), fmt(league["team_cal_name"]), fmt(league["team_cal_desc"]), t_kept, t_games, now)
        safe_write_ics(path, t_cal.to_ical())
    if league.get("teams"):
        print(f"  → {len(league['teams'])} team feeds")
    return ok


def slugify(name: str) -> str:
    """'Paris Saint-Germain' -> 'paris_saint_germain', 'HB Køge' -> 'hb_koge'."""
    import re
    import unicodedata
    n = unicodedata.normalize("NFKD", name.replace("ø", "o").replace("Ø", "O")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def auto_teams(lid: str, league: dict, fixtures: list[dict], out_dir: Path) -> dict:
    """Team list derived from the fixtures (league["auto_teams"]), for competitions whose
    field changes every season (UCL). Skips teams that only played rounds whose name
    contains a skip word (e.g. "Qualifying"), and writes feeds/teams/<league>.json
    (id, name, slug, crest) for the homepage picker."""
    rule = league["auto_teams"]
    skip = [w.lower() for w in rule.get("skip_rounds_containing", [])]
    found = {}
    for fx in fixtures:
        if any(w in fx["league"].get("round", "").lower() for w in skip):
            continue
        for side in ("home", "away"):
            t = fx["teams"][side]
            name = apifootball.team_name(t, league)
            found[str(t["id"])] = {"id": str(t["id"]), "name": name, "slug": slugify(name), "logo": t.get("logo", "")}
    teams = sorted(found.values(), key=lambda t: t["name"])
    path = out_dir / "feeds" / "teams" / f"{lid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(teams, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {t["id"]: [t["name"], t["slug"]] for t in teams}


def run_api_football(lid: str, league: dict, out_dir: Path, main_file: Path, full: bool, cutoff: date) -> bool:
    """Same output as the ESPN path, from API-Football (see apifootball.py)."""
    af = league["api_football"]
    try:
        fixtures = apifootball.fetch_fixtures(af["league"], af["season"])
    except apifootball.SourceError as e:
        print(f"  ⚠️  {e} — keeping existing {league['name']} feeds")
        return False
    now = datetime.now(timezone.utc)
    season_start = date.fromisoformat(league["season"]["start"])
    in_season = [fx for fx in fixtures if datetime.fromisoformat(fx["fixture"]["date"]).date() >= season_start]
    placeholders = apifootball.placeholder_ids(in_season, now, af.get("uniform_min", 4))
    all_games = [g for g in (apifootball.parse(fx, league, placeholders) for fx in in_season) if g]
    games = [g for g in all_games if g["start"].date() >= cutoff]
    kept = [] if full else kept_past_events(main_file, cutoff)
    cal = build_calendar(league["prodid"], league["cal_name"], league["cal_desc"], kept, games, now)
    total = len(cal.walk("VEVENT"))
    print(f"  → {len(games)} fetched ({sum(g['time_tbc'] for g in games)} time TBC) + {len(kept)} kept = {total} events")
    if total == 0:
        print("  ⚠️  No events — keeping existing file")
        return False
    ok = safe_write_ics(main_file, cal.to_ical())
    write_strip_teams(lid, games, out_dir, datetime.now(timezone.utc).date())
    teams = auto_teams(lid, league, in_season, out_dir) if league.get("auto_teams") else league.get("teams", {})
    for team_id, (team, slug) in teams.items():
        path = out_dir / f"{league['team_prefix']}{slug}.ics"
        # A new team file gets the whole season; an existing one reuses its older games.
        new_file = full or not path.exists()
        t_games = [g for g in (all_games if new_file else games) if team_id in g["team_ids"]]
        t_kept = [] if new_file else kept_past_events(path, cutoff)
        fmt = lambda s: s.format(team=team)
        t_cal = build_calendar(fmt(league["team_prodid"]), fmt(league["team_cal_name"]), fmt(league["team_cal_desc"]), t_kept, t_games, now)
        safe_write_ics(path, t_cal.to_ical())
    if teams:
        print(f"  → {len(teams)} team feeds")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("leagues", nargs="*", help="league ids from feeds/espn_leagues.json (default: all)")
    ap.add_argument("--out-dir", default=str(ROOT), help="where to write (testing)")
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (testing)")
    args = ap.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))["leagues"]
    wanted = args.leagues or list(config)
    unknown = [x for x in wanted if x not in config]
    if unknown:
        sys.exit(f"Unknown league(s): {unknown}. Known: {list(config)}")
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)   # --out-dir to a fresh test folder

    failed = [lid for lid in wanted if not run_league(lid, config[lid], out_dir, today)]
    if failed:
        print(f"⚠️  Not updated: {failed} (existing files kept)")


if __name__ == "__main__":
    main()
