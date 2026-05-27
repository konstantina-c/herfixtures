#!/usr/bin/env python3
"""
HerFixtures — WNBA individual team feed generator
Uses ESPN public API to generate one .ics file per team.
No API key required.
Runs alongside fetch_wnba.py — does not replace it.
"""

import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event
import uuid
import os

# ── Config ────────────────────────────────────────────────────────────────────
SEASON = 2026
SEASON_START = "20260508"
SEASON_END   = "20261031"

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
ESPN_HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; HerFixtures/1.0)"}

# ── Team map — ESPN ID → (display name, slug) ─────────────────────────────────
TEAMS = {
    20:     ("Atlanta Dream",          "atlanta_dream"),
    19:     ("Chicago Sky",            "chicago_sky"),
    18:     ("Connecticut Sun",        "connecticut_sun"),
    3:      ("Dallas Wings",           "dallas_wings"),
    129689: ("Golden State Valkyries", "golden_state_valkyries"),
    5:      ("Indiana Fever",          "indiana_fever"),
    17:     ("Las Vegas Aces",         "las_vegas_aces"),
    6:      ("Los Angeles Sparks",     "los_angeles_sparks"),
    8:      ("Minnesota Lynx",         "minnesota_lynx"),
    9:      ("New York Liberty",       "new_york_liberty"),
    11:     ("Phoenix Mercury",        "phoenix_mercury"),
    132052: ("Portland Fire",          "portland_fire"),
    14:     ("Seattle Storm",          "seattle_storm"),
    131935: ("Toronto Tempo",          "toronto_tempo"),
    16:     ("Washington Mystics",     "washington_mystics"),
}

# ── Fetch all season games (reuse same strategy as fetch_wnba.py) ─────────────
def fetch_all_games():
    games = []
    today = datetime.now(timezone.utc).date()
    season_start = datetime.strptime(SEASON_START, "%Y%m%d").date()
    season_end   = datetime.strptime(SEASON_END,   "%Y%m%d").date()

    # Past games: week by week for scores + broadcaster info
    if today > season_start:
        past_end = min(today, season_end)
        cursor = season_start
        while cursor < past_end:
            chunk_end = min(cursor + timedelta(days=6), past_end)
            params = {"dates": f"{cursor.strftime('%Y%m%d')}-{chunk_end.strftime('%Y%m%d')}", "limit": 50}
            try:
                r = requests.get(ESPN_SCOREBOARD, headers=ESPN_HEADERS, params=params, timeout=30)
                r.raise_for_status()
                for event in r.json().get("events", []):
                    game = parse_event(event)
                    if game:
                        games.append(game)
            except Exception as e:
                print(f"  ⚠ Week {cursor} failed: {e}")
            cursor = chunk_end + timedelta(days=1)

    # Future games: single wide call
    future_start = max(today, season_start)
    if future_start <= season_end:
        params = {"dates": f"{future_start.strftime('%Y%m%d')}-{season_end.strftime('%Y%m%d')}", "limit": 500}
        try:
            r = requests.get(ESPN_SCOREBOARD, headers=ESPN_HEADERS, params=params, timeout=30)
            r.raise_for_status()
            for event in r.json().get("events", []):
                game = parse_event(event)
                if game:
                    games.append(game)
        except Exception as e:
            print(f"  ⚠ Future fetch failed: {e}")

    # Deduplicate — past games (with scores) win
    seen = set()
    unique = []
    for g in games:
        if g["event_id"] not in seen:
            seen.add(g["event_id"])
            unique.append(g)

    return unique


def parse_event(event):
    comp = event["competitions"][0]
    competitors = comp["competitors"]
    home = next((c for c in competitors if c["homeAway"] == "home"), competitors[0])
    away = next((c for c in competitors if c["homeAway"] == "away"), competitors[1])

    home_id   = int(home["team"]["id"])
    away_id   = int(away["team"]["id"])
    home_name = home["team"]["displayName"]
    away_name = away["team"]["displayName"]

    date_str = event.get("date", "")
    if not date_str:
        return None

    game_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

    status_type  = event.get("status", {}).get("type", {})
    status_state = status_type.get("state", "pre")
    status_desc  = status_type.get("description", "Scheduled")
    completed    = status_state == "post"

    home_score = home.get("score", "")
    away_score = away.get("score", "")

    broadcasts = [n for b in comp.get("broadcasts", []) for n in b.get("names", [])]

    venue      = comp.get("venue", {})
    venue_name = venue.get("fullName", "")
    venue_city = venue.get("address", {}).get("city", "")

    tickets    = comp.get("tickets", [])
    ticket_url = tickets[0].get("links", [{}])[0].get("href", "") if tickets else ""

    return {
        "home_id":    home_id,
        "away_id":    away_id,
        "home_name":  home_name,
        "away_name":  away_name,
        "game_dt":    game_dt,
        "status":     status_desc,
        "completed":  completed,
        "home_score": home_score,
        "away_score": away_score,
        "broadcasts": broadcasts,
        "venue_name": venue_name,
        "venue_city": venue_city,
        "ticket_url": ticket_url,
        "event_id":   event.get("id", ""),
    }


# ── Build a single team calendar ──────────────────────────────────────────────
def build_team_calendar(team_id, team_name, games):
    cal = Calendar()
    cal.add("prodid", f"-//HerFixtures//WNBA 2026 {team_name}//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"{team_name} 2026 — HerFixtures")
    cal.add("x-wr-caldesc", f"{team_name} 2026 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    team_games = [g for g in games if g["home_id"] == team_id or g["away_id"] == team_id]

    for game in team_games:
        home      = game["home_name"]
        away      = game["away_name"]
        is_home   = game["home_id"] == team_id
        game_dt   = game["game_dt"]
        completed = game["completed"]
        home_score = game["home_score"]
        away_score = game["away_score"]
        broadcasts = game["broadcasts"]
        venue_name = game["venue_name"]
        venue_city = game["venue_city"]
        ticket_url = game["ticket_url"]
        event_id   = game["event_id"]

        # Title — home marker + score for finished games
        home_marker = " 🏠" if is_home else ""
        if completed and home_score and away_score:
            summary = f"🏀 {away} {away_score}–{home_score} {home} ✓{home_marker}"
        else:
            summary = f"🏀 {away} @ {home}{home_marker}"

        desc_lines = [
            f"WNBA 2026 · {'Home' if is_home else 'Away'} Game",
            f"{away} at {home}",
            f"Status: {game['status']}",
        ]
        if completed and home_score and away_score:
            desc_lines.append(f"Final score: {away} {away_score} – {home} {home_score}")
        if broadcasts:
            desc_lines.append(f"Watch: {' · '.join(broadcasts)}")
        if venue_name:
            loc = f"{venue_name}, {venue_city}" if venue_city else venue_name
            desc_lines.append(f"Venue: {loc}")
        if ticket_url:
            desc_lines.append(f"Tickets: {ticket_url}")
        desc_lines += ["", "Fixtures by HerFixtures.com — Women's Sports on Your Calendar"]

        location = f"{venue_name}, {venue_city}" if venue_name and venue_city else venue_name

        event = Event()
        event.add("uid", f"wnba-{event_id}-{team_id}@herfixtures.com")
        event.add("summary", summary)
        event.add("description", "\n".join(desc_lines))
        event.add("dtstart", game_dt)
        event.add("dtend", game_dt + timedelta(hours=2, minutes=30))
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("url", "https://herfixtures.com")
        if location:
            event.add("location", location)

        cal.add_component(event)

    return cal, len(team_games)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Fetching WNBA {SEASON} full season (ESPN API)...")
    all_games = fetch_all_games()
    print(f"  → {len(all_games)} total games fetched")
    print()

    for team_id, (team_name, slug) in TEAMS.items():
        output_file = f"wnba_{slug}.ics"
        cal, count = build_team_calendar(team_id, team_name, all_games)
        with open(output_file, "wb") as f:
            f.write(cal.to_ical())
        print(f"  ✓ {output_file:45} ({count} games)")

    print()
    print(f"Done — {len(TEAMS)} team feeds written.")

if __name__ == "__main__":
    main()
