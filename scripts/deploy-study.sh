#!/bin/bash
# Run the unchanged unified deploy with configuration pointing to this owned checkout.
# The legacy shared checkout may contain unrelated uncommitted work.
set -euo pipefail
REPO_DIR="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
test -z "$(git -C "$REPO_DIR" status --porcelain)"
git -C "$REPO_DIR" fetch origin main
test "$(git -C "$REPO_DIR" rev-parse HEAD)" = "$(git -C "$REPO_DIR" rev-parse origin/main)"
DEPLOY_DIR="$(mktemp -d /tmp/petrarca-owned-deploy.XXXXXX)"
trap 'rm -rf "$DEPLOY_DIR"' EXIT
mkdir "$DEPLOY_DIR/scripts"
cp "$HOME/src/expo/scripts/deploy.sh" "$DEPLOY_DIR/scripts/deploy.sh"
python3 - "$HOME/src/expo/config.json" "$DEPLOY_DIR/config.json" "$REPO_DIR" <<'PY'
import json,sys
config=json.load(open(sys.argv[1]))
config['projects']['petrarca']['local_root']=sys.argv[3]
with open(sys.argv[2],'w') as f: json.dump(config,f)
PY
cmp "$HOME/src/expo/scripts/deploy.sh" "$DEPLOY_DIR/scripts/deploy.sh"
bash "$DEPLOY_DIR/scripts/deploy.sh" petrarca
bash "$REPO_DIR/scripts/deploy-mobile-api.sh"
bash "$REPO_DIR/app/deploy-mobile.sh" "${1:-Norway assessment: overview recordings and reliable audio identity}"
