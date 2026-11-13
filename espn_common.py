"""Shared helpers for every HerFixtures fetch script.

1. fetch_days()       — ESPN scoreboard, one request per day.
   Since 2026-09-15 ESPN answers 400 Bad Request to ANY multi-day `dates=A-B`
   range (all sports). Single days still work. Responses are cached on disk for
   the length of one refresh run, so a league script and its team script share
   the same fetch instead of doubling the load on ESPN.

2. is_placeholder()   — true for "TBD vs TBD"-style events (never publish fake games).

3. safe_write_ics()   — shrink guard. Refuses to overwrite an .ics file when the
   new version has fewer than 50% of the existing file's events (the Liga F bug:
   240 events silently replaced by 1). Logs a GitHub Actions warning instead.
   Legitimate big shrinks (e.g. a new season starting): set
   HERFIXTURES_ALLOW_SHRINK=<filename>[,<filename>...] or "all" for one run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

SHRINK_LIMIT = 0.5
CACHE_DIR = Path(os.environ.get("HERFIXTURES_ESPN_CACHE", Path(tempfile.gettempdir()) / "herfixtures-espn-cache"))
CACHE_TTL_SECONDS = 3 * 3600  # one refresh run, never across runs
PLACEHOLDER_NAMES = {"tbd", "tba", "to be determined", "to be announced"}


# ── ESPN day-by-day fetch ─────────────────────────────────────────────────────

def _cache_path(url: str, day: str) -> Path:
    return CACHE_DIR / (hashlib.sha1(f"{url}|{day}".encode()).hexdigest() + ".json")


def _get_day(url: str, day: str) -> tuple[str, list | None]:
    p = _cache_path(url, day)
    if p.exists() and time.time() - p.stat().st_mtime < CACHE_TTL_SECONDS:
        try:
            return day, json.loads(p.read_text())
        except ValueError:
            pass
    for attempt in range(3):
        try:
            r = requests.get(url, params={"dates": day, "limit": 100}, timeout=15)
            if r.status_code == 200:
                events = r.json().get("events", [])
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(events))
                return day, events
            if r.status_code < 500 and r.status_code != 429:
                break  # 4xx other than rate limit: retrying won't help
        except requests.exceptions.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return day, None


def fetch_days(scoreboard_url: str, start: date, end: date, *, max_fail_ratio: float = 0.05, workers: int = 6) -> dict:
    """All events between start and end (inclusive), keyed by ESPN event id.

    Raises RuntimeError if more than max_fail_ratio of the days failed, so the
    caller never writes a feed built from a partial season.
    """
    days = [(start + timedelta(n)).strftime("%Y%m%d") for n in range((end - start).days + 1)]
    events, failed = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for day, day_events in pool.map(lambda d: _get_day(scoreboard_url, d), days):
            if day_events is None:
                failed.append(day)
                continue
            for ev in day_events:
                if ev.get("id"):
                    events[ev["id"]] = ev
    if days and len(failed) / len(days) > max_fail_ratio:
        raise RuntimeError(f"{len(failed)}/{len(days)} days failed (e.g. {failed[:3]}) — refusing to build a partial feed")
    if failed:
        print(f"  ⚠️  {len(failed)} of {len(days)} days failed and were skipped: {failed[:5]}")
    return events


# ── Placeholder filter ────────────────────────────────────────────────────────

def is_placeholder(event: dict) -> bool:
    try:
        comps = event["competitions"][0]["competitors"]
    except (KeyError, IndexError, TypeError):
        return True
    for c in comps:
        team = c.get("team") or {}
        names = {str(team.get(k, "")).strip().lower() for k in ("displayName", "name", "abbreviation")}
        if names & PLACEHOLDER_NAMES or names <= {""}:
            return True
    return False


# ── Shrink guard ──────────────────────────────────────────────────────────────

def count_events(data: bytes | str) -> int:
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    return len(re.findall(r"^BEGIN:VEVENT", data, re.M))


def safe_write_ics(path: str | os.PathLike, data: bytes | str) -> bool:
    """Write an .ics file unless it would shrink below SHRINK_LIMIT of the current one."""
    path = Path(path)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    new_count = count_events(payload)
    old_count = count_events(path.read_bytes()) if path.exists() else 0

    allow = {x.strip() for x in os.environ.get("HERFIXTURES_ALLOW_SHRINK", "").split(",") if x.strip()}
    allowed = "all" in allow or path.name in allow
    if old_count and new_count < old_count * SHRINK_LIMIT and not allowed:
        msg = (f"{path.name}: new version has {new_count} events vs {old_count} now "
               f"(below {int(SHRINK_LIMIT * 100)}%) — NOT written, existing file kept. "
               f"If this is intended (e.g. new season), rerun with HERFIXTURES_ALLOW_SHRINK={path.name}")
        print(f"::warning title=Shrink guard::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"  🛑 {msg}")
        return False
    path.write_bytes(payload)
    return True
