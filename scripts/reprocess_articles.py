#!/usr/bin/env python3
"""Reprocess articles that have missing LLM analysis (content_type: unknown, 0 claims).

Also removes obvious junk articles (account pages, login pages, etc.)

Usage:
    python3 scripts/reprocess_articles.py              # reprocess all broken articles
    python3 scripts/reprocess_articles.py --dry-run     # just show what would be done
    python3 scripts/reprocess_articles.py --delete-junk  # also remove junk articles
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_articles import (
    fetch_article,
    _call_llm,
    _build_article_prompt,
    _split_into_sections,
    _save_json,
    _load_json,
)

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
APP_DATA_DIR = SCRIPT_DIR.parent / "app" / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
CONCEPTS_PATH = DATA_DIR / "concepts.json"

JUNK_PATTERNS = [
    "my account", "sign in", "log in", "login", "upgrade to paid",
    "404 not found", "page not found", "access denied",
]


def is_junk(article: dict) -> bool:
    title = (article.get("title") or "").lower()
    summary = (article.get("one_line_summary") or "").lower()
    text = title + " " + summary
    return any(p in text for p in JUNK_PATTERNS)


def needs_reprocessing(article: dict) -> bool:
    if article.get("content_type") == "unknown":
        return True
    if not article.get("key_claims"):
        return True
    if not article.get("topics"):
        return True
    return False


def reprocess_article(article: dict, dry_run: bool = False) -> dict:
    """Re-run LLM analysis on an article."""
    url = article.get("source_url", "")
    content = article.get("content_markdown", "")
    title = article.get("title", "Untitled")

    if not content or len(content.strip()) < 100:
        print(f"  Refetching content for: {url[:80]}", file=sys.stderr)
        if dry_run:
            return article
        fetched = fetch_article(url)
        if fetched and fetched.get("text"):
            content = fetched["text"]
            article["content_markdown"] = content
            article["word_count"] = fetched["word_count"]
            if fetched.get("title"):
                title = fetched["title"]

    if not content or len(content.strip()) < 100:
        print(f"  SKIP: no content available for {url[:80]}", file=sys.stderr)
        return article

    if dry_run:
        print(f"  [dry-run] Would reprocess: {title[:60]}", file=sys.stderr)
        return article

    print(f"  Processing: {title[:60]} ({len(content.split())} words)", file=sys.stderr)
    prompt = _build_article_prompt(content, title)
    response = _call_llm(prompt, provider="gemini")

    if not response:
        print(f"  LLM call failed for: {title[:60]}", file=sys.stderr)
        return article

    import re
    cleaned = response
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)

    try:
        llm = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"  JSON parse failed for: {title[:60]}", file=sys.stderr)
        return article

    # Update article with LLM results
    article["title"] = llm.get("title", title)
    article["one_line_summary"] = llm.get("one_line_summary", "")
    article["full_summary"] = llm.get("full_summary", "")
    article["key_claims"] = llm.get("key_claims", [])
    article["topics"] = llm.get("topics", [])
    article["content_type"] = llm.get("content_type", "unknown")
    article["estimated_read_minutes"] = llm.get("estimated_read_minutes", max(1, len(content.split()) // 200))

    # Rebuild sections
    section_contents = _split_into_sections(content, llm.get("sections", []))
    article["sections"] = section_contents

    print(f"    OK: {article['content_type']}, {len(article['key_claims'])} claims, {len(article['sections'])} sections", file=sys.stderr)
    return article


def main():
    parser = argparse.ArgumentParser(description="Reprocess broken articles")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delete-junk", action="store_true", help="Remove junk articles")
    args = parser.parse_args()

    articles = _load_json(ARTICLES_PATH) or []
    print(f"Loaded {len(articles)} articles", file=sys.stderr)

    # Find and optionally delete junk
    if args.delete_junk:
        junk = [a for a in articles if is_junk(a)]
        if junk:
            print(f"\nJunk articles ({len(junk)}):", file=sys.stderr)
            for a in junk:
                print(f"  [{a['id']}] {a.get('title', '?')[:60]}", file=sys.stderr)
            if not args.dry_run:
                articles = [a for a in articles if not is_junk(a)]
                print(f"  Removed {len(junk)} junk articles", file=sys.stderr)

    # Find articles needing reprocessing
    broken = [(i, a) for i, a in enumerate(articles) if needs_reprocessing(a)]
    print(f"\nArticles needing reprocessing: {len(broken)}", file=sys.stderr)

    for idx, (i, article) in enumerate(broken):
        title = article.get("title", "?")[:60]
        claims = len(article.get("key_claims", []))
        ctype = article.get("content_type", "?")
        print(f"\n[{idx+1}/{len(broken)}] {title} (claims={claims}, type={ctype})", file=sys.stderr)

        articles[i] = reprocess_article(article, dry_run=args.dry_run)

        if not args.dry_run:
            time.sleep(0.5)

    if not args.dry_run and (broken or args.delete_junk):
        _save_json(articles, ARTICLES_PATH)
        _save_json(articles, APP_DATA_DIR / "articles.json")
        print(f"\nSaved {len(articles)} articles", file=sys.stderr)

        # Update manifest
        import hashlib
        from datetime import datetime, timezone
        concepts = _load_json(CONCEPTS_PATH) or []
        manifest = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "article_count": len(articles),
            "concept_count": len(concepts),
            "articles_hash": hashlib.sha256(json.dumps(articles, sort_keys=True).encode()).hexdigest()[:16],
            "concepts_hash": hashlib.sha256(json.dumps(concepts, sort_keys=True).encode()).hexdigest()[:16],
        }
        _save_json(manifest, DATA_DIR / "manifest.json")
        print("Manifest updated", file=sys.stderr)


if __name__ == "__main__":
    main()
