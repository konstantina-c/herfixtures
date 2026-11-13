#!/usr/bin/env bash
# Publish an automatic feed-data update straight to main, with no review step.
#
# This is the ONLY way Claude is allowed to push (see .claude/settings.local.json).
# It refuses unless:
#   - we are on main and in sync with origin/main
#   - every changed file is in that feed's "publish_paths" in feeds/manifest.json
#   - the feed passes scripts/check_feed_health.py for that feed
# Anything else (index.html, design, copy) must go through a normal PR.
#
# Usage: bash scripts/publish_feed_update.sh <feed-id> "<one-line summary>"
set -euo pipefail

FEED_ID="${1:?usage: publish_feed_update.sh <feed-id> \"<summary>\"}"
SUMMARY="${2:?usage: publish_feed_update.sh <feed-id> \"<summary>\"}"
cd "$(dirname "$0")/.."

refuse() { echo "REFUSED: $*" >&2; echo "Nothing was pushed." >&2; exit 1; }

[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || refuse "not on main"

ALLOWED="$(python3 -c "
import json, sys
m = json.load(open('feeds/manifest.json'))
f = [x for x in m['feeds'] if x['id'] == sys.argv[1]]
print('\n'.join(f[0].get('publish_paths', [])) if f else '')
" "$FEED_ID")"
[ -n "$ALLOWED" ] || refuse "feed '$FEED_ID' has no publish_paths in feeds/manifest.json"

CHANGED="$(git status --porcelain --untracked-files=all | sed -E 's/^.. //')"
[ -n "$CHANGED" ] || { echo "No changes to publish."; exit 0; }
while IFS= read -r path; do
  grep -qxF "$path" <<<"$ALLOWED" || refuse "'$path' is not a data file of feed '$FEED_ID' (allowed: $(tr '\n' ' ' <<<"$ALLOWED"))"
done <<<"$CHANGED"

python3 scripts/check_feed_health.py --feed "$FEED_ID" --strict || refuse "health check failed for '$FEED_ID'"

git fetch --quiet origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || refuse "local main is not in sync with origin/main (run git pull --ff-only first)"

git -c user.name="HerFixtures Bot" -c user.email="bot@herfixtures.com" \
  commit --quiet -m "Auto-update $FEED_ID: $SUMMARY" -- $(tr '\n' ' ' <<<"$ALLOWED")

# The refresh bot may have pushed in the meantime; it never touches these files, so a rebase is safe.
for attempt in 1 2 3; do
  if git push --quiet origin HEAD:main; then
    echo "Pushed $(git rev-parse --short HEAD) to main: Auto-update $FEED_ID: $SUMMARY"
    exit 0
  fi
  echo "Push rejected (attempt $attempt); rebasing on origin/main and retrying..."
  git pull --quiet --rebase origin main
done
refuse "push failed 3 times"
