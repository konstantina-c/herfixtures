#!/usr/bin/env bash
# Merge a NON-VISUAL pull request into main. Claude's only merge path
# (gh pr merge itself stays denied in .claude/settings.json).
#
# Rule (Konstantina, Nov 13 2026): technical changes are Claude's responsibility;
# anything a visitor sees or experiences (index.html, blog, assets, copy, links,
# bottom sheets, add-to-calendar flows) is reviewed by her on the Vercel Preview
# and merged by her. This script enforces that split.
#
# Refuses unless: PR is open, not draft, targets main, touches no visual/experience
# file, GitHub reports it mergeable, and every check has passed.
# Usage: bash scripts/merge_pr.sh <pr-number>
set -euo pipefail
cd "$(dirname "$0")/.."

PR="${1:?usage: merge_pr.sh <pr-number>}"
refuse() { echo "REFUSED: $*" >&2; echo "Nothing was merged." >&2; exit 1; }

# Visual / experience paths: these always need Konstantina's review.
VISUAL_RE='(^|/)index\.html$|\.html?$|\.css$|^blog/|^assets/|\.(svg|png|jpe?g|webp|gif|ico)$|^og-image|^Favicon'

INFO="$(gh pr view "$PR" --json state,isDraft,baseRefName,mergeable,files,statusCheckRollup)"
read -r STATE DRAFT BASE MERGEABLE < <(jq -r '[.state, .isDraft, .baseRefName, .mergeable] | @tsv' <<<"$INFO")

[ "$STATE" = "OPEN" ]      || refuse "PR #$PR is $STATE"
[ "$DRAFT" = "false" ]     || refuse "PR #$PR is a draft"
[ "$BASE" = "main" ]       || refuse "PR #$PR targets '$BASE', not main"
[ "$MERGEABLE" = "MERGEABLE" ] || refuse "GitHub says PR #$PR is not mergeable ($MERGEABLE)"

VISUAL_FILES="$(jq -r '.files[].path' <<<"$INFO" | grep -E "$VISUAL_RE" || true)"
[ -z "$VISUAL_FILES" ] || refuse "PR #$PR touches visual/experience files, so Konstantina reviews and merges it:
$VISUAL_FILES"

TOTAL="$(jq '.statusCheckRollup | length' <<<"$INFO")"
NOT_OK="$(jq -r '.statusCheckRollup[] | select(((.conclusion // .state) | ascii_upcase) as $s | ($s != "SUCCESS" and $s != "NEUTRAL" and $s != "SKIPPED")) | "\(.name // .context): \(.conclusion // .state // "pending")"' <<<"$INFO")"
[ "$TOTAL" -gt 0 ] || refuse "PR #$PR has no checks yet (wait for Vercel)"
[ -z "$NOT_OK" ]   || refuse "checks not all passing on PR #$PR:
$NOT_OK"

gh pr merge "$PR" --squash --delete-branch >/dev/null
echo "Merged PR #$PR: $(gh pr view "$PR" --json mergeCommit --jq .mergeCommit.oid | cut -c1-8)"
