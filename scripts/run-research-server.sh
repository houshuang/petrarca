#!/usr/bin/env bash
# Start research-server.py with Mac-mini paths + API keys loaded.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Run first:  bash scripts/bootstrap-mac-mini.sh"
  exit 1
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

# Ensure `claude` CLI is findable without shadowing venv Python (append, do not prepend)
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

MAC_ENV="$ROOT/scripts/.env.mac-mini"
if [[ -f "$MAC_ENV" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$MAC_ENV"
  set +a
fi

# curriculum.py mkdirs CURRICULUM_DIR at import — must not default to /opt/petrarca
if [[ -n "${PETRARCA_DATA:-}" && -z "${CURRICULUM_DIR:-}" ]]; then
  export CURRICULUM_DIR="$PETRARCA_DATA/curricula"
fi
if [[ -n "${CURRICULUM_DIR:-}" ]]; then
  mkdir -p "$CURRICULUM_DIR"
fi

# Prefer installed limbic in venv over missing /opt/limbic
_LIM="$(python3 -c "import importlib.util, pathlib; s=importlib.util.find_spec('limbic'); print(pathlib.Path(s.origin).parent.parent if s and s.origin else '')" 2>/dev/null || true)"
if [[ -n "${_LIM:-}" ]]; then
  export LIMBIC_ROOT="$_LIM"
fi

echo "PETRARCA_DB=$PETRARCA_DB"
echo "Listening on 0.0.0.0:${RESEARCH_PORT:-8090} — use Tailscale IP from your phone."
cd "$ROOT/scripts"
exec python3 research-server.py
