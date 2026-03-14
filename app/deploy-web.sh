#!/bin/bash
# Deploy Petrarca web app to Hetzner server
# Usage: ./deploy-web.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$APP_DIR/dist"
REMOTE="alif:/opt/petrarca/web/"

echo "Building web export..."
cd "$APP_DIR"
rm -rf dist
npx expo export -p web --clear

# Add content hash to bundle filename to bust browser caches
# (Expo reuses the same hash across builds)
BUNDLE=$(ls "$DIST_DIR/_expo/static/js/web"/entry-*.js 2>/dev/null | head -1)
if [ -n "$BUNDLE" ]; then
  CONTENT_HASH=$(md5 -q "$BUNDLE" | cut -c1-8)
  ORIG_NAME=$(basename "$BUNDLE")
  NEW_NAME="${ORIG_NAME%.js}-${CONTENT_HASH}.js"
  mv "$BUNDLE" "$(dirname "$BUNDLE")/$NEW_NAME"
  # Update index.html to reference the new filename
  sed -i '' "s|$ORIG_NAME|$NEW_NAME|g" "$DIST_DIR/index.html"
  echo "Bundle: $NEW_NAME"
fi

echo "Deploying to $REMOTE..."
scp -r "$DIST_DIR"/* "$REMOTE"

echo "Done. Visit http://alifstian.duckdns.org:8084/"
