#!/bin/bash
set -e

SERVER="alif"
REMOTE_DIR="/opt/petrarca"

echo "=== TypeScript check ==="
(cd app && npx tsc --noEmit --skipLibCheck)

echo "=== Deploying to $SERVER ==="
ssh $SERVER "cd $REMOTE_DIR && git pull && cd app && npm install --no-audit --no-fund && systemctl restart petrarca-expo"

echo "=== Waiting for startup ==="
sleep 10

echo "=== Verifying ==="
ssh $SERVER "curl -sf http://localhost:8082 > /dev/null && echo 'Expo OK' || echo 'Expo FAILED'"

echo "URL: exp://alifstian.duckdns.org:8082"
