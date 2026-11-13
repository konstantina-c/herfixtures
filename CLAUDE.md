# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HerFixtures (herfixtures.com) is a women's sports calendar subscription service. It serves live `.ics` calendar feeds for women's football and basketball competitions (Women's UCL, EuroLeague Women, WNBA) that users can add directly to Google Calendar or Apple Calendar with one click.

## Architecture

There is **no build system**. The site is:

- `index.html` — the entire frontend: vanilla HTML, CSS custom properties, and inline JavaScript. No framework, no bundler.
- `api/subscribe.js` — a Vercel serverless function (Node.js) that handles email capture via the Beehiiv newsletter API.
- `*.ics` files — the calendar feeds, committed directly to the repo and served statically.
- `fetch_ucl.py` — fetches Women's Champions League fixtures from ESPN's public API (no key) and writes `womens_ucl.ics`.
- `generate_euroleague_women_ics.py` — builds `euroleague_women.ics` from the hand-maintained `feeds/euroleague-women-2026-27/fixtures.json` (copied from FIBA's official schedule; not in the cron — edit the JSON, re-run, open a PR). Add later rounds only once FIBA confirms both teams.
- `fetch_wnba.py` — fetches WNBA fixtures from ESPN's public API (no key) and writes `wnba.ics`.
- `.github/workflows/refresh.yml` — GitHub Actions cron (6am and 18pm UTC daily) that runs the `fetch_*.py` scripts and commits the updated `.ics` files back to `main`.

Deployment is on **Vercel**. `vercel.json` sets the `Content-Type: text/calendar` header and a 12-hour cache for all `.ics` routes.

## Running the feed scripts locally

The cron scripts use ESPN's public API and need no keys:

```bash
python fetch_ucl.py     # womens_ucl.ics
python fetch_wnba.py    # wnba.ics
```

Python dependencies: `pip install requests icalendar pytz`

## Serving locally

Because there is no build step, you can open `index.html` directly in a browser, or run any static file server:

```bash
python -m http.server 8080
```

The `api/subscribe.js` endpoint only works when deployed to Vercel (it uses `process.env.BEEHIIV_API_KEY`).

## Key design decisions

- **`.ics` files are committed to the repo** — Vercel serves them as static assets. The GitHub Actions bot refreshes and commits them twice a day. This keeps the calendar feeds stable even during API outages.
- **Single `index.html`** — all CSS and JS are inline. No external dependencies except Google Fonts and the gtag analytics script.
- **Light/dark theme** — controlled by `data-theme` on `<html>`. CSS custom properties (`--bg`, `--text`, `--brand-fg`, etc.) handle all theming. The `toggleTheme()` function (button `#theme-icon-btn`) handles the toggle and saves the choice to `localStorage` (`theme` key); an inline script in `<head>` reads it back on load.
- **UCL Final card** — a special celebrated card (`#ucl-final-card`) that auto-hides after May 23 2026 via an inline script. The `#ucl-badge` dynamically updates with a countdown.
- **Email capture** calls `POST /api/subscribe` which proxies to Beehiiv's subscriptions API. The Beehiiv publication ID is hardcoded in `api/subscribe.js`.

## Required secrets

| Secret | Used by |
|---|---|
| `BEEHIIV_API_KEY` | `api/subscribe.js` — email subscriptions (Vercel environment variable) |

The feed scripts need no secrets. RapidAPI was dropped in Nov 2026 — never hardcode an API key as a fallback in source.

## Who reviews what (decided Nov 13, 2026)

- **Konstantina reviews and merges** anything a visitor sees or experiences: `index.html`, any `.html`, `blog/`, `assets/`, CSS, images, copy, links, bottom sheets, add-to-calendar flows. She checks it on the Vercel Preview like a design review on staging.
- **Claude owns everything technical** (fetch scripts, feeds, workflows, infra, tooling) end to end, from branch to merge to production check. It uses only:
  - `bash scripts/push_branch.sh`: pushes the current feature branch; never main, never force.
  - `bash scripts/merge_pr.sh <n>`: squash-merges a PR only if it's open, targets main, touches **no** visual/experience file, is mergeable, and all checks pass.
  - `bash scripts/publish_feed_update.sh`: feed-data-only pushes to main (scheduled runs).
  - `git push` and `gh pr merge` stay denied in `.claude/settings.json`.

### Technical release checklist (every non-visual PR)

1. Root cause confirmed from evidence (run logs, git history), not assumed.
2. Branch from a fresh `git pull --ff-only` of main.
3. `python3 -m py_compile` on every changed `.py`; run every changed fetch script locally.
4. Event counts before → after for every touched feed; `python3 scripts/check_feed_health.py` all healthy (or only known, unrelated problems).
5. Revert files that only changed by side effect (DTSTAMP-only `.ics` diffs, `scores.json`) to keep the PR focused.
6. PR description: root cause, fix, before/after numbers, what was tested.
7. Vercel Preview: fetch the changed `.ics` files from the Preview (Dia, via the Claude in Chrome extension; Previews need a Vercel login) and compare event counts.
8. Merge with `scripts/merge_pr.sh`, then verify **production**: fetch the live `.ics` from herfixtures.com, compare counts, and trigger `gh workflow run refresh.yml`. Confirm the run succeeds and the next bot commit keeps the counts (the shrink guard will warn if not).
9. Log it in Notion "Session Log — Sam".

### ESPN API constraints (current)

- **Since 2026-09-15 ESPN returns 400 for any multi-day `dates=A-B` range, in every sport.** Use `espn_common.fetch_days()` (one request per day, cached per run, refuses partial seasons). This bug silently emptied Liga F (240 → 1), froze WNBA, and stripped all FIBA scores until Nov 13.
- Every feed write goes through `espn_common.safe_write_ics()` (shrink guard: refuses <50% of the existing event count; override for one run with `HERFIXTURES_ALLOW_SHRINK=<file>`).
- Placeholder ("TBD") games are dropped via `espn_common.is_placeholder()`.

## Feed maintenance (autonomous, no review)

Decided Nov 13, 2026: **feed-data updates go straight to main without Konstantina's review.** Anything visual or user-facing (`index.html`, badges, copy, design) still goes through a PR for her review.

- `feeds/manifest.json` — one entry per competition: season dates, breaks, expected event count, how it is updated, and `publish_paths` (the only files an automatic update may push). **Add every new feed here.**
- `scripts/check_feed_health.py` — runs at the end of every `refresh.yml` run. Opens one GitHub issue "🚨 Feed health alert" (Konstantina gets the email) when an in-season feed has no upcoming events, is far below its expected size, or contains TBD placeholders. Updates it when the problems change and closes it automatically when all feeds are healthy.
- `scripts/update_euroleague_fixtures.py` — the only way to change EuroLeague Women data: pipe new games as JSON on stdin. Adds or corrects future games only, never deletes, refuses on any failed check (unknown team/round, unrealistic tip-off, team playing twice within 20h, game outside the season). Use `--dry-run` first.
- `scripts/publish_feed_update.sh <feed-id> "<summary>"` — the only way Claude may push. Refuses unless on main, in sync with origin, every changed file is in that feed's `publish_paths`, and the health check passes. Commits as HerFixtures Bot.
- EuroLeague Women updates run as scheduled Claude tasks on Konstantina's Mac (Dec 3 2026, Feb 3 2027, Mar 11 2027; they retry daily for up to 7 days). FIBA's site blocks scripts, so the runs read it through her Dia browser (Claude in Chrome extension).

## FIBA WWC 2026 feed

Fixture data lives at `feeds/fiba-wwc-2026/fixtures.json` — this is a manually maintained JSON file, not fetched by any cron. It is not part of the V1/V2 feed list. After editing it, always re-run the fetch script locally before committing:

```bash
python3 fetch_fiba_scores.py        # fetches ESPN scores + writes all.ics + 16 team feeds + patches scores.json
```

`generate_fiba_ics.py` and `generate_fiba_ics_teams.py` still exist as dev tools (no ESPN call, no scores) but are no longer in the cron — `fetch_fiba_scores.py` replaced them in Stage 3 (PR #25).

There is no cron refresh for this feed — it only goes live on merge to main.

### Knockout-stage partially-known matchups

When a round is scheduled before the previous round's winner is known, **never use placeholder text** like "Winner of Game X" or "TBD". Instead:

- If one team is confirmed and the other is one of two, show both real possibilities using a slash: `Puerto Rico/China vs France`.
- In `fixtures.json`, store the display string in `home` (or `away`) and list the candidate team names in a parallel `home_options` (or `away_options`) array so team feeds pick up the event correctly.
- `generate_fiba_ics.py` requires no code change — the slash string passes all existing checks and triggers STATUS:CONFIRMED automatically.
- `generate_fiba_ics_teams.py` matches via the `home_options`/`away_options` arrays.
- Once the previous round finishes, follow up to replace the slash string and options array with the single confirmed team name and bump SEQUENCE.
