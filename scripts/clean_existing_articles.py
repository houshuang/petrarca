#!/usr/bin/env python3
"""Apply markdown cleanup to existing articles.json without re-running LLM pipeline.

Fixes: run-together Wikipedia links, [edit] artifacts, citation markers,
bibliography-only sections, and articles that are purely reference material.

Usage:
    python3 scripts/clean_existing_articles.py              # apply cleanup
    python3 scripts/clean_existing_articles.py --dry-run    # just report issues
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_articles import clean_markdown, _is_bibliography_section

SCRIPT_DIR = Path(__file__).parent
APP_DATA_DIR = SCRIPT_DIR.parent / "app" / "data"
ARTICLES_PATH = APP_DATA_DIR / "articles.json"


def is_bibliography_article(article: dict) -> bool:
    """Check if an entire article is just bibliography/reference content."""
    title = article.get("title", "").lower()
    bib_keywords = [
        "bibliography", "references", "further reading", "external links",
        "bibliografia", "riferimenti", "collegamenti esterni", "voci correlate",
        "note e riferimenti",
    ]
    for kw in bib_keywords:
        if kw in title:
            return True
    return False


def count_issues(text: str) -> dict:
    """Count various quality issues in markdown text."""
    return {
        "run_together_links": len(re.findall(r'\)\[', text)),
        "edit_links": len(re.findall(r'\[edit\]', text, re.IGNORECASE)),
        "citation_markers": len(re.findall(r'\[\d{1,3}\]', text)),
        "empty_links": len(re.findall(r'\[\s*\]\([^)]+\)', text)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    articles = json.loads(ARTICLES_PATH.read_text())
    print(f"Loaded {len(articles)} articles")

    stats = {
        "cleaned_markdown": 0,
        "removed_bib_articles": 0,
        "cleaned_sections": 0,
        "removed_bib_sections": 0,
    }

    # Track articles to remove
    to_remove = set()

    for i, article in enumerate(articles):
        aid = article.get("id", "?")
        title = article.get("title", "Untitled")

        # Check if entire article is bibliography
        if is_bibliography_article(article):
            stats["removed_bib_articles"] += 1
            to_remove.add(i)
            print(f"  REMOVE bib article: {title[:60]}")
            continue

        # Clean content_markdown
        content = article.get("content_markdown", "")
        issues = count_issues(content)
        total_issues = sum(issues.values())

        if total_issues > 0:
            stats["cleaned_markdown"] += 1
            if not args.dry_run:
                article["content_markdown"] = clean_markdown(content)
            print(f"  CLEAN ({total_issues} issues): {title[:60]}")

        # Clean sections
        sections = article.get("sections", [])
        cleaned_sections = []
        for sec in sections:
            heading = sec.get("heading", "")
            sec_content = sec.get("content", "")

            if _is_bibliography_section(heading, sec_content):
                stats["removed_bib_sections"] += 1
                print(f"    REMOVE bib section: {heading[:40]}")
                continue

            sec_issues = count_issues(sec_content)
            if sum(sec_issues.values()) > 0:
                stats["cleaned_sections"] += 1
                if not args.dry_run:
                    sec["content"] = clean_markdown(sec_content)

            cleaned_sections.append(sec)

        if not args.dry_run:
            article["sections"] = cleaned_sections

    # Remove bibliography articles
    if to_remove and not args.dry_run:
        articles = [a for i, a in enumerate(articles) if i not in to_remove]

    print(f"\nSummary:")
    print(f"  Articles with cleaned markdown: {stats['cleaned_markdown']}")
    print(f"  Bibliography articles removed: {stats['removed_bib_articles']}")
    print(f"  Sections cleaned: {stats['cleaned_sections']}")
    print(f"  Bibliography sections removed: {stats['removed_bib_sections']}")

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
    else:
        ARTICLES_PATH.write_text(json.dumps(articles, indent=2, ensure_ascii=False))
        print(f"\nWrote {len(articles)} articles to {ARTICLES_PATH}")


if __name__ == "__main__":
    main()
