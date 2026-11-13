#!/usr/bin/env python3
"""Check every competition feed listed in feeds/manifest.json for silent failures.

Rules (only while a competition is in season):
  - empty-future: no upcoming events, and the last event was more than grace_days ago
                  (skipped during declared breaks, e.g. UCL's winter gap)
  - thin:         fewer events than min_events (e.g. a feed that only has one matchday)
  - placeholder:  events with "TBD" teams (never publish fake events)
  - missing/unreadable file (always)

Usage:
  python3 scripts/check_feed_health.py                 # report, exit 0
  python3 scripts/check_feed_health.py --strict        # exit 1 if any problem
  python3 scripts/check_feed_health.py --feed euroleague-women --strict
  python3 scripts/check_feed_health.py --github-issue  # in Actions: open / update / close one issue
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "feeds" / "manifest.json"
ISSUE_TITLE = "🚨 Feed health alert"
PLACEHOLDER = re.compile(r"\bTBD\b|\bTBA\b", re.I)


def d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def read_events(path: Path) -> list[tuple[date, str]]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold folded lines
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        m = re.search(r"^DTSTART[^:\n]*:(\d{8})", block, re.M)
        s = re.search(r"^SUMMARY:(.*)$", block, re.M)
        if m:
            events.append((datetime.strptime(m.group(1), "%Y%m%d").date(), s.group(1).strip() if s else ""))
    return sorted(events)


def check_feed(feed: dict, today: date) -> list[str]:
    path = ROOT / feed["ics"]
    if not path.exists():
        return [f"`{feed['ics']}` is missing"]
    try:
        events = read_events(path)
    except Exception as e:  # noqa: BLE001
        return [f"`{feed['ics']}` could not be read ({e})"]

    problems = []
    placeholders = [(day, s) for day, s in events if PLACEHOLDER.search(s)]
    if placeholders:
        problems.append(f"{len(placeholders)} placeholder event(s) such as “{placeholders[0][1]}” on {placeholders[0][0]}")

    start, end = d(feed["season"]["start"]), d(feed["season"]["end"])
    if not (start <= today <= end):
        return problems

    if len(events) < feed.get("min_events", 0):
        problems.append(f"only {len(events)} events in season (expected at least {feed['min_events']})")

    in_break = any(d(b["start"]) <= today <= d(b["end"]) for b in feed.get("breaks", []))
    upcoming = [e for e in events if e[0] >= today]
    last = events[-1][0] if events else None
    if not upcoming and not in_break:
        if last is None:
            problems.append("no events at all during the season")
        elif today > last + timedelta(days=feed.get("grace_days", 3)):
            problems.append(f"no upcoming events; last event was {last} ({(today - last).days} days ago)")
    return problems


def run_checks(feed_filter: str | None, today: date) -> dict[str, dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = {}
    for feed in manifest["feeds"]:
        if feed_filter and feed["id"] != feed_filter:
            continue
        results[feed["id"]] = {"feed": feed, "problems": check_feed(feed, today)}
    if feed_filter and not results:
        sys.exit(f"No feed with id {feed_filter!r} in feeds/manifest.json")
    return results


def report(results: dict, today: date) -> str:
    bad = {k: v for k, v in results.items() if v["problems"]}
    lines = [f"Checked {len(results)} feeds on {today}."]
    if not bad:
        return lines[0] + " All healthy."
    lines.append("")
    for fid, r in bad.items():
        f = r["feed"]
        lines.append(f"### {f['name']} (`{f['ics']}`, {f['source']})")
        lines += [f"- {p}" for p in r["problems"]]
        lines.append(f"- How it's updated: {f.get('update', '?')}")
        lines.append("")
    return "\n".join(lines)


def github_issue(text: str, healthy: bool) -> None:
    import requests

    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    api = f"https://api.github.com/repos/{repo}/issues"
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    open_issues = requests.get(api, headers=h, params={"state": "open", "per_page": 100}, timeout=20).json()
    issue = next((i for i in open_issues if i.get("title") == ISSUE_TITLE and "pull_request" not in i), None)
    footer = "\n\n---\n_Opened automatically by `scripts/check_feed_health.py` in the Refresh workflow. It updates when the problems change and closes itself once every feed is healthy._"

    if healthy:
        if issue:
            requests.post(f"{api}/{issue['number']}/comments", headers=h, json={"body": f"✅ {text}"}, timeout=20)
            requests.patch(f"{api}/{issue['number']}", headers=h, json={"state": "closed"}, timeout=20)
            print(f"Closed issue #{issue['number']}")
        return
    if not issue:
        r = requests.post(api, headers=h, json={"title": ISSUE_TITLE, "body": text + footer}, timeout=20)
        print(f"Opened issue #{r.json().get('number')}")
        return
    old = issue.get("body", "").split("\n---\n")[0]
    strip = lambda s: "\n".join(s.splitlines()[1:]).strip()  # ignore the date line
    if strip(old) != strip(text):
        requests.patch(f"{api}/{issue['number']}", headers=h, json={"body": text + footer}, timeout=20)
        requests.post(f"{api}/{issue['number']}/comments", headers=h, json={"body": "The problems changed:\n\n" + text}, timeout=20)
        print(f"Updated issue #{issue['number']}")
    else:
        print(f"Issue #{issue['number']} already describes these problems")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", help="check only this feed id")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any problem")
    ap.add_argument("--github-issue", action="store_true", help="open/update/close the alert issue (Actions)")
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (testing)")
    args = ap.parse_args()

    today = d(args.today) if args.today else date.today()
    results = run_checks(args.feed, today)
    text = report(results, today)
    print(text)
    healthy = not any(r["problems"] for r in results.values())
    if args.github_issue:
        github_issue(text, healthy)
    if args.strict and not healthy:
        sys.exit(1)


if __name__ == "__main__":
    main()
