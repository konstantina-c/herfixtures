# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HerFixtures (herfixtures.com) is a women's sports calendar subscription service. It serves live `.ics` calendar feeds for women's football and basketball competitions (Women's UCL, EuroLeague Women, WNBA) that users can add directly to Google Calendar or Apple Calendar with one click.

## Architecture

There is **no build system**. The site is:

- `index.html` — the entire frontend: vanilla HTML, CSS custom properties, and inline JavaScript. No framework, no bundler.
- `api/subscribe.js` — a Vercel serverless function (Node.js) that handles email capture via the Beehiiv newsletter API.
- `*.ics` files — the calendar feeds, committed directly to the repo and served statically.
- `fetch_fixtures.py` — fetches football fixtures from RapidAPI and writes `womens_ucl.ics` and `euroleague_women.ics`.
- `fetch_wnba.py` — fetches WNBA fixtures from BallDontLie API and writes `wnba.ics`.
- `.github/workflows/refresh.yml` — GitHub Actions cron (6am and 18pm UTC daily) that runs both Python scripts and commits the updated `.ics` files back to `main`.

Deployment is on **Vercel**. `vercel.json` sets the `Content-Type: text/calendar` header and a 12-hour cache for all `.ics` routes.

## Running the feed scripts locally

Both scripts require environment variables. Set them before running:

```bash
# Football feeds (Women's UCL, EuroLeague Women)
RAPIDAPI_KEY=<key> python fetch_fixtures.py

# WNBA feed
BALLDONTLIE_API_KEY=<key> python fetch_wnba.py
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
- **Light/dark theme** — controlled by `data-theme` on `<html>`. CSS custom properties (`--bg`, `--text`, `--brand-fg`, etc.) handle all theming. The `toggleThemeReal()` function in the script section handles the toggle button.
- **UCL Final card** — a special celebrated card (`#ucl-final-card`) that auto-hides after May 23 2026 via an inline script. The `#ucl-badge` dynamically updates with a countdown.
- **Email capture** calls `POST /api/subscribe` which proxies to Beehiiv's subscriptions API. The Beehiiv publication ID is hardcoded in `api/subscribe.js`.

## Required secrets

| Secret | Used by |
|---|---|
| `RAPIDAPI_KEY` | `fetch_fixtures.py` — football data |
| `BALLDONTLIE_API_KEY` | `fetch_wnba.py` — WNBA data |
| `BEEHIIV_API_KEY` | `api/subscribe.js` — email subscriptions |

All three must be set in GitHub Actions secrets and (for the API function) in Vercel environment variables.
