#!/usr/bin/env python3
"""
HerFixtures — scores.json generator
Fetches WNBA, NWSL, and ICC Women's T20 WC results + upcoming fixtures
from ESPN public API and writes scores.json for the homepage scores strip.

Output shape:
{
  "updated": "2026-06-04T06:00:00Z",
  "competitions": {
    "wnba":           { "name": ..., "sport": ..., "slug": ..., "postgame": [], ... },
    "nwsl":           { ... },
    "icc-womens-t20": { ... }
  }
}
"""

import json
import requests
from datetime import datetime, timezone, timedelta, date

OUTPUT_FILE  = "scores.json"
WNBA_URL     = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
NWSL_URL     = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.nwsl"
ICC_URL      = "https://site.api.espn.com/apis/site/v2/sports/cricket/8634"
HEADERS      = {"User-Agent": "Mozilla/5.0"}
TODAY        = datetime.now(timezone.utc).date()
YESTERDAY    = TODAY - timedelta(days=1)
DAY_AFTER    = TODAY + timedelta(days=2)

# Hardcoded logo map by ESPN team ID — newer expansion teams use
# abbreviation-based slugs instead of numeric IDs
LOGO_OVERRIDES = {
    "129689": "https://a.espncdn.com/i/teamlogos/wnba/500/gs.png",   # GS Valkyries
    "132052": "https://a.espncdn.com/i/teamlogos/wnba/500/por.png",  # Portland Fire
    "131935": "https://a.espncdn.com/i/teamlogos/wnba/500/tor.png",  # Toronto Tempo
}


def fetch_scoreboard(base_url, date_from, date_to):
    try:
        r = requests.get(
            f"{base_url}/scoreboard",
            params={
                "dates": f"{date_from.strftime('%Y%m%d')}-{date_to.strftime('%Y%m%d')}",
                "limit": 50,
            },
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("events", [])
    except requests.exceptions.RequestException as e:
        print(f"    ⚠️  Scoreboard {date_from}–{date_to} error, skipping: {e}")
        return []


def fetch_scoreboard_single(base_url, d):
    """Fetch scoreboard for a single date — required for soccer endpoints that reject ranges."""
    try:
        r = requests.get(
            f"{base_url}/scoreboard",
            params={"dates": d.strftime("%Y%m%d"), "limit": 50},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("events", [])
    except requests.exceptions.RequestException as e:
        print(f"    ⚠️  Scoreboard {d} error, skipping: {e}")
        return []


def _parse_score(raw):
    """Return int for numeric scores (basketball/football), str for others (cricket)."""
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return raw


def team_data(competitor, sport_path="wnba"):
    team    = competitor.get("team", {})
    team_id = str(team.get("id", ""))
    if team_id in LOGO_OVERRIDES:
        logo = LOGO_OVERRIDES[team_id]
    elif team.get("logos"):
        logo = team["logos"][0].get("href", "")
    else:
        logo = f"https://a.espncdn.com/i/teamlogos/{sport_path}/500/{team_id}.png"
    return {
        "name":  team.get("shortDisplayName") or team.get("displayName", ""),
        "score": _parse_score(competitor.get("score")),
        "logo":  logo,
    }


def parse_event(event, label, sport_path="wnba"):
    comp   = event["competitions"][0]
    status = event["status"]["type"]
    state  = status.get("state", "pre")   # pre | in | post

    home_comp = next((t for t in comp["competitors"] if t["homeAway"] == "home"), None)
    away_comp = next((t for t in comp["competitors"] if t["homeAway"] == "away"), None)
    if not home_comp or not away_comp:
        return None

    home = team_data(home_comp, sport_path)
    away = team_data(away_comp, sport_path)

    try:
        ko = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    return {
        "state":   state,
        "ko":      ko,
        "league":  label,
        "home":    home,
        "away":    away,
    }


def kickoff_label(ko: datetime) -> str:
    """Human-readable kickoff time per Figma time rules."""
    now     = datetime.now(timezone.utc)
    diff_ms = (ko - now).total_seconds() * 1000
    diff_min = round(diff_ms / 60000)
    diff_hrs = round(diff_ms / 3600000)

    if diff_min < 60:
        return f"in {diff_min} min"
    if diff_ms < 86400000:
        return f"in {diff_hrs}h"

    h, m = ko.hour, ko.minute
    if h == 0  and m == 0: time_str = "midnight"
    elif h == 12 and m == 0: time_str = "midday"
    else:
        ampm  = "pm" if h >= 12 else "am"
        h12   = h % 12 or 12
        time_str = f"{h12}:{m:02d}{ampm}" if m else f"{h12}{ampm}"

    tomorrow = (now + timedelta(days=1)).date()
    if ko.date() == tomorrow:
        return f"Tomorrow @ {time_str}"

    days = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
    return f"{days[ko.weekday()]} @ {time_str}"


def process_league(base_url, label, home_first=False):
    """Fetch and classify events for one league.

    home_first=False (default): Away @ Home — away data in "home" slot.
                                Used for American sports (WNBA, NWSL).
    home_first=True:            Home first — no swap. Used for cricket
                                and other global conventions.
    """
    sport_path = {"WNBA": "wnba", "NWSL": "soccer"}.get(label, "cricket")

    if label == "WNBA":
        past_events   = fetch_scoreboard(base_url, YESTERDAY, TODAY)
        future_events = fetch_scoreboard(base_url, TODAY, DAY_AFTER)
        all_events = {e["id"]: e for e in past_events + future_events}
    else:
        # Soccer/cricket scoreboard rejects date ranges — fetch each day individually
        all_events = {}
        for day in [YESTERDAY, TODAY, TODAY + timedelta(days=1), DAY_AFTER]:
            for e in fetch_scoreboard_single(base_url, day):
                all_events[e["id"]] = e

    postgame, livegame, pregame = [], [], []

    for event in all_events.values():
        parsed = parse_event(event, label, sport_path)
        if not parsed:
            continue

        state = parsed["state"]
        home  = parsed["home"]
        away  = parsed["away"]
        ko    = parsed["ko"]

        if home_first:
            # Cricket convention: home team listed first, no swap
            card = {
                "league": parsed["league"],
                "home":   {"name": home["name"], "logo": home["logo"]},
                "away":   {"name": away["name"], "logo": away["logo"]},
            }
        else:
            # American sports convention: Away @ Home — away data in "home" slot
            card = {
                "league": parsed["league"],
                "home":   {"name": away["name"], "logo": away["logo"]},
                "away":   {"name": home["name"], "logo": home["logo"]},
            }

        if state == "post":
            if home_first:
                card["home"]["score"] = home["score"]
                card["away"]["score"] = away["score"]
                card["winner"] = "home" if home["score"] > away["score"] else "away"
            else:
                card["home"]["score"] = away["score"]
                card["away"]["score"] = home["score"]
                card["winner"] = "home" if away["score"] > home["score"] else "away"
            postgame.append(card)

        elif state == "in":
            if home_first:
                card["home"]["score"] = home["score"]
                card["away"]["score"] = away["score"]
            else:
                card["home"]["score"] = away["score"]
                card["away"]["score"] = home["score"]
            livegame.append(card)

        elif state == "pre":
            card["kickoff"]       = ko.strftime("%Y-%m-%dT%H:%M:%SZ")
            card["kickoff_label"] = kickoff_label(ko)
            pregame.append(card)

    postgame.sort(key=lambda x: x.get("kickoff", ""), reverse=True)
    pregame.sort(key=lambda x: x.get("kickoff", ""))

    return {"postgame": postgame, "livegame": livegame, "pregame": pregame}


LEAGUE_CONFIGS = [
    #  url        name                  sport         slug               home_first
    (WNBA_URL, "WNBA",               "basketball", "wnba",           False),
    (NWSL_URL, "NWSL",               "football",   "nwsl",           False),
    (ICC_URL,  "ICC Women's T20 WC", "cricket",    "icc-womens-t20", True),
]


def main():
    # Load existing scores.json so a failed competition can fall back to last-known-good
    existing_competitions = {}
    try:
        with open(OUTPUT_FILE) as f:
            existing_competitions = json.load(f).get("competitions", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    print(f"Fetching scores for strip ({YESTERDAY} → {DAY_AFTER})...")

    competitions = {}
    for base_url, name, sport, slug, home_first in LEAGUE_CONFIGS:
        try:
            result = process_league(base_url, name, home_first=home_first)
            competitions[slug] = {"name": name, "sport": sport, "slug": slug, **result}
            pg, lg, prg = result["postgame"], result["livegame"], result["pregame"]
            print(f"  {name}: {len(pg)} postgame, {len(lg)} live, {len(prg)} upcoming")
        except Exception as e:
            print(f"  ⚠️  {name} failed — keeping last-known-good data: {e}")
            if slug in existing_competitions:
                competitions[slug] = existing_competitions[slug]
            else:
                competitions[slug] = {
                    "name": name, "sport": sport, "slug": slug,
                    "postgame": [], "livegame": [], "pregame": [],
                }

    output = {
        "updated":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "competitions": competitions,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    total_pg  = sum(len(c["postgame"]) for c in competitions.values())
    total_lg  = sum(len(c["livegame"]) for c in competitions.values())
    total_prg = sum(len(c["pregame"])  for c in competitions.values())
    print(f"  → scores.json written: {total_pg} postgame, {total_lg} live, {total_prg} upcoming")


if __name__ == "__main__":
    main()
