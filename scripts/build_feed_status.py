#!/usr/bin/env python3
"""Work out each competition's homepage badge from its season dates and feed, write feed_status.json.

Hand-typed badges went stale every season change (7 of 8 were wrong on Nov 12, 2026).
This runs in every refresh, so badges follow the calendar on their own.

Rules, per feed in feeds/manifest.json (first match wins):
  1. an active "highlight" (manifest, from..until)  -> its text/style   e.g. "Playoffs · Final 21 Nov"
  2. before season start                            -> "Starts 3 January"            (live)
  3. in a declared break                            -> "Back 3 February" / "Winter break" (offseason)
  4. during the season                              -> "Season in progress"          (live)
  5. after the season, kind=tournament              -> "Tournament complete"         (offseason)
  6. after the season, kind=league                  -> "Off-season"                  (offseason)

Usage: python3 scripts/build_feed_status.py [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "feeds" / "manifest.json"
OUTPUT = ROOT / "feed_status.json"


def d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def human(day: date, with_year: bool = False) -> str:
    return f"{day.day} {day.strftime('%B')}" + (f" {day.year}" if with_year else "")


def event_dates(ics: Path) -> list[date]:
    if not ics.exists():
        return []
    text = re.sub(r"\r?\n[ \t]", "", ics.read_text(encoding="utf-8"))
    return sorted(datetime.strptime(m, "%Y%m%d").date() for m in re.findall(r"^DTSTART[^:\n]*:(\d{8})", text, re.M))


def status(feed: dict, today: date) -> dict:
    events = event_dates(ROOT / feed["ics"])
    upcoming = [e for e in events if e >= today]
    nxt = upcoming[0] if upcoming else None
    start, end = d(feed["season"]["start"]), d(feed["season"]["end"])
    base = {"next_game": nxt.isoformat() if nxt else None, "upcoming_games": len(upcoming)}

    for h in feed.get("highlights", []):
        if d(h["from"]) <= today <= d(h["until"]):
            return {**base, "text": h["text"], "style": h.get("style", "live"), "rule": "highlight"}
    if today < start:
        first = nxt or start
        return {**base, "text": f"Starts {human(first, first.year != today.year)}", "style": "live", "rule": "before-season"}
    if today <= end:
        for b in feed.get("breaks", []):
            if d(b["start"]) <= today <= d(b["end"]):
                text = f"Back {human(nxt)}" if nxt else "Winter break"
                return {**base, "text": text, "style": "offseason", "rule": "break"}
        return {**base, "text": "Season in progress", "style": "live", "rule": "in-season"}
    if feed.get("kind") == "tournament":
        return {**base, "text": "Tournament complete", "style": "offseason", "rule": "after-tournament"}
    return {**base, "text": "Off-season", "style": "offseason", "rule": "off-season"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (testing)")
    ap.add_argument("--print-only", action="store_true", help="don't write feed_status.json")
    args = ap.parse_args()
    today = d(args.today) if args.today else datetime.now(timezone.utc).date()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    feeds = {f["id"]: status(f, today) for f in manifest["feeds"]}
    for fid, s in feeds.items():
        print(f"  {fid:20} {s['text']:28} ({s['style']}, {s['rule']}, next {s['next_game']})")
    if args.print_only:
        return
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "for_date": today.isoformat(), "feeds": feeds}
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.name}")


if __name__ == "__main__":
    main()
