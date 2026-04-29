import requests
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
from pathlib import Path

# ── Your API key ─────────────────────────────────────────────
import os
API_KEY = os.environ.get("RAPIDAPI_KEY", "b15e332eecmsh80382e2738af2f5p1131e7jsn0d4914c2f5b7")

# ── Competitions to fetch ────────────────────────────────────
COMPETITIONS = [
    {
        "id": "9375",
        "name": "Women's Champions League",
        "emoji": "⚽",
        "filename": "womens_ucl.ics",
        "cal_name": "UEFA Women's Champions League 🏆"
    },
    {
        "id": "10270",
        "name": "EuroLeague Women",
        "emoji": "🏀",
        "filename": "euroleague_women.ics",
        "cal_name": "EuroLeague Women 🏀"
    },
    {
        "id": "10269",
        "name": "WNBA",
        "emoji": "🏀",
        "filename": "wnba.ics",
        "cal_name": "WNBA 🏀"
    },
]

# ── Fetch fixtures for one competition ───────────────────────
def fetch_fixtures(competition):
    url = "https://free-api-live-football-data.p.rapidapi.com/football-get-all-matches-by-league"
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": "free-api-live-football-data.p.rapidapi.com"
    }
    params = {"leagueid": competition["id"]}
    print(f"Fetching {competition['name']}...")
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    if "response" not in data:
        print(f"  ⚠️  No data returned for {competition['name']}")
        print(f"  API said: {data}")
        return []
    return data["response"]["matches"]

# ── Generate .ics file for one competition ───────────────────
def generate_ics(competition, matches):
    cal = Calendar()
    cal.add("prodid", f"-//HerFixtures//{competition['name']}//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("X-WR-CALNAME", competition["cal_name"])
    cal.add("X-WR-TIMEZONE", "UTC")

    added = 0
    for match in matches:
        try:
            status = match["status"]
            utc_time = datetime.fromisoformat(
                status["utcTime"].replace("Z", "+00:00")
            )
            home = match["home"]["name"]
            away = match["away"]["name"]

            event = Event()
            event.add("summary", f"{competition['emoji']} {home} vs {away}")
            event.add("dtstart", utc_time)
            event.add("dtend", utc_time + timedelta(hours=2))
            event.add("description", f"{competition['name']}\nCalendar by HerFixtures.com")
            event.add("location", competition["name"])
            event.add("uid", f"{match['id']}@herfixtures.com")

            cal.add_component(event)
            added += 1
        except Exception as e:
            print(f"  Skipped a match: {e}")

    output_path = Path(competition["filename"])
    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"  ✅ {added} matches → {competition['filename']}")

# ── Run for all competitions ─────────────────────────────────
print("🟢 HerFixtures — generating calendar feeds...\n")
for comp in COMPETITIONS:
    matches = fetch_fixtures(comp)
    if matches:
        generate_ics(comp, matches)

print("\n✅ All done! Files saved in:", Path(".").resolve())