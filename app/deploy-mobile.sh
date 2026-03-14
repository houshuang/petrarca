#!/bin/bash
# Deploy Petrarca mobile app to Hetzner Expo dev server
# Syncs source files, restarts Expo, verifies the bundle compiles
# Usage: ./deploy-mobile.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE_DIR="alif:/opt/petrarca/app/"
BUNDLE_URL="http://localhost:8082/node_modules/expo-router/entry.bundle?platform=ios&dev=true&minify=false"

echo "=== Syncing app to server ==="
rsync -av --delete \
  --exclude='node_modules' \
  --exclude='.expo' \
  --exclude='dist' \
  --exclude='assets/fonts' \
  --exclude='.git' \
  "$APP_DIR/" "$REMOTE_DIR" \
  | tail -3

echo ""
echo "=== Restarting Expo dev server ==="
ssh alif 'sudo systemctl restart petrarca-expo'
echo "Waiting for Metro to start..."
sleep 8

echo ""
echo "=== Triggering iOS bundle ==="
HTTP_CODE=$(ssh alif "curl -s -o /dev/null -w '%{http_code}' '$BUNDLE_URL'" 2>/dev/null)
if [ "$HTTP_CODE" != "200" ]; then
  echo "ERROR: Bundle request returned HTTP $HTTP_CODE"
  exit 1
fi

echo "Waiting for bundle to compile..."
sleep 12

echo ""
echo "=== Checking for errors ==="
ERRORS=$(ssh alif 'journalctl -u petrarca-expo --since "25 sec ago" --no-pager 2>/dev/null | grep -iE "error|Error|fail|Unable to resolve" | grep -v "Bundled" | grep -v "systemd" | grep -v "kill control group"' 2>/dev/null || true)

if [ -n "$ERRORS" ]; then
  echo "ERRORS FOUND:"
  echo "$ERRORS"
  echo ""
  echo "Deploy FAILED — fix errors before using the app."
  exit 1
fi

# Check bundle actually compiled
BUNDLED=$(ssh alif 'journalctl -u petrarca-expo --since "25 sec ago" --no-pager 2>/dev/null | grep "Bundled"' 2>/dev/null || true)
if [ -z "$BUNDLED" ]; then
  echo "WARNING: No bundle compilation detected — server may still be starting."
  echo "Check manually: ssh alif 'journalctl -u petrarca-expo -f'"
  exit 1
fi

echo "$BUNDLED"
echo ""
echo "Deploy OK. Open Expo Go → exp://alifstian.duckdns.org:8082"
