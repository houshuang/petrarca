#!/usr/bin/env bash
# One-time / repeat safe setup for Petrarca on a Mac (mini).
# Run from anywhere:  bash scripts/bootstrap-mac-mini.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Repo: $ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "==> Creating .venv …"
  python3 -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

echo "==> pip install (needs network for limbic from GitHub) …"
pip install -q -r "$ROOT/requirements.txt"

MAC_ENV="$ROOT/scripts/.env.mac-mini"
if [[ ! -f "$MAC_ENV" ]]; then
  echo "==> Creating $MAC_ENV from template …"
  cp "$ROOT/scripts/env.mac-mini.example" "$MAC_ENV"
fi

KEYS="$ROOT/.env"
if [[ ! -f "$KEYS" ]]; then
  echo "==> Creating $KEYS from .env.keys.template — EDIT THIS FILE and add keys …"
  cp "$ROOT/.env.keys.template" "$KEYS"
  echo "    Open: $KEYS"
fi

# shellcheck disable=SC1091
set -a
source "$MAC_ENV"
set +a

echo "==> Initializing SQLite at $PETRARCA_DB …"
cd "$ROOT/scripts"
python3 -c "from db import init_db; init_db()"
echo "==> Done. Next:"
echo "    1) Edit $KEYS — set GEMINI_KEY and ANTHROPIC_API_KEY"
echo "    2) Install Claude Code CLI and run:  claude  (login once)"
echo "    3) Start API:  bash scripts/run-research-server.sh"
