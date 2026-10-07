#!/bin/bash
# Pull the latest Substack posts into the README and open a pull request.
# Usage: ./update-articles.sh
set -euo pipefail
cd "$(dirname "$0")"

# --- settings ---------------------------------------------------------------
export SUBSTACK_FEED="https://itsrubenclarke.substack.com/feed"
export MAX_POSTS="3"
export LINK_TITLES="false"
# "false" shows the section on the profile. "true" keeps it updated but hidden
# (inside an HTML comment).
export HIDE_SECTION="false"
# -----------------------------------------------------------------------------

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "You have uncommitted changes. Commit or stash them first." >&2
  exit 1
fi

git checkout -q main
git pull -q --ff-only
python3 .github/scripts/update_substack.py

git add README.md profile-assets
if git diff --cached --quiet; then
  echo "Already up to date. Nothing to do."
  exit 0
fi

branch="substack-update-$(date +%Y-%m-%d-%H%M)"
git checkout -q -b "$branch"
git commit -q -m "chore: update recent Substack articles"
git push -q -u origin "$branch"
gh pr create --base main --head "$branch" \
  --title "chore: update recent Substack articles" \
  --body "Refresh the latest Substack posts in the README."
git checkout -q main
echo "Done. Merge the pull request above to publish the update."
