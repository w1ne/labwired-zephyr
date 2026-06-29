#!/usr/bin/env bash
# Materialize the zephyr-bme280 template into a throwaway GitHub repo and watch
# its CI. Idempotent: if the repo already exists, force-push an updated commit.
#
# Usage: bash scripts/prove_export.sh [repo-name]
set -euo pipefail

REPO_NAME="${1:-zephyr-bme280-proof}"
OWNER="${OWNER:-w1ne}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/export/template/zephyr-bme280"
WORK="$(mktemp -d)"

cp -r "$SRC/." "$WORK/"
cd "$WORK"
git init -q
git add -A
git commit -q -m "init zephyr-bme280 verifiable build"

# Create repo if it doesn't exist; otherwise just add the remote and force-push.
if gh repo view "$OWNER/$REPO_NAME" --json name -q .name >/dev/null 2>&1; then
    echo "Repo $OWNER/$REPO_NAME already exists — force-pushing update..."
    git remote add origin "https://github.com/$OWNER/$REPO_NAME.git"
    git push -f origin HEAD:main
else
    echo "Creating repo $OWNER/$REPO_NAME ..."
    gh repo create "$OWNER/$REPO_NAME" --public --source=. --push
fi

echo "Waiting for CI to start for $OWNER/$REPO_NAME ..."
sleep 15
gh run watch -R "$OWNER/$REPO_NAME" --exit-status
