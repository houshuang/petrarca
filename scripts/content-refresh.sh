#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

START_TIME=$(date +%s)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=== Petrarca content refresh starting ==="
log "Script dir: $SCRIPT_DIR"
log "Project dir: $PROJECT_DIR"

# Activate venv
if [ -d "/opt/petrarca/.venv" ]; then
    log "Using venv at /opt/petrarca/.venv"
    source /opt/petrarca/.venv/bin/activate
elif [ -d "$PROJECT_DIR/.venv" ]; then
    log "Using venv at $PROJECT_DIR/.venv"
    source "$PROJECT_DIR/.venv/bin/activate"
else
    log "WARNING: No venv found, using system Python"
fi

# Load environment
if [ -f "/opt/petrarca/.env" ]; then
    log "Loading environment from /opt/petrarca/.env"
    set -a
    source /opt/petrarca/.env
    set +a
fi

# Step 1: Fetch Twitter bookmarks
log "Step 1: Fetching Twitter bookmarks..."
python3 "$SCRIPT_DIR/fetch_twitter_bookmarks.py" --save --limit 50 \
    || log "Step 1 FAILED: fetch_twitter_bookmarks.py"

# Step 2: Fetch Readwise Reader
log "Step 2: Fetching Readwise Reader..."
python3 "$SCRIPT_DIR/fetch_readwise_reader.py" --save --incremental \
    || log "Step 2 FAILED: fetch_readwise_reader.py"

# Step 3: Build articles
log "Step 3: Building articles..."
python3 "$SCRIPT_DIR/build_articles.py" --limit 10 \
    || log "Step 3 FAILED: build_articles.py"

# Step 4: Generate syntheses
if [ -f "$SCRIPT_DIR/generate_syntheses.py" ]; then
    log "Step 4: Generating syntheses..."
    python3 "$SCRIPT_DIR/generate_syntheses.py" \
        || log "Step 4 FAILED: generate_syntheses.py"
else
    log "Step 4: Skipping syntheses (generate_syntheses.py not found)"
fi

# Step 5: Copy output to app data directory
log "Step 5: Copying output files..."
for f in articles.json concepts.json manifest.json; do
    if [ -f "$PROJECT_DIR/data/$f" ]; then
        cp "$PROJECT_DIR/data/$f" "$PROJECT_DIR/app/data/"
    else
        log "WARNING: $PROJECT_DIR/data/$f not found, skipping"
    fi
done
log "Copied to $PROJECT_DIR/app/data/"

if [ -d "/opt/petrarca/data" ]; then
    for f in articles.json concepts.json manifest.json; do
        if [ -f "$PROJECT_DIR/data/$f" ]; then
            cp "$PROJECT_DIR/data/$f" /opt/petrarca/data/
        fi
    done
    log "Copied to /opt/petrarca/data/ (HTTP serving)"
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
log "=== Content refresh complete in ${ELAPSED}s ==="
