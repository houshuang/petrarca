#!/usr/bin/env python3
"""Fetch documents and highlights from Readwise Reader API v3.

Usage:
    # Set token in .env or environment:
    echo "READWISE_ACCESS_TOKEN=xxx" >> .env

    # Fetch all documents + highlights:
    python3 scripts/fetch_readwise_reader.py --save

    # Fetch only articles:
    python3 scripts/fetch_readwise_reader.py --category article --save

    # Incremental update (only new/changed since last fetch):
    python3 scripts/fetch_readwise_reader.py --save --incremental

    # Search fetched documents:
    python3 scripts/fetch_readwise_reader.py --search "knowledge management"

Saved to data/readwise_reader.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VENV_SITE = str(Path(__file__).parent.parent / ".venv/lib/python3.12/site-packages")
if os.path.exists(VENV_SITE):
    sys.path.insert(0, VENV_SITE)

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_PATH = DATA_DIR / "readwise_reader.json"
BASE_URL = "https://readwise.io/api/v3"
RATE_LIMIT_RPM = 20
MIN_INTERVAL = 60.0 / RATE_LIMIT_RPM  # 3 seconds between requests


def load_token() -> str:
    token = os.environ.get("READWISE_ACCESS_TOKEN")
    if token:
        return token

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("READWISE_ACCESS_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")

    print("ERROR: READWISE_ACCESS_TOKEN not found.", file=sys.stderr)
    print("Set it in .env or as an environment variable.", file=sys.stderr)
    print("Get your token at: https://readwise.io/access_token", file=sys.stderr)
    sys.exit(1)


def api_get(token: str, endpoint: str, params: dict | None = None) -> dict:
    headers = {"Authorization": f"Token {token}"}
    url = f"{BASE_URL}/{endpoint}/"

    while True:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            print(f"  Rate limited, waiting {retry_after}s...", file=sys.stderr)
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        return resp.json()


def fetch_all_documents(
    token: str,
    category: str | None = None,
    location: str | None = None,
    updated_after: str | None = None,
) -> list[dict]:
    """Fetch all documents, paginating through cursor-based results."""
    documents = []
    params = {}
    if category:
        params["category"] = category
    if location:
        params["location"] = location
    if updated_after:
        params["updatedAfter"] = updated_after

    cursor = None
    page = 0

    while True:
        if cursor:
            params["pageCursor"] = cursor

        page += 1
        data = api_get(token, "list", params)
        results = data.get("results", [])
        documents.extend(results)

        print(f"  Page {page}: {len(results)} documents (total: {len(documents)})", file=sys.stderr)

        cursor = data.get("nextPageCursor")
        if not cursor:
            break

        time.sleep(MIN_INTERVAL)

    return documents


def organize_documents(raw_documents: list[dict]) -> list[dict]:
    """Attach highlights/notes as children of their parent documents."""
    parents = {}
    children = []

    for doc in raw_documents:
        if doc.get("parent_id"):
            children.append(doc)
        else:
            doc["highlights"] = []
            parents[doc["id"]] = doc

    for child in children:
        parent_id = child["parent_id"]
        if parent_id in parents:
            parents[parent_id]["highlights"].append({
                "id": child["id"],
                "category": child.get("category"),
                "title": child.get("title"),
                "summary": child.get("summary"),
                "notes": child.get("notes"),
                "url": child.get("url"),
                "created_at": child.get("created_at"),
                "tags": child.get("tags", {}),
            })

    return list(parents.values())


def search_documents(documents: list[dict], query: str) -> list[dict]:
    terms = query.lower().split()
    results = []
    for doc in documents:
        searchable = " ".join(filter(None, [
            doc.get("title", ""),
            doc.get("author", ""),
            doc.get("summary", ""),
            doc.get("notes", ""),
            doc.get("site_name", ""),
            " ".join(doc.get("tags", {}).keys()),
            " ".join(h.get("title", "") or "" for h in doc.get("highlights", [])),
            " ".join(h.get("notes", "") or "" for h in doc.get("highlights", [])),
        ])).lower()
        if all(t in searchable for t in terms):
            results.append(doc)
    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch Readwise Reader documents")
    parser.add_argument("--category", type=str,
                        help="Filter: article, email, rss, highlight, note, pdf, epub, tweet, video")
    parser.add_argument("--location", type=str,
                        help="Filter: new, later, shortlist, archive, feed")
    parser.add_argument("--save", action="store_true",
                        help="Save to data/readwise_reader.json")
    parser.add_argument("--incremental", action="store_true",
                        help="Only fetch documents updated since last save")
    parser.add_argument("--search", type=str,
                        help="Search saved documents by keyword")
    parser.add_argument("--stats", action="store_true",
                        help="Show statistics about saved documents")
    args = parser.parse_args()

    if args.search or args.stats:
        if not OUTPUT_PATH.exists():
            print("No saved data. Run with --save first.", file=sys.stderr)
            sys.exit(1)
        documents = json.loads(OUTPUT_PATH.read_text())

        if args.stats:
            categories = {}
            for doc in documents:
                cat = doc.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1
            total_highlights = sum(len(doc.get("highlights", [])) for doc in documents)
            print(f"Total documents: {len(documents)}")
            print(f"Total highlights: {total_highlights}")
            print("By category:")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
                print(f"  {cat}: {count}")
            return

        if args.search:
            results = search_documents(documents, args.search)
            print(f"Found {len(results)} matching '{args.search}'", file=sys.stderr)
            for doc in results:
                hl_count = len(doc.get("highlights", []))
                hl_str = f" [{hl_count} highlights]" if hl_count else ""
                print(f"  - {doc.get('title', '(untitled)')}{hl_str}")
                print(f"    {doc.get('url', '')}")
            return

    token = load_token()

    # Validate token
    resp = requests.get("https://readwise.io/api/v2/auth/", headers={"Authorization": f"Token {token}"})
    if resp.status_code != 204:
        print(f"ERROR: Token validation failed (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)
    print("Token validated", file=sys.stderr)

    updated_after = None
    if args.incremental and OUTPUT_PATH.exists():
        existing = json.loads(OUTPUT_PATH.read_text())
        latest = max(
            (doc.get("updated_at", "") for doc in existing),
            default=None,
        )
        if latest:
            updated_after = latest
            print(f"Incremental: fetching updates since {latest}", file=sys.stderr)

    print("Fetching documents...", file=sys.stderr)
    raw = fetch_all_documents(
        token,
        category=args.category,
        location=args.location,
        updated_after=updated_after,
    )
    print(f"Fetched {len(raw)} raw items", file=sys.stderr)

    documents = organize_documents(raw)
    print(f"Organized into {len(documents)} documents", file=sys.stderr)

    try:
        from server_log import log_server_event
        log_server_event('readwise_fetched', count=len(raw), documents=len(documents))
    except ImportError:
        pass

    if args.incremental and OUTPUT_PATH.exists():
        existing = json.loads(OUTPUT_PATH.read_text())
        existing_by_id = {doc["id"]: doc for doc in existing}
        for doc in documents:
            existing_by_id[doc["id"]] = doc
        documents = list(existing_by_id.values())
        print(f"Merged: {len(documents)} total documents", file=sys.stderr)

    total_highlights = sum(len(doc.get("highlights", [])) for doc in documents)
    print(f"Total highlights: {total_highlights}", file=sys.stderr)

    output = json.dumps(documents, indent=2, ensure_ascii=False)

    if args.save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(output)
        print(f"Saved to {OUTPUT_PATH}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
