#!/usr/bin/env python3
"""
HerFixtures — scores.json generator
Fetches WNBA and NWSL results + upcoming fixtures from ESPN public API
and writes scores.json for the homepage scores strip.

Output shape:
{
  "updated": "2026-06-03T12:00:00Z",
  "postgame": [ { league, home, away } ],   # yesterday's completed games
  "livegame":  [ { league, home, away } ],  # currently live
  "pregame":   [ { league, kickoff, kickoff_label, home, away } ]  # next 2 days
}
"""

import json
import requests
from datetime import datetime, timezone, timedelta, date

OUTPUT_FILE  = "scores.json"
WNBA_URL     = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"
NWSL_URL     = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.nwsl"
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


def fetch_scoreboard_single(base_url, d):
    """Fetch scoreboard for a single date — required for soccer endpoints that reject ranges."""
    r = requests.get(
        f"{base_url}/scoreboard",
        params={"dates": d.strftime("%Y%m%d"), "limit": 50},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("events", [])


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
        "score": int(competitor["score"]) if competitor.get("score") not in (None, "") else None,
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


def process_league(base_url, label):
    sport_path = "wnba" if label == "WNBA" else "soccer"

    if label == "WNBA":
        past_events   = fetch_scoreboard(base_url, YESTERDAY, TODAY)
        future_events = fetch_scoreboard(base_url, TODAY, DAY_AFTER)
        all_events = {e["id"]: e for e in past_events + future_events}
    else:
        # Soccer scoreboard rejects date ranges — fetch each day individually
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

        # American sports convention: Away @ Home — away team listed first
        card = {
            "league": parsed["league"],
            "home":   {"name": away["name"], "logo": away["logo"]},
            "away":   {"name": home["name"], "logo": home["logo"]},
        }

        if state == "post":
            # Winner is still determined by actual scores
            card["home"]["score"] = away["score"]
            card["away"]["score"] = home["score"]
            # Mark winner on the away-first display
            card["winner"] = "home" if away["score"] > home["score"] else "away"
            postgame.append(card)

        elif state == "in":
            card["home"]["score"] = away["score"]
            card["away"]["score"] = home["score"]
            livegame.append(card)

        elif state == "pre":
            card["kickoff"]       = ko.strftime("%Y-%m-%dT%H:%M:%SZ")
            card["kickoff_label"] = kickoff_label(ko)
            pregame.append(card)

    return postgame, livegame, pregame


def main():
    print(f"Fetching scores for strip ({YESTERDAY} → {DAY_AFTER})...")

    all_postgame, all_livegame, all_pregame = [], [], []

    for base_url, label in [(WNBA_URL, "WNBA"), (NWSL_URL, "NWSL")]:
        pg, lg, prg = process_league(base_url, label)
        all_postgame.extend(pg)
        all_livegame.extend(lg)
        all_pregame.extend(prg)
        print(f"  {label}: {len(pg)} postgame, {len(lg)} live, {len(prg)} upcoming")

    # Sort: postgame newest first, pregame soonest first
    all_postgame.sort(key=lambda x: x.get("kickoff", ""), reverse=True)
    all_pregame.sort(key=lambda x: x.get("kickoff", ""))

    output = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "postgame": all_postgame,
        "livegame": all_livegame,
        "pregame":  all_pregame,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"  → scores.json written: {len(all_postgame)} postgame, {len(all_livegame)} live, {len(all_pregame)} upcoming")


if __name__ == "__main__":
    main()
