#!/bin/bash
# Deploy only the versioned private mobile nginx gateway. No runtime data changes.
set -euo pipefail
REPO_DIR="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
if [ -n "$(git -C "$REPO_DIR" status --porcelain)" ]; then
  echo 'Commit and push from a clean owned checkout first.' >&2
  exit 1
fi
git -C "$REPO_DIR" fetch origin main
HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD)"
if [ "$HEAD_SHA" != "$(git -C "$REPO_DIR" rev-parse origin/main)" ]; then
  echo 'Deployment checkout must match origin/main.' >&2
  exit 1
fi
# The only interpolated value is a locally resolved Git SHA. Preserve unrelated
# server runtime files and refuse tracked edits or a different checked-out branch.
ssh alif "set -eu
cd /opt/petrarca
test \"\$(git branch --show-current)\" = main
test -z \"\$(git status --porcelain --untracked-files=no)\"
git pull --ff-only origin main
test \"\$(git rev-parse HEAD)\" = '$HEAD_SHA'
python3 scripts/install_mobile_api.py"
