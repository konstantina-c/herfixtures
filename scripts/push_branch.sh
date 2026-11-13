#!/usr/bin/env bash
# Push the current feature branch to GitHub. Never pushes main, never forces.
# Claude's only general push path (git push itself stays denied in .claude/settings.json).
# Usage: bash scripts/push_branch.sh
set -euo pipefail
cd "$(dirname "$0")/.."

refuse() { echo "REFUSED: $*" >&2; echo "Nothing was pushed." >&2; exit 1; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
case "$BRANCH" in
  main|master|HEAD|dev) refuse "won't push '$BRANCH' (only feature branches; main changes only through merged PRs)" ;;
esac
[ -z "$(git status --porcelain)" ] || refuse "uncommitted changes; commit them first"

git push --quiet -u origin "HEAD:refs/heads/$BRANCH"
echo "Pushed $BRANCH ($(git rev-parse --short HEAD))"
