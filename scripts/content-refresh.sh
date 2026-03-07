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

# Load environment (includes GEMINI_KEY, READWISE_ACCESS_TOKEN, etc.)
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

# Step 3b: Validate and fix articles
log "Step 3b: Validating articles..."
python3 "$SCRIPT_DIR/validate_articles.py" --fix \
    || log "Step 3b FAILED: validate_articles.py"

# Step 3c: Extract entity concepts for new articles (incremental)
log "Step 3c: Extracting entity concepts for new articles..."
python3 "$SCRIPT_DIR/extract_entity_concepts.py" --incremental \
    || log "Step 3c FAILED: extract_entity_concepts.py"

# Step 4: Syntheses (disabled — generate_syntheses.py removed)
# log "Step 4: Generating syntheses..."
# python3 "$SCRIPT_DIR/generate_syntheses.py"

# Step 5: Generate books manifest from individual book meta files
BOOKS_DIR="$PROJECT_DIR/data/books"
if [ -d "$BOOKS_DIR" ] && ls "$BOOKS_DIR"/*/meta.json 1>/dev/null 2>&1; then
    log "Step 5: Generating books.json manifest..."
    python3 -c "
import json, pathlib, hashlib
books_dir = pathlib.Path('$BOOKS_DIR')
books = []
for meta_file in sorted(books_dir.glob('*/meta.json')):
    meta = json.loads(meta_file.read_text())
    # Strip fields only needed by pipeline, keep what app needs
    books.append({
        'id': meta['id'],
        'title': meta['title'],
        'author': meta['author'],
        'cover_url': meta.get('cover_url'),
        'chapters': meta['chapters'],
        'topics': meta.get('topics', []),
        'thesis_statement': meta.get('thesis_statement'),
        'running_argument': meta.get('running_argument', []),
        'language': meta.get('language', 'en'),
        'added_at': meta.get('added_at', 0),
    })
out = json.dumps(books, indent=2, ensure_ascii=False)
(books_dir.parent / 'books.json').write_text(out)
# Update manifest hash
manifest_path = books_dir.parent / 'manifest.json'
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text())
    manifest['books_hash'] = hashlib.sha256(out.encode()).hexdigest()[:16]
    manifest_path.write_text(json.dumps(manifest, indent=2))
print(f'Generated books.json with {len(books)} books')
" || log "Step 5 FAILED: books manifest generation"
else
    log "Step 5: No books found, skipping books.json generation"
fi

# Step 6: Copy output to app data directory (with file size validation)
log "Step 6: Copying output files..."
for f in articles.json concepts.json manifest.json books.json; do
    if [ -s "$PROJECT_DIR/data/$f" ]; then
        cp "$PROJECT_DIR/data/$f" "$PROJECT_DIR/app/data/"
    elif [ -f "$PROJECT_DIR/data/$f" ]; then
        log "WARNING: $f is empty, skipping copy to app/data"
    else
        log "WARNING: $PROJECT_DIR/data/$f not found, skipping"
    fi
done
log "Copied to $PROJECT_DIR/app/data/"

if [ -d "/opt/petrarca/data" ]; then
    for f in articles.json concepts.json manifest.json books.json; do
        if [ -s "$PROJECT_DIR/data/$f" ]; then
            cp "$PROJECT_DIR/data/$f" /opt/petrarca/data/
        else
            log "WARNING: $f is empty or missing, skipping copy to /opt/petrarca/data/"
        fi
    done
    # Also copy book chapter section files
    if [ -d "$PROJECT_DIR/data/books" ]; then
        mkdir -p /opt/petrarca/data/books
        cp -r "$PROJECT_DIR/data/books"/* /opt/petrarca/data/books/ 2>/dev/null \
            || log "Note: no book data to copy"
    fi
    log "Copied to /opt/petrarca/data/ (HTTP serving)"
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
log "=== Content refresh complete in ${ELAPSED}s ==="
