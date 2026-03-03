#!/bin/bash
set -e

SERVER="alif"
REMOTE_DIR="/opt/petrarca"

echo "=== TypeScript check ==="
(cd app && npx tsc --noEmit --skipLibCheck)

echo "=== Deploying to $SERVER ==="
ssh $SERVER "cd $REMOTE_DIR && git pull && cd app && npm install --no-audit --no-fund && systemctl restart petrarca-expo"

echo "=== Setting up research server ==="
ssh $SERVER "cp $REMOTE_DIR/scripts/petrarca-research.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable petrarca-research && systemctl restart petrarca-research && mkdir -p /opt/petrarca/research-results"

echo "=== Waiting for startup ==="
sleep 10

echo "=== Verifying ==="
ssh $SERVER "curl -sf http://localhost:8082 > /dev/null && echo 'Expo OK' || echo 'Expo FAILED'"
ssh $SERVER "curl -sf http://localhost:8090/health > /dev/null && echo 'Research server OK' || echo 'Research server FAILED'"

echo "URL: exp://alifstian.duckdns.org:8082"
