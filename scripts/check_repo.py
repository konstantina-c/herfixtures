#!/usr/bin/env python3
"""Pre-merge consistency check (runs on every PR via .github/workflows/pr-checks.yml).

Catches mistakes that YAML validation and a local test run don't:
  1. every path/glob in refresh.yml's `git add` matches at least one tracked file
     (Nov 15, 2026: a missing space glued two names together and the bot's commit
      failed, which silently stops every feed update)
  2. every feed in feeds/manifest.json and every league in feeds/espn_leagues.json
     (competition + team files) is covered by that `git add` line
  3. every Python file compiles
  4. the JSON config files parse (and Frauen-BL corrections are complete)
Exit 1 with a list of problems, so scripts/merge_pr.sh refuses the merge.
"""

from __future__ import annotations

import fnmatch
import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
problems: list[str] = []

tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
tracked += [str(p.relative_to(ROOT)) for p in ROOT.glob("*.ics")]  # new, not-yet-committed feeds count too

# 4. JSON configs
configs = {}
for name in ("feeds/manifest.json", "feeds/espn_leagues.json", "feeds/frauen_bl_overrides.json", "feeds/strip.json"):
    try:
        configs[name] = json.loads((ROOT / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        problems.append(f"{name} does not parse: {e}")

# 4b. Frauen-BL corrections: every entry complete, kick-off a real date-time
from datetime import datetime  # noqa: E402
for i, o in enumerate(configs.get("feeds/frauen_bl_overrides.json", {}).get("overrides", [])):
    missing = [k for k in ("match_id", "game", "kickoff_local", "openligadb_last_update", "source") if not o.get(k)]
    if missing:
        problems.append(f"frauen_bl_overrides.json entry {i}: missing {', '.join(missing)}")
        continue
    try:
        datetime.fromisoformat(o["kickoff_local"])
    except ValueError:
        problems.append(f"frauen_bl_overrides.json entry {i}: kickoff_local '{o['kickoff_local']}' is not YYYY-MM-DDTHH:MM")

# 1. git add paths in refresh.yml
wf = (ROOT / ".github/workflows/refresh.yml").read_text(encoding="utf-8")
m = re.search(r"^\s*git add (.+)$", wf, re.M)
patterns = m.group(1).split() if m else []
if not patterns:
    problems.append("refresh.yml: no `git add` line found")
for pat in patterns:
    if not any(fnmatch.fnmatch(f, pat) for f in tracked):
        problems.append(f"refresh.yml git add: '{pat}' matches no file (typo or two names glued together?)")

def covered(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)

# 2. every feed is committed by the bot
for f in configs.get("feeds/manifest.json", {}).get("feeds", []):
    if f.get("source") == "auto" and not covered(f["ics"]):
        problems.append(f"manifest feed '{f['id']}': {f['ics']} is not in refresh.yml git add (bot would never publish it)")
for lid, lg in configs.get("feeds/espn_leagues.json", {}).get("leagues", {}).items():
    if not covered(lg["output"]):
        problems.append(f"ESPN league '{lid}': {lg['output']} is not in refresh.yml git add")
    for _, slug in lg.get("teams", {}).values():
        team_file = f"{lg['team_prefix']}{slug}.ics"
        if not covered(team_file):
            problems.append(f"ESPN league '{lid}': team file {team_file} is not in refresh.yml git add")
            break
    if not any(f["ics"] == lg["output"] for f in configs.get("feeds/manifest.json", {}).get("feeds", [])):
        problems.append(f"ESPN league '{lid}' is missing from feeds/manifest.json (no health check, no badge)")

# 3. Python compiles
for py in sorted(ROOT.glob("*.py")) + sorted((ROOT / "scripts").glob("*.py")):
    try:
        py_compile.compile(str(py), doraise=True)
    except py_compile.PyCompileError as e:
        problems.append(f"{py.relative_to(ROOT)} does not compile: {e.msg.strip().splitlines()[-1]}")

if problems:
    print("Repo check FAILED:")
    for p in problems:
        print("  ✗", p)
    sys.exit(1)
print(f"Repo check passed: {len(patterns)} git add paths, configs, Python files OK")
