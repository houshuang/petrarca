#!/usr/bin/env python3
"""Validate and optionally fix articles.json data quality issues.

Usage:
    python3 scripts/validate_articles.py              # report issues
    python3 scripts/validate_articles.py --fix        # fix and save
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
CONCEPTS_PATH = DATA_DIR / "concepts.json"

BOILERPLATE_PATTERNS = [
    re.compile(r"bitcoin", re.IGNORECASE),
    re.compile(r"donation", re.IGNORECASE),
    re.compile(r"downloads last month", re.IGNORECASE),
    re.compile(r"buy me a coffee", re.IGNORECASE),
    re.compile(r"patreon\.com", re.IGNORECASE),
    re.compile(r"paypal\.me", re.IGNORECASE),
    re.compile(r"subscribe to our newsletter", re.IGNORECASE),
]


def is_valid_section(heading: str, content: str) -> bool:
    h = heading.strip()
    if h in ("[", "") or h.startswith("](#"):
        return False
    if len(content.strip()) < 20:
        return False
    return True


def strip_boilerplate_tail(markdown: str) -> str:
    """Remove trailing boilerplate from article content."""
    lines = markdown.rstrip().split("\n")
    # Walk backwards, removing lines that match boilerplate
    while lines:
        tail = "\n".join(lines[-10:])  # check last 10 lines
        has_boilerplate = any(p.search(tail) for p in BOILERPLATE_PATTERNS)
        if not has_boilerplate:
            break
        # Remove last paragraph (up to empty line)
        while lines and lines[-1].strip():
            lines.pop()
        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()
    return "\n".join(lines)


def validate_articles(articles: list[dict], fix: bool = False) -> tuple[list[dict], dict]:
    """Validate articles and optionally fix issues. Returns (articles, stats)."""
    stats = {
        "total": len(articles),
        "bad_headings_removed": 0,
        "short_sections_removed": 0,
        "boilerplate_stripped": 0,
        "articles_removed": 0,
    }

    fixed = []
    for article in articles:
        # Check content
        if not article.get("content_markdown") or len(article["content_markdown"]) < 100:
            if fix:
                stats["articles_removed"] += 1
                print(f"  REMOVE: {article['id']} — content too short ({len(article.get('content_markdown', ''))} chars)", file=sys.stderr)
                continue
            else:
                print(f"  ISSUE: {article['id']} — content too short", file=sys.stderr)

        # Check key_claims
        if not article.get("key_claims"):
            if fix:
                stats["articles_removed"] += 1
                print(f"  REMOVE: {article['id']} — no key claims: {article.get('title', '')[:60]}", file=sys.stderr)
                continue
            else:
                print(f"  ISSUE: {article['id']} — no key claims: {article.get('title', '')[:60]}", file=sys.stderr)

        # Check/fix sections
        sections = article.get("sections", [])
        valid_sections = []
        for s in sections:
            if is_valid_section(s.get("heading", ""), s.get("content", "")):
                valid_sections.append(s)
            else:
                h = s.get("heading", "")
                c_len = len(s.get("content", "").strip())
                if h == "[" or h.startswith("](#"):
                    stats["bad_headings_removed"] += 1
                    if not fix:
                        print(f"  ISSUE: {article['id']} — bad heading: '{h}'", file=sys.stderr)
                elif c_len < 20:
                    stats["short_sections_removed"] += 1
                    if not fix:
                        print(f"  ISSUE: {article['id']} — short section '{h}' ({c_len} chars)", file=sys.stderr)

        if fix:
            article["sections"] = valid_sections
            # Ensure at least one section
            if not valid_sections and article.get("content_markdown"):
                article["sections"] = [{
                    "heading": "Full Article",
                    "content": article["content_markdown"],
                    "summary": article.get("full_summary", ""),
                    "key_claims": article.get("key_claims", []),
                }]

        # Check/fix boilerplate
        tail = (article.get("content_markdown") or "")[-500:]
        has_boilerplate = any(p.search(tail) for p in BOILERPLATE_PATTERNS)
        if has_boilerplate:
            stats["boilerplate_stripped"] += 1
            if fix:
                article["content_markdown"] = strip_boilerplate_tail(article["content_markdown"])
                print(f"  FIX: {article['id']} — stripped boilerplate tail", file=sys.stderr)
            else:
                print(f"  ISSUE: {article['id']} — boilerplate in tail", file=sys.stderr)

        fixed.append(article)

    return fixed, stats


def validate_concepts(concepts: list[dict], article_ids: set[str]) -> dict:
    """Validate concepts, return stats."""
    stats = {"total": len(concepts), "missing_text": 0, "bad_refs": 0}
    for c in concepts:
        if not c.get("text", "").strip() or not c.get("topic", "").strip():
            stats["missing_text"] += 1
            print(f"  ISSUE: concept {c['id']} — missing text or topic", file=sys.stderr)
        missing = [aid for aid in c.get("source_article_ids", []) if aid not in article_ids]
        if missing:
            stats["bad_refs"] += 1
            print(f"  ISSUE: concept {c['id']} — refs missing articles: {missing}", file=sys.stderr)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Validate and fix articles.json")
    parser.add_argument("--fix", action="store_true", help="Fix issues and save")
    args = parser.parse_args()

    if not ARTICLES_PATH.exists():
        print(f"ERROR: {ARTICLES_PATH} not found", file=sys.stderr)
        sys.exit(1)

    articles = json.loads(ARTICLES_PATH.read_text())
    print(f"\n=== Validating {len(articles)} articles ===", file=sys.stderr)

    articles, a_stats = validate_articles(articles, fix=args.fix)

    article_ids = {a["id"] for a in articles}

    concepts = []
    if CONCEPTS_PATH.exists():
        concepts = json.loads(CONCEPTS_PATH.read_text())
        print(f"\n=== Validating {len(concepts)} concepts ===", file=sys.stderr)
        c_stats = validate_concepts(concepts, article_ids)
    else:
        c_stats = {}

    print(f"\n=== Summary ===", file=sys.stderr)
    print(f"  Articles: {a_stats['total']}", file=sys.stderr)
    print(f"  Bad headings: {a_stats['bad_headings_removed']}", file=sys.stderr)
    print(f"  Short sections: {a_stats['short_sections_removed']}", file=sys.stderr)
    print(f"  Boilerplate: {a_stats['boilerplate_stripped']}", file=sys.stderr)
    print(f"  Articles removed: {a_stats['articles_removed']}", file=sys.stderr)
    if c_stats:
        print(f"  Concepts: {c_stats['total']}", file=sys.stderr)
        print(f"  Missing text/topic: {c_stats.get('missing_text', 0)}", file=sys.stderr)
        print(f"  Bad refs: {c_stats.get('bad_refs', 0)}", file=sys.stderr)

    if args.fix:
        # Save fixed data
        ARTICLES_PATH.write_text(json.dumps(articles, indent=2, ensure_ascii=False))
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ARTICLES_PATH, APP_DATA_DIR / "articles.json")
        print(f"\n  Saved to {ARTICLES_PATH}", file=sys.stderr)
        print(f"  Copied to {APP_DATA_DIR / 'articles.json'}", file=sys.stderr)

    # Exit with error if issues found
    total_issues = (
        a_stats["bad_headings_removed"]
        + a_stats["short_sections_removed"]
        + a_stats["boilerplate_stripped"]
        + a_stats["articles_removed"]
        + c_stats.get("missing_text", 0)
        + c_stats.get("bad_refs", 0)
    )

    if total_issues > 0 and not args.fix:
        print(f"\n  {total_issues} issues found. Run with --fix to repair.", file=sys.stderr)
        sys.exit(1)
    elif args.fix:
        print(f"\n  Fixed {total_issues} issues.", file=sys.stderr)


if __name__ == "__main__":
    main()
