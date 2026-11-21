"""API-Football (api-sports.io) source for the HerFixtures feed engine.

A league in feeds/espn_leagues.json with "source": "api-football" is fetched
here instead of from ESPN. The rest of the engine (calendar building, team
feeds, kept past games, shrink guard) is shared.

- Licensed source: paid plan on Konstantina's API-Football account. The key
  comes from the APIFOOTBALL_KEY environment variable (GitHub secret in
  refresh.yml). It is never written to the repo or printed.
- One request per league per run (the whole season), retried; any failure
  means "keep the existing feeds".
- Time TBC: API-Football has no "time not confirmed" flag for most leagues.
  It gives unconfirmed games a placeholder kick-off, typically the same time
  for every game of a round. Two rules mark a game "(time TBC)":
    1. status TBD ("Time To Be Defined")
    2. a future round where at least `api_football.uniform_min` games (default 4)
       share one identical kick-off and that kick-off is more than 7 days away.
       Set uniform_min to 0 for leagues with a real standard kick-off slot.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://v3.football.api-sports.io"
DONE = {"FT", "AET", "PEN", "AWD", "WO"}
DROP = {"CANC", "ABD"}  # cancelled / abandoned: never publish
FOOTER = "\nFixtures by HerFixtures.com — Women's Sports on Your Calendar"


class SourceError(RuntimeError):
    pass


def fetch_fixtures(league_id: int, season: int) -> list[dict]:
    key = os.environ.get("APIFOOTBALL_KEY", "").strip()
    if not key:
        raise SourceError("APIFOOTBALL_KEY is not set")
    last = ""
    for attempt in range(3):
        try:
            r = requests.get(f"{BASE}/fixtures", params={"league": league_id, "season": season},
                             headers={"x-apisports-key": key}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                errors = data.get("errors")
                if errors:
                    raise SourceError(f"API-Football error: {errors}")
                return data.get("response", [])
            last = f"HTTP {r.status_code}"
        except requests.exceptions.RequestException as e:
            last = type(e).__name__
        time.sleep(2 * (attempt + 1))
    raise SourceError(f"API-Football request failed ({last})")


def placeholder_ids(fixtures: list[dict], now: datetime, min_games: int = 4) -> set[int]:
    """Fixture ids whose kick-off looks like a placeholder (see module doc, rule 2).

    min_games <= 0 turns the rule off: some leagues really do play most of a
    round at one standard time (Eredivisie Women: Sunday 16:45, confirmed by ESPN).
    """
    if min_games <= 0:
        return set()
    by_round: dict[str, list[dict]] = defaultdict(list)
    for f in fixtures:
        if f["fixture"]["status"]["short"] in ("NS", "TBD"):
            by_round[f["league"]["round"]].append(f)
    out: set[int] = set()
    horizon = now + timedelta(days=7)
    for games in by_round.values():
        times = defaultdict(list)
        for f in games:
            times[f["fixture"]["date"]].append(f)
        for kickoff, same in times.items():
            if len(same) >= min_games and datetime.fromisoformat(kickoff) > horizon:
                out.update(f["fixture"]["id"] for f in same)
    return out


def team_name(team: dict, league: dict) -> str:
    """Our display name: from the config team list, else API name without the ' W' suffix."""
    cfg = league.get("teams", {}).get(str(team.get("id")))
    if cfg:
        return cfg[0]
    name = " ".join(str(team.get("name", "")).split())
    return name[:-2] if name.endswith(" W") else name


def parse(fx: dict, league: dict, placeholders: set[int], first_line: str | None = None) -> dict | None:
    """API-Football fixture -> the engine's plain game dict (same shape as the ESPN parser)."""
    try:
        f, teams = fx["fixture"], fx["teams"]
        status = f["status"]["short"]
        if status in DROP:
            return None
        h, a = team_name(teams["home"], league), team_name(teams["away"], league)
        if not h or not a:
            return None
        start = datetime.fromisoformat(f["date"]).astimezone(timezone.utc)
        done = status in DONE
        time_tbc = not done and (status == "TBD" or f["id"] in placeholders)
        goals = fx.get("goals") or {}

        def g(v):
            return "?" if v is None else str(v)

        if league["order"] == "home_vs_away":
            score = f" ({g(goals.get('home'))}–{g(goals.get('away'))})" if done else ""
            title = line2 = f"{h} vs {a}"
        else:
            score = f" ({g(goals.get('away'))}–{g(goals.get('home'))})" if done else ""
            title, line2 = f"{a} @ {h}", f"{a} at {h}"
        summary = f"{league['emoji']} {title}{score}"
        if status == "PST":
            summary += " (postponed)"
        elif time_tbc:
            summary += " (time TBC)"

        desc = [first_line or league["title"], line2, f"Status: {f['status'].get('long', '')}"]
        if time_tbc:
            desc.append("Kick-off time not confirmed yet. Your calendar updates automatically once it is.")
        venue = f.get("venue") or {}
        if venue.get("name"):
            desc.append(f"Venue: {venue['name']}{', ' + venue['city'] if venue.get('city') else ''}")
        desc.append(FOOTER)

        return {
            "uid": f"{league['uid_prefix']}-{f['id']}@herfixtures.com",
            "summary": summary,
            "description": "\n".join(desc),
            "start": start,
            "minutes": league.get("match_minutes", 120),
            "time_tbc": time_tbc,
            "url": "https://herfixtures.com",
            "team_ids": {str(teams["home"].get("id", "")), str(teams["away"].get("id", ""))},
        }
    except (KeyError, TypeError, ValueError) as e:
        print(f"  ⚠️  Skipping malformed fixture {fx.get('fixture', {}).get('id', '?')}: {e}")
        return None
