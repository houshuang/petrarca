#!/usr/bin/env python3
"""Import individual URLs into Petrarca's article database.

Reuses fetch_article, LLM processing, and concept extraction from build_articles.py
but for importing one or more URLs manually (not from Twitter/Readwise sources).

Usage:
    python3 scripts/import_url.py "https://en.wikipedia.org/wiki/History_of_Sicily"
    python3 scripts/import_url.py --urls-file urls.txt
    python3 scripts/import_url.py --from-exploration data/explorations/sicily.json
    python3 scripts/import_url.py "https://..." --chunk
    python3 scripts/import_url.py "https://..." --tag exploration --exploration-tag sicily
    python3 scripts/import_url.py "https://..." --dry-run
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Import shared functions from build_articles.py
sys.path.insert(0, str(Path(__file__).parent))
from build_articles import (
    fetch_article,
    _call_claude,
    _build_article_prompt,
    _article_id,
    _save_json,
    _load_json,
    _split_into_sections,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
CONCEPTS_PATH = DATA_DIR / "concepts.json"

# ---------------------------------------------------------------------------
# Chunking (split long articles at H2 boundaries)
# ---------------------------------------------------------------------------

def _chunk_at_h2(text: str, min_words: int = 200) -> list[dict]:
    """Split markdown text at H2 (##) boundaries.

    Returns list of {heading, content} dicts. Sections shorter than
    min_words are merged into the previous chunk.
    """
    pattern = re.compile(r'^##\s+(.+)$', re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [{"heading": "Full Article", "content": text}]

    chunks = []

    # Content before first H2
    preamble = text[:matches[0].start()].strip()
    if preamble and len(preamble.split()) >= min_words:
        chunks.append({"heading": "Introduction", "content": preamble})

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        if len(content.split()) < min_words and chunks:
            # Merge short section into previous
            chunks[-1]["content"] += f"\n\n## {heading}\n\n{content}"
        else:
            chunks.append({"heading": heading, "content": content})

    # If preamble was too short and we have chunks, prepend it
    if preamble and len(preamble.split()) < min_words and chunks:
        chunks[0]["content"] = preamble + "\n\n" + chunks[0]["content"]

    return chunks


# ---------------------------------------------------------------------------
# LLM processing (mirrors build_articles.py pipeline)
# ---------------------------------------------------------------------------

def _process_with_llm(fetched: dict, dry_run: bool = False) -> dict:
    """Run LLM analysis on fetched article content. Returns parsed LLM output."""
    title = fetched["title"] or "Untitled"
    word_count = fetched["word_count"]

    if dry_run:
        print(f"  [dry-run] Would process: {title[:60]} ({word_count} words)", file=sys.stderr)
        return {
            "title": title,
            "one_line_summary": "[dry run]",
            "full_summary": "[dry run]",
            "sections": [],
            "key_claims": [],
            "topics": [],
            "estimated_read_minutes": max(1, word_count // 200),
            "content_type": "unknown",
        }

    print(f"  Processing with LLM: {title[:60]} ({word_count} words)", file=sys.stderr)
    prompt = _build_article_prompt(fetched["text"], title)
    response = _call_claude(prompt)

    if response:
        try:
            cleaned = response
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
            llm = json.loads(cleaned)
            print(f"    OK: {llm.get('content_type', '?')}, {len(llm.get('sections', []))} sections", file=sys.stderr)
            return llm
        except json.JSONDecodeError:
            print(f"    JSON parse failed, using fallback", file=sys.stderr)

    # Fallback
    return {
        "title": title,
        "one_line_summary": fetched["text"][:120],
        "full_summary": fetched["text"][:500],
        "sections": [],
        "key_claims": [],
        "topics": [],
        "estimated_read_minutes": max(1, word_count // 200),
        "content_type": "unknown",
    }


def _build_article_obj(
    fetched: dict,
    llm: dict,
    url: str,
    source_tag: str = "manual",
    exploration_tag: str | None = None,
    parent_id: str | None = None,
    article_id: str | None = None,
    reading_order: str | None = None,
) -> dict:
    """Build an article dict matching the Article interface."""
    aid = article_id or _article_id(url)
    section_contents = _split_into_sections(fetched["text"], llm.get("sections", []))

    article = {
        "id": aid,
        "title": llm.get("title", fetched["title"]) or fetched["title"] or "Untitled",
        "author": fetched.get("author", ""),
        "source_url": url,
        "hostname": fetched.get("hostname", "") or urlparse(url).netloc,
        "date": fetched.get("date", "") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "content_markdown": fetched["text"],
        "sections": section_contents,
        "one_line_summary": llm.get("one_line_summary", ""),
        "full_summary": llm.get("full_summary", ""),
        "key_claims": llm.get("key_claims", []),
        "topics": llm.get("topics", []),
        "estimated_read_minutes": llm.get("estimated_read_minutes", max(1, fetched["word_count"] // 200)),
        "content_type": llm.get("content_type", "unknown"),
        "word_count": fetched["word_count"],
        "sources": [{"type": source_tag}],
    }

    if exploration_tag:
        article["exploration_tag"] = exploration_tag
    if parent_id:
        article["parent_id"] = parent_id
    if reading_order:
        article["reading_order"] = reading_order

    return article


# ---------------------------------------------------------------------------
# Concept extraction for newly imported articles
# ---------------------------------------------------------------------------

def _extract_concepts_for_articles(articles: list[dict], existing_concepts: list[dict],
                                    dry_run: bool = False) -> list[dict]:
    """Extract concepts from newly imported articles and merge with existing."""
    if dry_run:
        print("  [dry-run] Would extract concepts", file=sys.stderr)
        return existing_concepts

    from build_articles import extract_concepts
    new_concepts = extract_concepts(articles, dry_run=False)

    if not new_concepts:
        return existing_concepts

    # Merge: add new concepts, skip duplicates by ID
    existing_ids = {c["id"] for c in existing_concepts}
    added = 0
    for c in new_concepts:
        if c["id"] not in existing_ids:
            existing_concepts.append(c)
            existing_ids.add(c["id"])
            added += 1

    print(f"  Added {added} new concepts (total: {len(existing_concepts)})", file=sys.stderr)
    return existing_concepts


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def import_single_url(
    url: str,
    articles: list[dict],
    source_tag: str = "manual",
    exploration_tag: str | None = None,
    reading_order: str | None = None,
    chunk: bool = False,
    dry_run: bool = False,
    content_text: str | None = None,
) -> list[dict]:
    """Import a single URL. Returns list of new article dicts added.

    If content_text is provided, it is used as the article body instead of
    fetching the URL. This supports the /ingest endpoint where the Chrome
    extension already extracted the page content.
    """
    # Check for duplicate
    existing_urls = {a.get("source_url", "") for a in articles}
    if url in existing_urls:
        print(f"  SKIP (already exists): {url[:80]}", file=sys.stderr)
        return []

    if content_text and len(content_text.strip()) > 100:
        print(f"\n  Using pre-extracted content for: {url[:80]}...", file=sys.stderr)
        fetched = {
            "title": "",
            "text": content_text,
            "word_count": len(content_text.split()),
            "fetch_method": "pre-extracted",
            "author": "",
            "hostname": urlparse(url).netloc,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    else:
        print(f"\n  Fetching: {url[:80]}...", file=sys.stderr)
        fetched = fetch_article(url)

    if not fetched:
        print(f"  FAIL: no content extracted from {url[:80]}", file=sys.stderr)
        return []

    print(f"    {fetched['word_count']} words via {fetched['fetch_method']}: {fetched['title'][:60]}", file=sys.stderr)

    new_articles = []

    # Chunking mode for long articles
    if chunk and fetched["word_count"] > 3000:
        chunks = _chunk_at_h2(fetched["text"])
        if len(chunks) <= 1:
            print(f"    No H2 boundaries found, importing as single article", file=sys.stderr)
            chunk = False
        else:
            print(f"    Splitting into {len(chunks)} sub-articles", file=sys.stderr)

            parent_id = None
            for i, ch in enumerate(chunks):
                chunk_fetched = dict(fetched)
                chunk_fetched["text"] = ch["content"]
                chunk_fetched["word_count"] = len(ch["content"].split())
                chunk_fetched["title"] = f"{fetched['title']} — {ch['heading']}"

                chunk_url = f"{url}#chunk-{i}"
                chunk_aid = _article_id(chunk_url)

                if any(a["id"] == chunk_aid for a in articles):
                    print(f"    SKIP chunk {i} (already exists): {ch['heading'][:40]}", file=sys.stderr)
                    if i == 0:
                        parent_id = chunk_aid
                    continue

                llm = _process_with_llm(chunk_fetched, dry_run=dry_run)

                article = _build_article_obj(
                    chunk_fetched, llm, url,
                    source_tag=source_tag,
                    exploration_tag=exploration_tag,
                    parent_id=parent_id if i > 0 else None,
                    article_id=chunk_aid,
                    reading_order=reading_order,
                )
                # Override source_url to keep original, not the chunk URL
                article["source_url"] = url

                if i == 0:
                    parent_id = chunk_aid

                new_articles.append(article)

                if not dry_run:
                    time.sleep(1)

            return new_articles

    # Single article (no chunking)
    llm = _process_with_llm(fetched, dry_run=dry_run)
    article = _build_article_obj(
        fetched, llm, url,
        source_tag=source_tag,
        exploration_tag=exploration_tag,
        reading_order=reading_order,
    )
    new_articles.append(article)
    return new_articles


def load_urls_from_file(path: str) -> list[str]:
    """Read one URL per line from a text file, skipping blanks and comments."""
    urls = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def load_urls_from_exploration(path: str) -> tuple[list[str], str, dict[str, str]]:
    """Load URLs from an exploration JSON file.

    Expected format:
    {
        "topic": "History of Sicily",
        "exploration_tag": "sicily",
        "subtopics": [
            {
                "name": "...",
                "reading_order": "foundational" | "intermediate" | "deep",
                "urls": ["https://...", ...]
            },
            ...
        ]
    }

    Returns (urls, exploration_tag, url_reading_orders).
    """
    data = json.loads(Path(path).read_text())
    tag = data.get("exploration_tag", data.get("topic", "exploration").lower().replace(" ", "-"))

    urls = []
    url_reading_orders: dict[str, str] = {}
    for subtopic in data.get("subtopics", []):
        reading_order = subtopic.get("reading_order", "")
        for url in subtopic.get("urls", []):
            if url not in urls:
                urls.append(url)
            if reading_order and url not in url_reading_orders:
                url_reading_orders[url] = reading_order

    return urls, tag, url_reading_orders


def update_manifest(articles: list[dict], concepts: list[dict]):
    """Write manifest.json with current counts and hashes."""
    manifest = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "concept_count": len(concepts),
        "articles_hash": hashlib.sha256(
            json.dumps(articles, sort_keys=True).encode()
        ).hexdigest()[:16],
        "concepts_hash": hashlib.sha256(
            json.dumps(concepts, sort_keys=True).encode()
        ).hexdigest()[:16],
    }
    _save_json(manifest, DATA_DIR / "manifest.json")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import individual URLs into Petrarca's article database"
    )
    parser.add_argument("urls", nargs="*", help="URLs to import")
    parser.add_argument("--urls-file", help="File with one URL per line")
    parser.add_argument("--from-exploration", help="Exploration JSON file to import URLs from")
    parser.add_argument("--tag", choices=["manual", "exploration", "research_recommendation"],
                        default="manual", help="Source tag (default: manual)")
    parser.add_argument("--exploration-tag", help="Tag for grouping exploration articles")
    parser.add_argument("--chunk", action="store_true",
                        help="Split long articles at H2 boundaries (>3000 words)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    parser.add_argument("--no-concepts", action="store_true",
                        help="Skip concept extraction")
    parser.add_argument("--content-file",
                        help="Read pre-extracted article content from this file instead of fetching the URL")
    args = parser.parse_args()

    # Collect URLs from all input modes
    urls = list(args.urls)
    exploration_tag = args.exploration_tag
    url_reading_orders: dict[str, str] = {}

    if args.urls_file:
        urls.extend(load_urls_from_file(args.urls_file))

    if args.from_exploration:
        exploration_urls, expl_tag, expl_reading_orders = load_urls_from_exploration(args.from_exploration)
        urls.extend(exploration_urls)
        url_reading_orders.update(expl_reading_orders)
        if not exploration_tag:
            exploration_tag = expl_tag
        if args.tag == "manual":
            args.tag = "exploration"

    if not urls:
        parser.error("No URLs provided. Pass URLs as arguments, --urls-file, or --from-exploration.")

    # Deduplicate input URLs while preserving order
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
    urls = unique_urls

    print(f"Importing {len(urls)} URL(s), tag={args.tag}", file=sys.stderr)
    if exploration_tag:
        print(f"  exploration_tag: {exploration_tag}", file=sys.stderr)
    if args.chunk:
        print(f"  chunking enabled (split at H2 for articles >3000 words)", file=sys.stderr)
    if args.dry_run:
        print(f"  DRY RUN — no LLM calls", file=sys.stderr)

    # Load existing data
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    articles = _load_json(ARTICLES_PATH) or []
    concepts = _load_json(CONCEPTS_PATH) or []

    # Read pre-extracted content if provided
    pre_content = None
    if args.content_file:
        content_path = Path(args.content_file)
        if content_path.exists():
            pre_content = content_path.read_text()
            print(f"  Using pre-extracted content from: {args.content_file} ({len(pre_content)} chars)", file=sys.stderr)
        else:
            print(f"  WARNING: content file not found: {args.content_file}", file=sys.stderr)

    print(f"  Existing: {len(articles)} articles, {len(concepts)} concepts", file=sys.stderr)

    # Process each URL
    all_new = []
    for i, url in enumerate(urls):
        print(f"\n[{i+1}/{len(urls)}] {url[:80]}", file=sys.stderr)
        new_articles = import_single_url(
            url, articles,
            source_tag=args.tag,
            exploration_tag=exploration_tag,
            reading_order=url_reading_orders.get(url),
            chunk=args.chunk,
            dry_run=args.dry_run,
            content_text=pre_content if i == 0 else None,
        )
        for article in new_articles:
            articles.append(article)
            all_new.append(article)
            # Save incrementally
            _save_json(articles, ARTICLES_PATH)

    if not all_new:
        print(f"\nNo new articles imported.", file=sys.stderr)
        return

    # Save to both data/ and app/data/
    _save_json(articles, ARTICLES_PATH)
    _save_json(articles, APP_DATA_DIR / "articles.json")
    print(f"\n  Saved {len(articles)} articles", file=sys.stderr)

    # Extract concepts for new articles
    if not args.no_concepts:
        print(f"\n=== Extracting concepts ===", file=sys.stderr)
        concepts = _extract_concepts_for_articles(all_new, concepts, dry_run=args.dry_run)
        _save_json(concepts, CONCEPTS_PATH)
        _save_json(concepts, APP_DATA_DIR / "concepts.json")

    # Update manifest
    update_manifest(articles, concepts)

    # Summary
    print(f"\n=== Done ===", file=sys.stderr)
    print(f"  Imported {len(all_new)} new article(s)", file=sys.stderr)
    for a in all_new:
        parent = f" (parent: {a['parent_id']})" if a.get("parent_id") else ""
        print(f"    [{a['id']}] {a['title'][:60]}{parent}", file=sys.stderr)
    print(f"  Total: {len(articles)} articles, {len(concepts)} concepts", file=sys.stderr)


if __name__ == "__main__":
    main()
