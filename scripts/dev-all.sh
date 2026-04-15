#!/usr/bin/env bash
# One terminal: research API (background) + Expo Metro (foreground).
# Phone: same Wi‑Fi or Tailscale; scan QR with your Petrarca dev build.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

lsof -ti :8090 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti :8081 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

echo "==> Starting research-server on :8090 (background)…"
bash "$ROOT/scripts/run-research-server.sh" &
SRV_PID=$!
sleep 4
if ! curl -sS -m 3 "http://127.0.0.1:${RESEARCH_PORT:-8090}/health" | grep -q ok; then
  echo "ERROR: research-server did not become healthy. Check logs; killing $SRV_PID"
  kill "$SRV_PID" 2>/dev/null || true
  exit 1
fi
echo "==> API ok. Starting Metro on :8081 (foreground; Ctrl+C stops Metro only)…"
echo "    Stop API later:  kill $SRV_PID   or   lsof -ti :8090 | xargs kill -9"
cd "$ROOT/app"
exec npx expo start --port 8081
