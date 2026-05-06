#!/usr/bin/env python3
"""
HerFixtures — WNBA feed generator
Uses BallDontLie WNBA API to fetch fixtures and generate a .ics calendar file.
API key is read from the BALLDONTLIE_API_KEY environment variable.
"""

import os
import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event
import uuid

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("BALLDONTLIE_API_KEY")
BASE_URL = "https://api.balldontlie.io/wnba/v1"
OUTPUT_FILE = "wnba.ics"
SEASON = 2026

# Fetch games up to 60 days ahead and 7 days back
TODAY = datetime.now(timezone.utc).date()
DATE_FROM = (TODAY - timedelta(days=7)).isoformat()
DATE_TO = (TODAY + timedelta(days=60)).isoformat()

# ── Fetch games ───────────────────────────────────────────────────────────────
def fetch_games():
    if not API_KEY:
        raise ValueError("BALLDONTLIE_API_KEY environment variable not set.")

    headers = {"Authorization": API_KEY}
    params = {
        "seasons[]": SEASON,
        "start_date": DATE_FROM,
        "end_date": DATE_TO,
        "per_page": 100,
    }

    games = []
    cursor = None

    while True:
        if cursor:
            params["cursor"] = cursor

        response = requests.get(f"{BASE_URL}/games", headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        games.extend(data.get("data", []))

        # BallDontLie uses cursor-based pagination
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

    return games

# ── Build .ics ─────────────────────────────────────────────────────────────────
def build_calendar(games):
    cal = Calendar()
    cal.add("prodid", "-//HerFixtures//WNBA 2026//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "WNBA 2026 — HerFixtures")
    cal.add("x-wr-caldesc", "WNBA 2026 fixtures. Updated automatically by HerFixtures.com")
    cal.add("x-wr-timezone", "UTC")
    cal.add("refresh-interval;value=duration", "PT12H")
    cal.add("x-published-ttl", "PT12H")

    for game in games:
        try:
            home = game["home_team"]["full_name"]
            away = game["visitor_team"]["full_name"]
            date_str = game.get("date", "")

            if not date_str:
                continue

            # Parse date — API returns "2026-05-08" or full datetime string
            try:
                if "T" in date_str:
                    game_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    # Date only — default to TBD time, use noon UTC
                    game_dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
                        hour=0, minute=0, tzinfo=timezone.utc
                    )
            except ValueError:
                continue

            status = game.get("status", "")
            score = ""
            if game.get("home_team_score") and game.get("visitor_team_score"):
                score = f" ({away} {game['visitor_team_score']} – {home} {game['home_team_score']})"

            summary = f"🏀 {away} @ {home}{score}"
            description = (
                f"WNBA 2026 · Season Game\n"
                f"{away} at {home}\n"
                f"Status: {status}\n"
                f"\nFixtures by HerFixtures.com — Women's Sports on Your Calendar"
            )

            event = Event()
            event.add("uid", str(uuid.uuid4()))
            event.add("summary", summary)
            event.add("description", description)
            event.add("dtstart", game_dt)
            event.add("dtend", game_dt + timedelta(hours=2, minutes=30))
            event.add("dtstamp", datetime.now(timezone.utc))
            event.add("url", "https://herfixtures.com")

            cal.add_component(event)

        except (KeyError, TypeError):
            continue

    return cal

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Fetching WNBA {SEASON} games from {DATE_FROM} to {DATE_TO}...")
    games = fetch_games()
    print(f"  → {len(games)} games fetched")

    cal = build_calendar(games)

    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())

    print(f"  → {OUTPUT_FILE} written successfully")

if __name__ == "__main__":
    main()
