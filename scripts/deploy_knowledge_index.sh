#!/bin/bash
set -euo pipefail

# Deploy knowledge_index.json to nginx content directory and update manifest.
# Can be called standalone or from content-refresh.sh.
#
# Usage:
#   ./scripts/deploy_knowledge_index.sh           # deploy to /opt/petrarca/data
#   ./scripts/deploy_knowledge_index.sh --local    # only update local data/ and app/data/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$PROJECT_DIR/data"
KNOWLEDGE_INDEX="$DATA_DIR/knowledge_index.json"
MANIFEST="$DATA_DIR/manifest.json"

LOCAL_ONLY=false
if [[ "${1:-}" == "--local" ]]; then
    LOCAL_ONLY=true
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Verify the knowledge index exists and is non-empty
if [ ! -s "$KNOWLEDGE_INDEX" ]; then
    log "ERROR: $KNOWLEDGE_INDEX does not exist or is empty"
    exit 1
fi

FILE_SIZE=$(wc -c < "$KNOWLEDGE_INDEX" | tr -d ' ')
log "Knowledge index: $KNOWLEDGE_INDEX ($FILE_SIZE bytes)"

# Compute hash for manifest
KNOWLEDGE_HASH=$(shasum -a 256 "$KNOWLEDGE_INDEX" | cut -c1-16)
log "Hash: $KNOWLEDGE_HASH"

# Update manifest.json with knowledge_index_hash
if [ -f "$MANIFEST" ]; then
    python3 -c "
import json, sys
with open('$MANIFEST') as f:
    manifest = json.load(f)
manifest['knowledge_index_hash'] = '$KNOWLEDGE_HASH'
with open('$MANIFEST', 'w') as f:
    json.dump(manifest, f, indent=2)
print(f'Updated manifest with knowledge_index_hash={\"$KNOWLEDGE_HASH\"}', file=sys.stderr)
"
    log "Updated manifest.json"
else
    # Create minimal manifest
    python3 -c "
import json
manifest = {'knowledge_index_hash': '$KNOWLEDGE_HASH'}
with open('$MANIFEST', 'w') as f:
    json.dump(manifest, f, indent=2)
"
    log "Created manifest.json"
fi

# Copy to app/data/ for local development
if [ -d "$PROJECT_DIR/app/data" ]; then
    cp "$KNOWLEDGE_INDEX" "$PROJECT_DIR/app/data/"
    cp "$MANIFEST" "$PROJECT_DIR/app/data/"
    log "Copied to app/data/"
fi

# Deploy to nginx content directory on server
if [ "$LOCAL_ONLY" = false ] && [ -d "/opt/petrarca/data" ]; then
    cp "$KNOWLEDGE_INDEX" /opt/petrarca/data/
    cp "$MANIFEST" /opt/petrarca/data/
    log "Deployed to /opt/petrarca/data/ (nginx content dir)"
else
    if [ "$LOCAL_ONLY" = true ]; then
        log "Local-only mode, skipping server deploy"
    else
        log "No /opt/petrarca/data/ found, skipping server deploy"
    fi
fi

log "Deploy complete"
