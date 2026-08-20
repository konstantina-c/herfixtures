#!/usr/bin/env python3
"""Dependency-free integrity checks for the generated FIBA calendar."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT / "public" / "feeds" / "fiba-wwc-2026" / "fixtures.json").read_text(encoding="utf-8"))
ics = (ROOT / "public" / "feeds" / "fiba-wwc-2026" / "all.ics").read_text(encoding="utf-8")
unfolded = ics.replace("\n ", "")

assert len(data["fixtures"]) == 36
assert [f["game"] for f in data["fixtures"]] == list(range(1, 37))
assert ics.startswith("BEGIN:VCALENDAR\n") or ics.startswith("BEGIN:VCALENDAR\r\n")
assert ics.rstrip().endswith("END:VCALENDAR")
assert ics.count("BEGIN:VEVENT") == 30
assert ics.count("END:VEVENT") == 30
assert ics.count("UID:fiba-wwc-2026-") == 30
assert len({line for line in ics.splitlines() if line.startswith("UID:")}) == 30
for omitted in (25, 26, 27, 28, 33, 34):
    assert f"UID:fiba-wwc-2026-{omitted:03d}@herfixtures.com" not in ics
for included in (*range(1, 25), *range(29, 33), 35, 36):
    assert f"UID:fiba-wwc-2026-{included:03d}@herfixtures.com" in ics
assert "DTSTART:20260904T093000Z" in ics
assert "TZID=" not in ics
assert "19700101" not in ics
assert ics.count("Official tickets for this session:") == 24
assert ics.count("Official tickets for this game day:") == 6
assert "fiba-womens-basketball-world-cup-2026-berlin-arena-sessions-3961330" in unfolded
assert "fiba-womens-basketball-world-cup-2026-max-schmeling-halle-sessions-4006861" in unfolded
assert "fiba-womens-basketball-world-cup-2026-berlin-arena-tageskarten-4085168" in unfolded
for fixture in data["fixtures"][24:]:
    assert fixture["venue"] == "berlin-arena"
print("PASS: 36 source fixtures, 30 safe calendar events, 6 time-TBC games omitted")
