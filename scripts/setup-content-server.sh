#!/bin/bash
# Setup nginx content server and pipeline cron on Hetzner
# Run this once on the server to enable content refresh

set -e

PETRARCA_DIR="/opt/petrarca"
CONTENT_DIR="$PETRARCA_DIR/data"
SOURCES_DIR="$PETRARCA_DIR/data/sources"

echo "=== Setting up Petrarca content refresh ==="

# Create directories
sudo mkdir -p "$CONTENT_DIR" "$SOURCES_DIR"
sudo chown -R stian:stian "$PETRARCA_DIR"

# nginx config for loopback-only content serving on port 8083. Never alias the
# whole data directory: it also contains the canonical DB, recordings, logs,
# feedback, and caches.
sudo tee /etc/nginx/sites-available/petrarca-content > /dev/null <<'NGINX'
server {
    listen 127.0.0.1:8083;
    server_name alifstian.duckdns.org;

    location = /content/manifest.json {
        alias /opt/petrarca/data/manifest.json;
        default_type application/json;
        limit_except GET { deny all; }
        add_header Access-Control-Allow-Origin "*";
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options "nosniff";
    }

    location = /content/articles.json {
        alias /opt/petrarca/data/articles.json;
        default_type application/json;
        limit_except GET { deny all; }
        add_header Access-Control-Allow-Origin "*";
        add_header Cache-Control "public, max-age=300";
        add_header X-Content-Type-Options "nosniff";
    }

    location = /content/knowledge_index.json {
        alias /opt/petrarca/data/knowledge_index.json;
        default_type application/json;
        limit_except GET { deny all; }
        add_header Access-Control-Allow-Origin "*";
        add_header Cache-Control "public, max-age=300";
        add_header X-Content-Type-Options "nosniff";
    }

    location = /content/concept_clusters.json {
        alias /opt/petrarca/data/concept_clusters.json;
        default_type application/json;
        limit_except GET { deny all; }
        add_header Access-Control-Allow-Origin "*";
        add_header Cache-Control "public, max-age=300";
        add_header X-Content-Type-Options "nosniff";
    }

    location = /content/syntheses.json {
        alias /opt/petrarca/data/syntheses.json;
        default_type application/json;
        limit_except GET { deny all; }
        add_header Access-Control-Allow-Origin "*";
        add_header Cache-Control "public, max-age=300";
        add_header X-Content-Type-Options "nosniff";
    }

    location /content/ {
        return 404;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/petrarca-content /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Cron for daily pipeline run at 7 AM UTC
sudo tee /etc/cron.d/petrarca-refresh > /dev/null <<'CRON'
PETRARCA_SOURCES=/opt/petrarca/data/sources
0 7 * * * stian cd /opt/petrarca && python3 scripts/build_articles.py --limit 10 >> /var/log/petrarca-refresh.log 2>&1
CRON

echo "=== Done ==="
echo "Content is loopback-only on :8083; expose only the allowlisted files through HTTPS nginx."
echo "Pipeline runs daily at 7 AM UTC"
echo ""
echo "To sync source data from Mac, run:"
echo "  rsync -az ~/src/otak/data/twitter_bookmarks.json ~/src/otak/data/readwise_reader.json alif:/opt/petrarca/data/sources/"
