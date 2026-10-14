#!/usr/bin/env bash
# OpenArt — bring the VPS corpus up to date with this machine (workflow.MD, "Deploying the corpus").
#
# The API reads five data files, all in git, so they arrive with `git pull`:
#   dataset/opportunities.csv, dataset/labels/eligibility_constraints.jsonl,
#   dataset/labels/eligibility_constraints_reviewed.csv,
#   artifacts/opportunity_index.npz, artifacts/match_score.json
# A constraints file older than the corpus makes new calls show "This call has not
# been analysed yet". This script does the steps in order:
#   1. check locally that the constraints file covers every published call;
#   2. check that the five files are committed and pushed (the VPS gets them from git);
#   3. git pull on the VPS, rebuild/restart the API.
# The web app (Next) is not touched: rebuild it separately when web/ changed.
#
# Usage:
#   OPEN_ART_VPS=user@host OPEN_ART_DIR=/path/to/open_art deploy/sync_data.sh
set -euo pipefail

VPS="${OPEN_ART_VPS:?set OPEN_ART_VPS, e.g. user@host}"
DIR="${OPEN_ART_DIR:?set OPEN_ART_DIR, the repo path on the VPS}"
cd "$(dirname "$0")/.."

echo "1/3  Checking that the constraints cover every published call..."
uv run python scripts/check_constraints_coverage.py

echo "2/3  Checking that the corpus files in git are committed and pushed..."
GIT_FILES="dataset/opportunities.csv dataset/labels/eligibility_constraints.jsonl dataset/labels/eligibility_constraints_reviewed.csv artifacts/opportunity_index.npz artifacts/match_score.json"
for f in $GIT_FILES; do
    if ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        echo "NOT OK: $f is not in git. Commit and push it first: the API needs it on the VPS."
        exit 1
    fi
done
if ! git diff --quiet HEAD -- $GIT_FILES; then
    echo "NOT OK: uncommitted changes in: $(git diff --name-only HEAD -- $GIT_FILES | tr '\n' ' ')"
    echo "Commit and push them first: the VPS gets these files from git."
    exit 1
fi
git fetch --quiet
if [ -n "$(git log --oneline '@{u}..HEAD' 2>/dev/null)" ]; then
    echo "NOT OK: local commits not pushed yet. Push first: the VPS pulls from the remote."
    exit 1
fi

echo "3/3  Updating the VPS..."
ssh "$VPS" "cd '$DIR' && git pull --ff-only"
ssh "$VPS" "cd '$DIR' && docker compose up -d --build api"

echo "Done. Check the API log for a 'no eligibility constraints' warning:"
echo "  ssh $VPS \"cd '$DIR' && docker compose logs --tail 50 api\""
