#!/bin/bash
# Publish iPhone code/assets to the installed standalone preview app.
# Usage: bash app/deploy-mobile.sh "Describe the update"
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(git -C "$APP_DIR" rev-parse --show-toplevel)"
MESSAGE="${1:-$(git -C "$REPO_DIR" log -1 --format=%s)}"

# EAS uploads local files, so publish only the committed, integrated checkout.
if [ -n "$(git -C "$REPO_DIR" status --porcelain)" ]; then
  echo "ERROR: Publish from a clean owned checkout. Commit and push first."
  exit 1
fi
git -C "$REPO_DIR" fetch origin main
if [ "$(git -C "$REPO_DIR" rev-parse HEAD)" != "$(git -C "$REPO_DIR" rev-parse origin/main)" ]; then
  echo "ERROR: This checkout must match origin/main before publishing."
  exit 1
fi

cd "$APP_DIR"
npx tsc --noEmit --skipLibCheck
python3 "$REPO_DIR/scripts/mobile_api_preflight.py" --check
python3 "$REPO_DIR/scripts/mobile_api_preflight.py" eas update --channel preview --platform ios --environment preview --message "$MESSAGE" --non-interactive

echo "Published. Reopen Petrarca to download, leave it open briefly, then quit and reopen to apply."
echo "Native dependency/config changes require a version bump and a new preview build instead."
