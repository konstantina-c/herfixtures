# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HerFixtures (herfixtures.com) is a women's sports calendar subscription service: 12 competitions (football + basketball), each with a competition calendar and team calendars, added to Google/Apple/Outlook with one click.

**Full architecture (plain-language + reference): Notion → HerFixtures HQ → Knowledge Base → "HerFixtures Architecture".** Keep it in sync: any change to how feeds are built, published or checked must update that page in the same session.

## Architecture (summary)

There is **no build system**. Deployment is on **Vercel** (`vercel.json`: `text/calendar` + 12h cache for `.ics`).

- `index.html`: the entire frontend (vanilla HTML/CSS/JS): competition cards, team pickers (`*_CONFIG` objects + `FeedModal`), the **Scores Strip** (reads `scores.json`, built from our own feeds by `scripts/build_scores_json.py`; its rules are in that file's docstring), badges (read `feed_status.json`).
- `api/subscribe.js`: Vercel function for email capture (Beehiiv).
- `*.ics`: the feeds, committed to the repo, served statically.
- **`fetch_espn_feeds.py` + `feeds/espn_leagues.json`: the shared feed engine.** 7 ESPN competitions are config entries: Liga F, WSL, Première Ligue, A-League Women, Liga MX Femenil, NCAA WBB, NWSL. Plus Eredivisie Women, Serie A Women and UEFA Women's Champions League from **API-Football** (`"source": "api-football"`, adapter `apifootball.py`, licensed paid plan on Konstantina's account): one request per league per run, same calendar building and shrink guard.
- Other sources: `fetch_frauen_bundesliga.py` (+ `_teams`, OpenLigaDB; it has no TBC flag, so unfinished games at its Sunday 15:30 Berlin placeholder become all-day "(time TBC)" events; hand-checked DFB kick-offs for games OpenLigaDB has wrong go in `feeds/frauen_bl_overrides.json`, never edit OpenLigaDB itself. A correction stops applying, with a warning in the refresh log, once OpenLigaDB edits that game again); `generate_euroleague_women_ics.py` + `scripts/update_euroleague_fixtures.py` (hand-maintained from FIBA's site, scheduled Claude runs).
- **Frozen** (files kept for subscribers, not refreshed): WNBA 2026 (re-add to the engine with the 2027 schedule), FIBA WWC 2026, ICC T20 2026.
- `feeds/manifest.json`: every competition's season dates/status. It drives the health check, badges, and auto-publish paths.
- `.github/workflows/refresh.yml`: runs 06:00 + 18:00 UTC: engine → Frauen-BL → Scores Strip → badges → sitemap → commit → health check. `.github/workflows/pr-checks.yml`: Repo check on every PR.

## Running the feed scripts locally

No keys needed (ESPN, OpenLigaDB are public):

```bash
python3 fetch_espn_feeds.py                          # all engine leagues
python3 fetch_espn_feeds.py --out-dir /tmp/x wsl     # one league into a scratch folder (testing)
python3 scripts/check_repo.py && python3 scripts/check_feed_health.py
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
| `APIFOOTBALL_KEY` | `fetch_espn_feeds.py` for `"source": "api-football"` leagues (GitHub Actions secret; locally `~/.config/herfixtures/apifootball_key`, which Konstantina runs herself — Claude's permissions block reading it) |

The ESPN, OpenLigaDB and FIBA paths need no secrets. RapidAPI was dropped in Nov 2026 — never hardcode an API key as a fallback in source. Never use RapidAPI resellers of FotMob/Sofascore/Flashscore data.

### API-Football leagues (time TBC)

API-Football has no reliable "time not confirmed" flag: unconfirmed games get a placeholder kick-off. `apifootball.py` marks status `TBD`, plus (rule 2) any future round where ≥ `api_football.uniform_min` games (default 4) share one kick-off > 7 days out. **Check each new league against a second source before enabling it:** Eredivisie Women really plays 4 games at Sunday 16:45, so it has `uniform_min: 0`. Serie A Women uses real placeholders (`uniform_min: 4`; checked against FIGC Nov 24: round 9 exact, rounds 10–22 all at one time → TBC). UCL Women has `uniform_min: 0`: the final league-stage matchday really kicks off simultaneously (ESPN and API-Football agree). `api_football.rename` keeps display names stable when a competition moves source; `title_round` appends API-Football's round to description line 1. Test locally with `--out-dir`: Konstantina runs `APIFOOTBALL_KEY="$(cat ~/.config/herfixtures/apifootball_key)" python3 fetch_espn_feeds.py --out-dir _af_test <league>`.

## Who reviews what (decided Nov 13, 2026)

- **Konstantina reviews and merges** anything a visitor sees or experiences: `index.html`, any `.html`, `blog/`, `assets/`, CSS, images, copy, links, bottom sheets, add-to-calendar flows. She checks it on the Vercel Preview like a design review on staging.
- **Claude owns everything technical** (fetch scripts, feeds, workflows, infra, tooling) end to end, from branch to merge to production check. It uses only:
  - `bash scripts/push_branch.sh`: pushes the current feature branch; never main, never force.
  - `bash scripts/merge_pr.sh <n>`: squash-merges a PR only if it's open, targets main, touches **no** visual/experience file, is mergeable, and all checks pass.
  - `bash scripts/publish_feed_update.sh`: feed-data-only pushes to main (scheduled runs).
  - `git push` and `gh pr merge` stay denied in `.claude/settings.json`.

### Editing gotcha: trailing spaces

The Edit tool drops a trailing space at the end of a replacement string, so an edit that ends in a space glues two words together. This broke the refresh `git add` line on Nov 15, 2026 and nearly did again. Anchor edits on the next word instead of a space, and always run `python3 scripts/check_repo.py` before a PR (the "Repo check" CI enforces it).

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

### Adding a competition from ESPN (shared feed engine)

New ESPN leagues are **config, not code**: add an entry to `feeds/espn_leagues.json`. Required fields: ESPN slug, season dates, calendar names, `order` (`away_at_home` / `home_vs_away`), team list with stable slugs. Then add it to `feeds/manifest.json` (health check + homepage badge). `fetch_espn_feeds.py` (one refresh step) builds the competition feed and every team feed. Test with `python3 fetch_espn_feeds.py --out-dir <scratch> <league-id>` before writing into the repo. Built in:
- **Time TBC:** ESPN's `timeValid=false` kick-offs (placeholder 18:00/20:00 UTC) become all-day "(time TBC)" events. They turn timed automatically when confirmed (same UID).
- **Polite fetching:** leagues run sequentially with 2 parallel requests. Games older than 7 days are kept from the existing file, not re-fetched. `HERFIXTURES_FULL_REFETCH=1` rebuilds everything.
- Placeholder games dropped, shrink guard on every write, partial fetches refused.
- Optional per-league settings: `rank_filter` (only games involving a team ranked 1..N), `show_rank` ("#5 Duke"), `team_name: "location"`, `team_source: "schedule"` (team feeds from each team's ESPN schedule; needed when the league feed is a subset, e.g. NCAA Top 25). All off by default.
- **Formatting changes to the engine** (summary, description, names) only reach games older than 7 days after a full rebuild: run `HERFIXTURES_FULL_REFETCH=1 python3 fetch_espn_feeds.py <league>` and commit the result.
- Team logos for the homepage picker: ESPN `teamlogos/soccer/500/<id>.png`. Some women's teams have none; use the club's men's-team crest id (e.g. Lens 175) and fall back to an emoji tile only if the club has none on ESPN.
- Migrated: Liga F (Nov 15), UCL Women + NWSL (Nov 16, proven identical apart from added TV lines). WNBA frozen until the 2027 schedule.
- **New competitions never come from ESPN** (its terms forbid automated use; decided Nov 24, 2026). Add them from API-Football. UCL Women moved ESPN → API-Football on Nov 24 (all 54 league-stage games identical, +9 qualifiers; UIDs changed once, `af-ucl-women`).

### Adding or removing a competition: the homepage pieces

What updates **automatically** from the data: the hero subtitle's competition count (it counts the homepage cards), the Scores Strip and its dropdown, card badges, and each map pin's colour (coral in season, grey off-season, from `feed_status.json`).

What needs **one manual step**, done in the same visual PR (Konstantina reviews):
1. **Card + picker** in `index.html`: the `feed-card` block with `data-feed="<manifest id>"`, a `*_CONFIG` object (teams + crests) and an `open…Modal()` opener.
2. **Map dot**: one line in the hero's `COMPS` list (`id`, `cfg`, `name`, optional `short`, `x`, `y`) and one entry in `COUNTRY` (the caption's "where"). Position as % of the map: `x = (lon + 130) / 310 × 100`, `y = (72 − lat) × 1.2 / 144 × 100` (use the league's centre of gravity, e.g. Eredivisie lon 5.3, lat 52.1). US competitions also go in `AWAY_FIRST`.
3. **Scores Strip labels** in `feeds/strip.json`: `order`, `labels` (dropdown), `short` (cards), and `away_first` if it's a US competition (technical file, can ship with the card).

Removing a competition = remove the card, its `COMPS` line and its `COUNTRY` entry; freezing it in `feeds/manifest.json` (`source: "frozen"`) already drops it from the Scores Strip.

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
