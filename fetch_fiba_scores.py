#!/usr/bin/env python3
"""
Fetch FIBA WWC 2026 final scores from ESPN, regenerate all FIBA .ics feeds
with scores appended to completed-game summaries, and patch fiba-wwc-2026
into scores.json for the homepage scores strip.

Run after fetch_scores_json.py so the FIBA entry is not overwritten.
"""

from __future__ import annotations

import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT            = Path(__file__).resolve().parent
FIXTURES_FILE   = ROOT / "feeds" / "fiba-wwc-2026" / "fixtures.json"
ALL_ICS_FILE    = ROOT / "feeds" / "fiba-wwc-2026" / "all.ics"
SCORES_JSON     = ROOT / "scores.json"
ESPN_BASE       = "https://site.api.espn.com/apis/site/v2/sports/basketball/fiba"
TOURNAMENT_START = "20260904"
DTSTAMP         = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# ESPN shortDisplayName → fixtures.json team name (only the two mismatches)
ESPN_TO_FIXTURE: dict[str, str] = {
    "United States": "USA",
    "South Korea":   "Korea",
}

FIBA_TEAMS = [
    ("Japan",        "japan"),
    ("Mali",         "mali"),
    ("Spain",        "spain"),
    ("Germany",      "germany"),
    ("Korea",        "korea"),
    ("Nigeria",      "nigeria"),
    ("Hungary",      "hungary"),
    ("France",       "france"),
    ("Australia",    "australia"),
    ("Puerto Rico",  "puerto_rico"),
    ("Belgium",      "belgium"),
    ("Türkiye",      "turkiye"),
    ("USA",          "usa"),
    ("China",        "china"),
    ("Czechia",      "czechia"),
    ("Italy",        "italy"),
]


# ---------------------------------------------------------------------------
# ICS helpers (mirrors generate_fiba_ics.py)
# ---------------------------------------------------------------------------

def escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> list[str]:
    """RFC 5545 line folding at 75 UTF-8 octets."""
    parts: list[str] = []
    current = ""
    limit = 75
    for char in line:
        if len((current + char).encode("utf-8")) > limit:
            parts.append(current)
            current = " " + char
            limit = 75
        else:
            current += char
    parts.append(current)
    return parts


def stage_label(fixture: dict) -> str:
    stage = fixture["stage"]
    if stage == "group":
        return f"Group {fixture['group']}"
    return {
        "qualification": "Qualification to Quarter-Finals",
        "quarter-final": "Quarter-Final",
        "semi-final":    "Semi-Final",
        "third-place":   "Third Place Game",
        "final":         "Final",
    }[stage]


def ticket_product_key(fixture: dict) -> str:
    if fixture.get("ticket_product"):
        return fixture["ticket_product"]
    if fixture["stage"] == "group":
        return f"{fixture['venue']}-sessions"
    return "berlin-arena-final-phase"


def participant(fixture: dict, side: str) -> str:
    """Display name — joins slash-separated options when multiple teams are possible."""
    opts = fixture.get(f"{side}_options")
    return "/".join(opts) if opts else fixture[side]


def is_placeholder(fixture: dict) -> bool:
    """True if home or away still contains a 'Winner/Loser/Group' token."""
    combined = fixture["home"] + fixture["away"]
    return any(t in combined for t in ("Winner", "Loser", "Group"))


# ---------------------------------------------------------------------------
# ESPN data fetch
# ---------------------------------------------------------------------------

def fetch_espn() -> dict[frozenset, dict]:
    """
    Returns dict keyed by frozenset{fixture_name_a, fixture_name_b}:
      {
        "date": "2026-09-04",
        "state": "post" | "in" | "pre",
        "completed": bool,
        "teams": {fixture_name: {"score": int, "logo": str}},
      }
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        r = requests.get(
            f"{ESPN_BASE}/scoreboard",
            params={"dates": f"{TOURNAMENT_START}-{today}", "limit": 100},
            timeout=10,
        )
        r.raise_for_status()
        events = r.json().get("events", [])
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  ESPN fetch failed — feeds will regenerate without scores: {e}")
        return {}

    results: dict[frozenset, dict] = {}
    for event in events:
        comp   = event["competitions"][0]
        status = event["status"]["type"]
        state  = status.get("state", "pre")

        teams: dict[str, dict] = {}
        for c in comp.get("competitors", []):
            espn_name    = c["team"].get("shortDisplayName") or c["team"].get("displayName", "")
            fixture_name = ESPN_TO_FIXTURE.get(espn_name, espn_name)
            score_raw    = c.get("score") or "0"
            try:
                score = int(score_raw)
            except (ValueError, TypeError):
                score = 0
            teams[fixture_name] = {
                "score": score,
                "logo":  c["team"].get("logo", ""),
            }

        key = frozenset(teams.keys())
        results[key] = {
            "date":      event.get("date", "")[:10],
            "state":     state,
            "completed": status.get("completed", False),
            "teams":     teams,
        }

    return results


def lookup_score(fixture: dict, espn: dict) -> tuple[int, int] | None:
    """Return (home_score, away_score) if the game is final, else None."""
    home_cands = fixture.get("home_options", [fixture["home"]])
    away_cands = fixture.get("away_options", [fixture["away"]])
    for h in home_cands:
        for a in away_cands:
            result = espn.get(frozenset({h, a}))
            if result and result["state"] == "post" and result["completed"]:
                t = result["teams"]
                return t.get(h, {}).get("score", 0), t.get(a, {}).get("score", 0)
    return None


# ---------------------------------------------------------------------------
# ICS generation
# ---------------------------------------------------------------------------

def _build_event(fixture: dict, espn: dict, competition: dict, tz: ZoneInfo,
                 duration: timedelta, venues: dict, ticket_products: dict) -> list[str]:
    """Return VEVENT lines for one fixture (score-aware)."""
    home_display = participant(fixture, "home")
    away_display = participant(fixture, "away")

    start_local = datetime.fromisoformat(
        f"{fixture['date']}T{fixture['time']}:00"
    ).replace(tzinfo=tz)
    end_local = start_local + duration
    start_utc = start_local.astimezone(timezone.utc)
    end_utc   = end_local.astimezone(timezone.utc)

    score_result = lookup_score(fixture, espn)
    if score_result:
        h_score, a_score = score_result
        summary = f"🏀 {home_display} vs {away_display} ({h_score}–{a_score})"
    else:
        summary = f"🏀 {home_display} vs {away_display}"

    label   = stage_label(fixture)
    tickets = ticket_products[ticket_product_key(fixture)]
    description = (
        f"FIBA Women's Basketball World Cup 2026\\n{escape(label)} - Game {fixture['game']}\\n"
        f"{escape(home_display)} vs {escape(away_display)}\\n"
        f"{escape(tickets['label'])}: {escape(tickets['url'])}\\n\\n"
        "Fixtures by HerFixtures.com - Women's Sports on Your Calendar"
    )

    return [
        "BEGIN:VEVENT",
        f"UID:fiba-wwc-2026-{fixture['game']:03d}@herfixtures.com",
        f"DTSTAMP:{DTSTAMP}",
        f"SEQUENCE:{fixture.get('sequence', 0)}",
        f"DTSTART:{start_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{end_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{escape(summary)}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{escape(venues[fixture['venue']])}",
        f"URL:{competition['source_url']}",
        f"STATUS:{'TENTATIVE' if is_placeholder(fixture) else 'CONFIRMED'}",
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]


def _ics_header(lines: list[str]) -> str:
    return "\r\n".join(part for line in lines for part in fold(line)) + "\r\n"


def build_all_ics(data: dict, espn: dict) -> tuple[str, list[int], int]:
    """Build combined feed. Returns (ics_str, omitted_game_numbers, scored_count)."""
    competition     = data["competition"]
    tz              = ZoneInfo(competition["timezone"])
    duration        = timedelta(minutes=competition["default_duration_minutes"])
    venues          = data["venues"]
    ticket_products = data["ticket_products"]

    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//HerFixtures//FIBA Women's Basketball World Cup 2026//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:FIBA Women's Basketball World Cup 2026 - HerFixtures",
        "X-WR-CALDESC:Official FIBA WWC 2026 fixtures in Berlin. Maintained by HerFixtures.com.",
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    omitted: list[int] = []
    scored = 0

    for fixture in data["fixtures"]:
        if fixture["time"] is None:
            omitted.append(fixture["game"])
            continue
        event_lines = _build_event(fixture, espn, competition, tz, duration, venues, ticket_products)
        lines.extend(event_lines)
        if lookup_score(fixture, espn):
            scored += 1

    lines.append("END:VCALENDAR")
    return _ics_header(lines), omitted, scored


def build_team_ics(data: dict, espn: dict, team_name: str) -> tuple[str, int]:
    """Build per-team feed. Returns (ics_str, event_count)."""
    competition     = data["competition"]
    tz              = ZoneInfo(competition["timezone"])
    duration        = timedelta(minutes=competition["default_duration_minutes"])
    venues          = data["venues"]
    ticket_products = data["ticket_products"]

    lines = [
        "BEGIN:VCALENDAR",
        f"PRODID:-//HerFixtures//FIBA Women's Basketball World Cup 2026 {team_name}//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{team_name} — FIBA WWC 2026 — HerFixtures",
        f"X-WR-CALDESC:{team_name} FIBA Women's Basketball World Cup 2026 fixtures."
        " Updated automatically by HerFixtures.com.",
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    count = 0
    for fixture in data["fixtures"]:
        if fixture["time"] is None:
            continue
        home_cands = fixture.get("home_options", [fixture["home"]])
        away_cands = fixture.get("away_options", [fixture["away"]])
        if team_name not in home_cands + away_cands:
            continue
        lines.extend(_build_event(fixture, espn, competition, tz, duration, venues, ticket_products))
        count += 1

    lines.append("END:VCALENDAR")
    return _ics_header(lines), count


# ---------------------------------------------------------------------------
# scores.json entry
# ---------------------------------------------------------------------------

def _kickoff_label(ko: datetime) -> str:
    now      = datetime.now(timezone.utc)
    diff_ms  = (ko - now).total_seconds() * 1000
    diff_min = round(diff_ms / 60000)
    diff_hrs = round(diff_ms / 3600000)
    if diff_min < 60:
        return f"in {diff_min} min"
    if diff_ms < 86_400_000:
        return f"in {diff_hrs}h"
    h, m = ko.hour, ko.minute
    ampm  = "pm" if h >= 12 else "am"
    h12   = h % 12 or 12
    time_str = f"{h12}:{m:02d}{ampm}" if m else f"{h12}{ampm}"
    tomorrow = (now + timedelta(days=1)).date()
    if ko.date() == tomorrow:
        return f"Tomorrow @ {time_str}"
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return f"{days[ko.weekday()]} @ {time_str}"


def build_scores_entry(data: dict, espn: dict) -> dict:
    """Build the fiba-wwc-2026 competitions entry for scores.json."""
    tz  = ZoneInfo("Europe/Berlin")
    now = datetime.now(timezone.utc)

    postgame: list[dict] = []
    livegame: list[dict] = []
    pregame:  list[dict] = []

    for fixture in data["fixtures"]:
        if fixture["time"] is None:
            continue

        home_display = participant(fixture, "home")
        away_display = participant(fixture, "away")
        home_cands   = fixture.get("home_options", [fixture["home"]])
        away_cands   = fixture.get("away_options", [fixture["away"]])

        # Locate ESPN result for this fixture
        espn_result: dict | None = None
        for h in home_cands:
            for a in away_cands:
                r = espn.get(frozenset({h, a}))
                if r:
                    espn_result = r
                    break
            if espn_result:
                break

        start_local = datetime.fromisoformat(
            f"{fixture['date']}T{fixture['time']}:00"
        ).replace(tzinfo=tz)
        start_utc = start_local.astimezone(timezone.utc)
        state     = espn_result["state"] if espn_result else ("post" if start_utc < now else "pre")

        # Logos from ESPN (national team flag format)
        home_logo, away_logo = "", ""
        if espn_result:
            t = espn_result["teams"]
            for h in home_cands:
                if h in t:
                    home_logo = t[h].get("logo", "")
                    break
            for a in away_cands:
                if a in t:
                    away_logo = t[a].get("logo", "")
                    break

        card: dict = {
            "league": "FIBA WWC 2026",
            "home":   {"name": home_display, "logo": home_logo},
            "away":   {"name": away_display, "logo": away_logo},
        }

        if state == "post" and espn_result and espn_result["completed"]:
            t = espn_result["teams"]
            for h in home_cands:
                if h in t:
                    card["home"]["score"] = t[h]["score"]
                    break
            for a in away_cands:
                if a in t:
                    card["away"]["score"] = t[a]["score"]
                    break
            h_sc = card["home"].get("score", 0)
            a_sc = card["away"].get("score", 0)
            if isinstance(h_sc, int) and isinstance(a_sc, int):
                card["winner"] = "home" if h_sc > a_sc else "away"
            postgame.append(card)

        elif state == "in" and espn_result:
            t = espn_result["teams"]
            for h in home_cands:
                if h in t:
                    card["home"]["score"] = t[h]["score"]
                    break
            for a in away_cands:
                if a in t:
                    card["away"]["score"] = t[a]["score"]
                    break
            livegame.append(card)

        else:
            card["kickoff"]       = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            card["kickoff_label"] = _kickoff_label(start_utc)
            pregame.append(card)

    return {
        "name":     "FIBA WWC 2026",
        "sport":    "basketball",
        "slug":     "fiba-wwc-2026",
        "postgame": postgame,
        "livegame": livegame,
        "pregame":  pregame,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))

    print("Fetching FIBA WWC 2026 scores from ESPN...")
    espn = fetch_espn()
    n_post = sum(1 for v in espn.values() if v["state"] == "post")
    n_live = sum(1 for v in espn.values() if v["state"] == "in")
    n_pre  = sum(1 for v in espn.values() if v["state"] == "pre")
    print(f"  ESPN: {n_post} completed, {n_live} live, {n_pre} upcoming")

    # Combined feed
    calendar, omitted, scored = build_all_ics(data, espn)
    ALL_ICS_FILE.write_text(calendar, encoding="utf-8", newline="")
    total = 36 - len(omitted)
    print(f"Wrote all.ics: {total} events ({scored} with final scores); omitted: {omitted}")

    # Per-team feeds
    print("Generating team feeds...")
    for team_name, slug in FIBA_TEAMS:
        out = ROOT / f"fiba_wwc_{slug}.ics"
        cal, count = build_team_ics(data, espn, team_name)
        out.write_text(cal, encoding="utf-8", newline="")
        print(f"  ✓ fiba_wwc_{slug}.ics ({count} events)")

    # Patch scores.json — run after fetch_scores_json.py so we add, not replace
    try:
        existing = json.loads(SCORES_JSON.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"updated": DTSTAMP, "competitions": {}}

    existing["competitions"]["fiba-wwc-2026"] = build_scores_entry(data, espn)
    existing["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    SCORES_JSON.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    entry = existing["competitions"]["fiba-wwc-2026"]
    print(
        f"Patched scores.json: fiba-wwc-2026 → "
        f"{len(entry['postgame'])} postgame, "
        f"{len(entry['livegame'])} live, "
        f"{len(entry['pregame'])} upcoming"
    )


if __name__ == "__main__":
    main()
