#!/usr/bin/env python3
"""Cleanup and validation for Petrarca article pipeline.

Detects and removes:
  1. Junk articles — X.com JavaScript errors, very short content, blog index pages
  2. Duplicates — exact content hash, URL duplicates, high claim overlap

Usage:
    python3 scripts/cleanup_articles.py                    # report only (default)
    python3 scripts/cleanup_articles.py --report           # same as default
    python3 scripts/cleanup_articles.py --remove-junk      # remove junk articles
    python3 scripts/cleanup_articles.py --merge-duplicates # keep better version of dupes
    python3 scripts/cleanup_articles.py --fix              # do both
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
KNOWLEDGE_INDEX_PATH = DATA_DIR / "knowledge_index.json"

# ---------------------------------------------------------------------------
# Junk detection
# ---------------------------------------------------------------------------

# Patterns that indicate a JavaScript error page (X.com, etc.)
JS_ERROR_PATTERNS = [
    re.compile(r"JavaScript is disabled", re.IGNORECASE),
    re.compile(r"Please enable JavaScript", re.IGNORECASE),
    re.compile(r"browser.*does not support JavaScript", re.IGNORECASE),
    re.compile(r"enable JavaScript.*to run this app", re.IGNORECASE),
    re.compile(r"requires JavaScript.*enabled", re.IGNORECASE),
]

# Patterns for generic error/access pages
ERROR_PAGE_PATTERNS = [
    re.compile(r"Access Denied", re.IGNORECASE),
    re.compile(r"403 Forbidden", re.IGNORECASE),
    re.compile(r"404 Not Found", re.IGNORECASE),
    re.compile(r"Page Not Found", re.IGNORECASE),
    re.compile(r"This page isn.t available", re.IGNORECASE),
    re.compile(r"Something went wrong", re.IGNORECASE),
]

MIN_WORD_COUNT = 80


def _word_count(text: str) -> int:
    """Count words after stripping markdown formatting."""
    # Strip markdown links, images, code blocks
    stripped = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    stripped = re.sub(r'!?\[([^\]]*)\]\([^)]+\)', r'\1', stripped)
    stripped = re.sub(r'#{1,6}\s+', '', stripped)
    stripped = re.sub(r'[*_~`]', '', stripped)
    return len(stripped.split())


def _link_count(text: str) -> int:
    """Count markdown links and bare URLs."""
    md_links = len(re.findall(r'\[.*?\]\(.*?\)', text))
    bare_urls = len(re.findall(r'https?://[^\s)\]]+', text))
    return md_links + bare_urls


def detect_js_error(article: dict) -> str | None:
    """Returns reason string if article is a JavaScript error page."""
    content = article.get("content_markdown", "")
    for pat in JS_ERROR_PATTERNS:
        if pat.search(content[:500]):
            return f"JavaScript error page: {pat.pattern}"
    return None


def detect_error_page(article: dict) -> str | None:
    """Returns reason string if article is a generic error page."""
    content = article.get("content_markdown", "")
    wc = _word_count(content)
    if wc > 200:
        return None
    for pat in ERROR_PAGE_PATTERNS:
        if pat.search(content[:500]):
            return f"Error page ({wc}w): {pat.pattern}"
    return None


def detect_too_short(article: dict) -> str | None:
    """Returns reason if article has too little actual content."""
    content = article.get("content_markdown", "")
    wc = _word_count(content)
    if wc < MIN_WORD_COUNT:
        return f"Too short: {wc} words (minimum {MIN_WORD_COUNT})"
    return None


def detect_blog_index(article: dict) -> str | None:
    """Returns reason if article is a blog index/listing page."""
    content = article.get("content_markdown", "")
    wc = _word_count(content)
    links = _link_count(content)

    if wc == 0:
        return None

    ratio = links / wc
    # Very high link density with many links = index page
    if ratio > 0.15 and links > 20:
        return f"Blog index page: {links} links in {wc} words (ratio {ratio:.2f})"

    return None


def detect_junk(article: dict) -> str | None:
    """Returns reason string if article is junk, None if OK."""
    return (
        detect_js_error(article)
        or detect_error_page(article)
        or detect_too_short(article)
    )


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Normalize URL: strip tracking params, trailing slashes, lowercase."""
    if not url:
        return ""
    parsed = urlparse(url)
    # Strip tracking params
    params = parse_qs(parsed.query, keep_blank_values=False)
    tracking_prefixes = ('utm_', 'ref', 'source', 'fbclid', 'gclid', 's')
    clean_params = {k: v for k, v in params.items()
                    if not any(k.startswith(p) or k == p for p in tracking_prefixes)}
    clean_query = urlencode(clean_params, doseq=True) if clean_params else ""
    normalized = parsed._replace(
        query=clean_query,
        fragment="",
    ).geturl()
    return normalized.rstrip("/").lower()


def _content_hash(text: str) -> str:
    """Hash normalized content for dedup."""
    normalized = " ".join(text.split())
    return hashlib.md5(normalized.encode()).hexdigest()


def _article_quality_score(article: dict) -> float:
    """Score article quality for choosing which duplicate to keep."""
    score = 0.0
    score += _word_count(article.get("content_markdown", "")) * 0.1
    score += len(article.get("key_claims", [])) * 10
    score += len(article.get("atomic_claims", [])) * 2
    score += len(article.get("sections", [])) * 5
    if article.get("full_summary"):
        score += 20
    if article.get("interest_topics"):
        score += 10
    if article.get("entities"):
        score += 5
    return score


def find_content_hash_duplicates(articles: list[dict]) -> list[tuple[str, list[dict]]]:
    """Find articles with identical content (after whitespace normalization)."""
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        content = a.get("content_markdown", "")
        if not content:
            continue
        h = _content_hash(content)
        by_hash[h].append(a)

    return [(h, group) for h, group in by_hash.items() if len(group) > 1]


def find_url_duplicates(articles: list[dict]) -> list[tuple[str, list[dict]]]:
    """Find articles with the same normalized URL AND similar content.

    Many Wikipedia articles are intentionally split into multiple section extracts
    from the same URL, so we only flag URL duplicates when the content is also
    very similar (same content hash).
    """
    by_url: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        url = a.get("source_url", "")
        if not url:
            continue
        norm = _normalize_url(url)
        if norm:
            by_url[norm].append(a)

    results = []
    for url, group in by_url.items():
        if len(group) <= 1:
            continue
        # Only flag as URL dupes if they also share content hashes
        # (i.e., genuinely the same article ingested twice, not different sections)
        hash_groups: dict[str, list[dict]] = defaultdict(list)
        for a in group:
            h = _content_hash(a.get("content_markdown", ""))
            hash_groups[h].append(a)
        for h, hgroup in hash_groups.items():
            if len(hgroup) > 1:
                results.append((url, hgroup))

    return results


def find_claim_overlap_duplicates(
    articles: list[dict],
    knowledge_index: dict | None,
    threshold: float = 0.90,
) -> list[tuple[str, dict, dict]]:
    """Find article pairs where >threshold of one article's claims are KNOWN from the other.

    Uses the article_novelty_matrix from knowledge_index.json.
    Only flags pairs from DIFFERENT source URLs (same-URL section splits are intentional).
    Returns list of (reason, worse_article, better_article).
    """
    if not knowledge_index:
        return []

    anm = knowledge_index.get("article_novelty_matrix", {})
    if not anm:
        return []

    article_by_id = {a["id"]: a for a in articles}
    duplicates = []
    seen_pairs = set()

    for aid_a, comparisons in anm.items():
        if aid_a not in article_by_id:
            continue
        for aid_b, counts in comparisons.items():
            if aid_b not in article_by_id:
                continue
            if aid_a == aid_b:
                continue

            pair_key = tuple(sorted([aid_a, aid_b]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            art_a = article_by_id[aid_a]
            art_b = article_by_id[aid_b]

            # Skip pairs from the same source URL (intentional section splits)
            url_a = _normalize_url(art_a.get("source_url", ""))
            url_b = _normalize_url(art_b.get("source_url", ""))
            if url_a and url_b and url_a == url_b:
                continue

            new_a = counts.get("new", 0)
            extends_a = counts.get("extends", 0)
            known_a = counts.get("known", 0)
            total_a = new_a + extends_a + known_a

            if total_a == 0:
                continue

            known_ratio = known_a / total_a
            if known_ratio >= threshold:
                score_a = _article_quality_score(art_a)
                score_b = _article_quality_score(art_b)

                if score_a >= score_b:
                    better, worse = art_a, art_b
                else:
                    better, worse = art_b, art_a

                reason = (
                    f"Claim overlap: {known_a}/{total_a} claims "
                    f"({known_ratio:.0%}) of '{art_a.get('title', '')[:40]}' "
                    f"known from '{art_b.get('title', '')[:40]}'"
                )
                duplicates.append((reason, worse, better))

    return duplicates


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(articles: list[dict], knowledge_index: dict | None) -> dict:
    """Generate a full cleanup report."""
    report = {
        "total_articles": len(articles),
        "junk": [],
        "content_hash_dupes": [],
        "url_dupes": [],
        "claim_overlap_dupes": [],
        "blog_indexes": [],
    }

    # Junk detection
    for a in articles:
        reason = detect_junk(a)
        if reason:
            report["junk"].append({
                "id": a["id"],
                "title": a.get("title", "")[:80],
                "reason": reason,
                "url": a.get("source_url", "")[:80],
            })

    # Blog index detection (separate from junk — these are real content, just not articles)
    for a in articles:
        reason = detect_blog_index(a)
        if reason:
            report["blog_indexes"].append({
                "id": a["id"],
                "title": a.get("title", "")[:80],
                "reason": reason,
            })

    # Content hash duplicates
    for h, group in find_content_hash_duplicates(articles):
        scored = sorted(group, key=_article_quality_score, reverse=True)
        report["content_hash_dupes"].append({
            "hash": h[:12],
            "keep": {"id": scored[0]["id"], "title": scored[0].get("title", "")[:60],
                      "score": _article_quality_score(scored[0])},
            "remove": [{"id": a["id"], "title": a.get("title", "")[:60],
                         "score": _article_quality_score(a)} for a in scored[1:]],
        })

    # URL duplicates
    for url, group in find_url_duplicates(articles):
        scored = sorted(group, key=_article_quality_score, reverse=True)
        report["url_dupes"].append({
            "url": url[:80],
            "keep": {"id": scored[0]["id"], "title": scored[0].get("title", "")[:60]},
            "remove": [{"id": a["id"], "title": a.get("title", "")[:60]} for a in scored[1:]],
        })

    # Claim overlap duplicates
    for reason, worse, better in find_claim_overlap_duplicates(articles, knowledge_index):
        report["claim_overlap_dupes"].append({
            "reason": reason,
            "keep": {"id": better["id"], "title": better.get("title", "")[:60]},
            "remove": {"id": worse["id"], "title": worse.get("title", "")[:60]},
        })

    return report


def print_report(report: dict):
    """Pretty-print the cleanup report."""
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  PETRARCA ARTICLE CLEANUP REPORT", file=sys.stderr)
    print(f"  Total articles: {report['total_articles']}", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    # Junk
    junk = report["junk"]
    print(f"\n--- JUNK ARTICLES ({len(junk)}) ---", file=sys.stderr)
    for j in junk:
        print(f"  {j['id']}  {j['title']}", file=sys.stderr)
        print(f"    Reason: {j['reason']}", file=sys.stderr)

    # Blog indexes
    indexes = report["blog_indexes"]
    print(f"\n--- BLOG INDEX PAGES ({len(indexes)}) ---", file=sys.stderr)
    for idx in indexes[:10]:
        print(f"  {idx['id']}  {idx['title']}", file=sys.stderr)
        print(f"    Reason: {idx['reason']}", file=sys.stderr)
    if len(indexes) > 10:
        print(f"  ... and {len(indexes) - 10} more", file=sys.stderr)

    # Content hash dupes
    ch_dupes = report["content_hash_dupes"]
    print(f"\n--- CONTENT HASH DUPLICATES ({len(ch_dupes)} groups) ---", file=sys.stderr)
    for d in ch_dupes:
        removable = sum(len(d["remove"]) for _ in [1])
        # Skip groups that are entirely junk (already counted above)
        junk_ids = {j["id"] for j in report["junk"]}
        non_junk_remove = [r for r in d["remove"] if r["id"] not in junk_ids]
        if not non_junk_remove and d["keep"]["id"] in junk_ids:
            continue
        print(f"  KEEP: {d['keep']['id']}  {d['keep']['title']} (score={d['keep']['score']:.0f})", file=sys.stderr)
        for r in d["remove"]:
            label = " [JUNK]" if r["id"] in junk_ids else ""
            print(f"  DROP: {r['id']}  {r['title']} (score={r['score']:.0f}){label}", file=sys.stderr)
        print(file=sys.stderr)

    # URL dupes
    url_dupes = report["url_dupes"]
    print(f"\n--- URL DUPLICATES ({len(url_dupes)} groups) ---", file=sys.stderr)
    for d in url_dupes:
        print(f"  URL: {d['url']}", file=sys.stderr)
        print(f"  KEEP: {d['keep']['id']}  {d['keep']['title']}", file=sys.stderr)
        for r in d["remove"]:
            print(f"  DROP: {r['id']}  {r['title']}", file=sys.stderr)
        print(file=sys.stderr)

    # Claim overlap dupes
    co_dupes = report["claim_overlap_dupes"]
    print(f"\n--- CLAIM OVERLAP DUPLICATES ({len(co_dupes)} pairs) ---", file=sys.stderr)
    for d in co_dupes:
        print(f"  {d['reason']}", file=sys.stderr)
        print(f"  KEEP: {d['keep']['id']}  {d['keep']['title']}", file=sys.stderr)
        print(f"  DROP: {d['remove']['id']}  {d['remove']['title']}", file=sys.stderr)
        print(file=sys.stderr)

    # Summary
    total_junk = len(junk)
    total_hash_remove = sum(len(d["remove"]) for d in ch_dupes)
    total_url_remove = sum(len(d["remove"]) for d in url_dupes)
    total_claim_remove = len(co_dupes)

    # Deduplicate removal IDs (an article may appear in multiple categories)
    remove_ids = set()
    for j in junk:
        remove_ids.add(j["id"])
    for d in ch_dupes:
        for r in d["remove"]:
            remove_ids.add(r["id"])
    for d in url_dupes:
        for r in d["remove"]:
            remove_ids.add(r["id"])
    for d in co_dupes:
        remove_ids.add(d["remove"]["id"])

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"  SUMMARY", file=sys.stderr)
    print(f"  Junk articles: {total_junk}", file=sys.stderr)
    print(f"  Content hash duplicates (removable): {total_hash_remove}", file=sys.stderr)
    print(f"  URL duplicates (removable): {total_url_remove}", file=sys.stderr)
    print(f"  Claim overlap duplicates: {total_claim_remove}", file=sys.stderr)
    print(f"  Blog index pages (info only): {len(indexes)}", file=sys.stderr)
    print(f"  ---", file=sys.stderr)
    print(f"  Unique articles to remove: {len(remove_ids)}", file=sys.stderr)
    print(f"  Articles remaining: {report['total_articles'] - len(remove_ids)}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Cleanup actions
# ---------------------------------------------------------------------------

def remove_junk(articles: list[dict]) -> tuple[list[dict], int]:
    """Remove junk articles. Returns (cleaned_articles, removed_count)."""
    removed = 0
    cleaned = []
    for a in articles:
        reason = detect_junk(a)
        if reason:
            print(f"  REMOVE: {a['id']}  {a.get('title', '')[:60]}", file=sys.stderr)
            print(f"    Reason: {reason}", file=sys.stderr)
            removed += 1
        else:
            cleaned.append(a)
    return cleaned, removed


def merge_duplicates(articles: list[dict], knowledge_index: dict | None) -> tuple[list[dict], int]:
    """Remove duplicate articles, keeping the better version. Returns (cleaned_articles, removed_count)."""
    remove_ids: set[str] = set()

    # Content hash duplicates
    for h, group in find_content_hash_duplicates(articles):
        scored = sorted(group, key=_article_quality_score, reverse=True)
        for a in scored[1:]:
            remove_ids.add(a["id"])
            print(f"  MERGE (content hash): drop {a['id']} '{a.get('title', '')[:50]}', "
                  f"keep {scored[0]['id']}", file=sys.stderr)

    # URL duplicates (only if not already removed by content hash)
    for url, group in find_url_duplicates(articles):
        remaining = [a for a in group if a["id"] not in remove_ids]
        if len(remaining) <= 1:
            continue
        scored = sorted(remaining, key=_article_quality_score, reverse=True)
        for a in scored[1:]:
            remove_ids.add(a["id"])
            print(f"  MERGE (URL dupe): drop {a['id']} '{a.get('title', '')[:50]}', "
                  f"keep {scored[0]['id']}", file=sys.stderr)

    # Claim overlap duplicates
    for reason, worse, better in find_claim_overlap_duplicates(articles, knowledge_index):
        if worse["id"] not in remove_ids:
            remove_ids.add(worse["id"])
            print(f"  MERGE (claim overlap): drop {worse['id']} '{worse.get('title', '')[:50]}', "
                  f"keep {better['id']}", file=sys.stderr)

    cleaned = [a for a in articles if a["id"] not in remove_ids]
    return cleaned, len(remove_ids)


def save_articles(articles: list[dict], backup: bool = True):
    """Save articles.json with backup."""
    if backup and ARTICLES_PATH.exists():
        backup_path = ARTICLES_PATH.with_suffix(".json.bak")
        shutil.copy2(ARTICLES_PATH, backup_path)
        print(f"  Backup saved to {backup_path}", file=sys.stderr)

    ARTICLES_PATH.write_text(json.dumps(articles, indent=2, ensure_ascii=False))
    print(f"  Saved {len(articles)} articles to {ARTICLES_PATH}", file=sys.stderr)

    # Copy to app data
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ARTICLES_PATH, APP_DATA_DIR / "articles.json")
    print(f"  Copied to {APP_DATA_DIR / 'articles.json'}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cleanup and validation for Petrarca article pipeline"
    )
    parser.add_argument("--report", action="store_true", default=True,
                        help="Print cleanup report (default)")
    parser.add_argument("--remove-junk", action="store_true",
                        help="Remove junk articles")
    parser.add_argument("--merge-duplicates", action="store_true",
                        help="Merge duplicate articles (keep better version)")
    parser.add_argument("--fix", action="store_true",
                        help="Remove junk and merge duplicates")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip backup before saving")
    args = parser.parse_args()

    if not ARTICLES_PATH.exists():
        print(f"ERROR: {ARTICLES_PATH} not found", file=sys.stderr)
        sys.exit(1)

    articles = json.loads(ARTICLES_PATH.read_text())
    print(f"Loaded {len(articles)} articles from {ARTICLES_PATH}", file=sys.stderr)

    # Load knowledge index if available
    knowledge_index = None
    if KNOWLEDGE_INDEX_PATH.exists():
        knowledge_index = json.loads(KNOWLEDGE_INDEX_PATH.read_text())
        print(f"Loaded knowledge index from {KNOWLEDGE_INDEX_PATH}", file=sys.stderr)

    is_action = args.remove_junk or args.merge_duplicates or args.fix
    report = generate_report(articles, knowledge_index)
    print_report(report)

    if not is_action:
        # Collect all removal IDs for exit code
        remove_ids = set()
        for j in report["junk"]:
            remove_ids.add(j["id"])
        for d in report["content_hash_dupes"]:
            for r in d["remove"]:
                remove_ids.add(r["id"])
        for d in report["url_dupes"]:
            for r in d["remove"]:
                remove_ids.add(r["id"])
        for d in report["claim_overlap_dupes"]:
            remove_ids.add(d["remove"]["id"])
        if remove_ids:
            print(f"Run with --fix to clean up {len(remove_ids)} articles.", file=sys.stderr)
            sys.exit(1)
        return

    total_removed = 0

    if args.remove_junk or args.fix:
        articles, removed = remove_junk(articles)
        total_removed += removed
        print(f"  Removed {removed} junk articles", file=sys.stderr)

    if args.merge_duplicates or args.fix:
        articles, removed = merge_duplicates(articles, knowledge_index)
        total_removed += removed
        print(f"  Removed {removed} duplicate articles", file=sys.stderr)

    if total_removed > 0:
        save_articles(articles, backup=not args.no_backup)
        print(f"\n  Total removed: {total_removed}", file=sys.stderr)
        print(f"  Articles remaining: {len(articles)}", file=sys.stderr)
    else:
        print(f"\n  No articles to remove.", file=sys.stderr)


if __name__ == "__main__":
    main()
