#!/bin/bash
# Refresh the Substack section of the profile README and push if it changed.
#
# Runs on a Mac (via launchd) because Substack blocks GitHub Actions' IP ranges.
# Works in whatever clone this script lives in; use a dedicated clone so it never
# touches a working copy with uncommitted edits.
set -euo pipefail
cd "$(dirname "$0")/../.."

# --- settings ---------------------------------------------------------------
export SUBSTACK_FEED="https://itsrubenclarke.substack.com/feed"
export MAX_POSTS="3"
export LINK_TITLES="false"
# "true" keeps the section updated but hidden (inside an HTML comment).
# Change to "false" once the real articles are live to show it on the profile.
export HIDE_SECTION="true"
# -----------------------------------------------------------------------------

git checkout -q main
git pull -q --ff-only
python3 .github/scripts/update_substack.py

git add README.md profile-assets
if git diff --cached --quiet; then
  echo "No changes to commit"
else
  git commit -q -m "chore: update recent Substack articles"
  git push -q
  echo "Pushed update"
fi
