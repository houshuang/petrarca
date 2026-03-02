#!/usr/bin/env python3
"""Build articles.json from Twitter bookmarks.

Pipeline:
  1. Load bookmarks from otak cache
  2. Filter for relevance
  3. Collect all article URLs (from tweet URLs + quoted tweet URLs)
  4. Fetch article content with 3-tier extraction
  5. Deduplicate
  6. LLM processing: generate sections, summaries, claims per article
  7. Output articles.json

Usage:
    python3 scripts/build_articles.py
    python3 scripts/build_articles.py --from articles   # skip to LLM step
    python3 scripts/build_articles.py --dry-run          # skip LLM calls
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests as _requests
import trafilatura
from lxml import html as lxml_html

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
OTAK_BOOKMARKS = Path.home() / "src" / "otak" / "data" / "twitter_bookmarks.json"

FILTERED_PATH = DATA_DIR / "bookmarks_filtered.json"
FETCHED_PATH = DATA_DIR / "articles_fetched.json"
ARTICLES_PATH = DATA_DIR / "articles.json"

# ---------------------------------------------------------------------------
# Step 1: Filter (reused from existing pipeline)
# ---------------------------------------------------------------------------

STRONG_PATTERNS = [
    r"\bclaude\s+code\b", r"\bclaude\s+cli\b", r"\bclaude\s+-p\b",
    r"\bclaude\.ai\b", r"\b@claudeai\b", r"\banthrop(?:ic|ics)\b",
    r"\bclaude\s+(?:sonnet|haiku|opus)\b", r"\bclaude\s+agent\b",
    r"\bclaude\s+desktop\b", r"\bclaude\s+(?:3|4)\b",
    r"\bmodel\s*context\s*protocol\b", r"\bmcp\s+server\b", r"\bmcp\s+tool\b",
    r"\bclaude(?:code|_code)\b", r"\bCLAUDE\.md\b", r"\bAGENTS\.md\b",
]

MEDIUM_PATTERNS = [
    r"\bclaude\b", r"\bmcp\b", r"\bagentic\s+cod(?:ing|er|e)\b",
    r"\bai\s+cod(?:ing|er|e)\b", r"\bcoding\s+agent\b", r"\bcode\s+agent\b",
    r"\bvibe\s*cod(?:ing|er|e)\b", r"\bllm\s+(?:cod(?:ing|er|e)|agent)\b",
]

CODING_CONTEXT = [
    r"\bgithub\b", r"\bprompt\b", r"\bterminal\b", r"\beditor\b", r"\bvscode\b",
    r"\bcursor\b", r"\bcopilot\b", r"\bwindsurf\b", r"\bcodebase\b", r"\brefactor\b",
    r"\bdebug\b", r"\bpull\s+request\b", r"\bcommit\b", r"\bbranch\b", r"\brepo\b",
    r"\bdev\s+tool\b", r"\btool\s+use\b", r"\btool\s+calling\b",
    r"\bprogramm(?:ing|er)\b", r"\bdevelop(?:er|ment)\b",
    r"\bapi\b", r"\bsdk\b", r"\bopen\s*source\b",
]

NEGATIVE_PATTERNS = [
    r"\bclaude\s+(?:monet|debussy|shannon|bernard|rains|giroux|levi.?strauss)\b",
    r"\bvan\s+damme\b",
]

KNOWN_AUTHORS = {
    "trq212", "alexalbert__", "birch_labs", "aaborovkov",
    "simonw", "swyx", "karpathy", "nateberkopec", "arvidkahl",
}


def _get_full_text(bookmark: dict) -> str:
    parts = [bookmark.get("text", "")]
    qt = bookmark.get("quoted_tweet")
    if qt and isinstance(qt, dict):
        parts.append(qt.get("text", ""))
    for u in bookmark.get("urls", []):
        if isinstance(u, dict):
            parts.append(u.get("display_url", ""))
            parts.append(u.get("expanded_url", ""))
        elif isinstance(u, str):
            parts.append(u)
    return " ".join(parts)


def _score_relevance(bookmark: dict) -> tuple[float, list[str]]:
    text = _get_full_text(bookmark).lower()
    matched = []
    for pat in NEGATIVE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return 0.0, ["negative_match"]
    score = 0.0
    for pat in STRONG_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            score += 1.0
            matched.append(f"strong:{pat}")
    for pat in MEDIUM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            score += 0.4
            matched.append(f"medium:{pat}")
    for pat in CODING_CONTEXT:
        if re.search(pat, text, re.IGNORECASE):
            score += 0.15
            matched.append(f"context:{pat}")
    if bookmark.get("author_username", "").lower() in KNOWN_AUTHORS:
        score += 0.3
        matched.append("known_author")
    return score, matched


def filter_bookmarks(bookmarks: list[dict], days: int = 60, min_score: float = 0.8) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []
    for bm in bookmarks:
        try:
            dt = datetime.strptime(bm["created_at"], "%a %b %d %H:%M:%S %z %Y")
        except (KeyError, ValueError):
            continue
        if dt < cutoff:
            continue
        score, matched = _score_relevance(bm)
        if score < min_score:
            continue
        bm_copy = dict(bm)
        bm_copy["_relevance_score"] = round(score, 2)
        bm_copy["_matched_patterns"] = matched
        bm_copy["_parsed_date"] = dt.isoformat()
        results.append(bm_copy)

    results.sort(key=lambda x: (-x["_relevance_score"], x["_parsed_date"]))
    print(f"  Filtered: {len(results)} relevant bookmarks", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 2: Extract article URLs and content
# ---------------------------------------------------------------------------

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nb;q=0.8,no;q=0.7",
}

SKIP_DOMAINS = {
    "twitter.com", "x.com", "t.co",
    "youtube.com", "youtu.be",
    "instagram.com", "tiktok.com",
    "imgur.com", "giphy.com",
    "open.spotify.com",
}

SKIP_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mp3", ".pdf", ".zip"}


def _is_article_url(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    if any(d in domain for d in SKIP_DOMAINS):
        return False
    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    return True


def _resolve_tco(url: str) -> str | None:
    """Resolve t.co shortlinks to final URL."""
    try:
        resp = _requests.head(url, headers=_BROWSER_HEADERS, timeout=10, allow_redirects=True)
        return resp.url
    except Exception:
        try:
            resp = _requests.get(url, headers=_BROWSER_HEADERS, timeout=10, allow_redirects=True, stream=True)
            final = resp.url
            resp.close()
            return final
        except Exception:
            return None


def _fetch_html_requests(url: str) -> str:
    resp = _requests.get(url, headers=_BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _extract_text_lxml(html_str: str) -> str:
    doc = lxml_html.fromstring(html_str)
    for el in doc.iter("script", "style", "noscript"):
        el.drop_tree()
    text = doc.text_content()
    lines = [line.strip() for line in text.splitlines()]
    paragraphs = []
    current = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(p for p in paragraphs if len(p) > 20)


def fetch_article(url: str) -> dict | None:
    """3-tier article extraction. Returns dict with title, text (markdown), author, etc."""
    downloaded = None
    text = None
    meta = None
    fetch_method = None

    # Tier 1: trafilatura native
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception:
        pass
    if downloaded:
        text = trafilatura.extract(downloaded, output_format="markdown", include_links=True)
        meta = trafilatura.extract_metadata(downloaded)
        if text:
            fetch_method = "trafilatura"

    # Tier 2: requests + trafilatura with favor_recall
    if not text:
        try:
            html_str = _fetch_html_requests(url)
            text = trafilatura.extract(html_str, output_format="markdown",
                                       include_links=True, favor_recall=True)
            meta = trafilatura.extract_metadata(html_str)
            if text:
                fetch_method = "requests+trafilatura"
                downloaded = html_str
        except Exception:
            pass

    # Tier 3: requests + lxml
    if not text:
        try:
            html_str = downloaded or _fetch_html_requests(url)
            text = _extract_text_lxml(html_str)
            if text:
                fetch_method = "requests+lxml"
        except Exception:
            pass

    if not text or len(text.split()) < 50:
        return None

    return {
        "title": (meta.title if meta else "") or "",
        "author": (meta.author if meta else "") or "",
        "date": (meta.date if meta else "") or "",
        "text": text,
        "word_count": len(text.split()),
        "source_url": url,
        "hostname": (meta.sitename if meta else "") or urlparse(url).netloc,
        "fetch_method": fetch_method,
    }


def _collect_urls(bookmark: dict) -> list[str]:
    """Collect all article URLs from a bookmark, including quoted tweets."""
    urls = []

    # Direct URLs
    for u in bookmark.get("urls", []):
        if isinstance(u, dict):
            expanded = u.get("expanded_url", "")
        else:
            expanded = u
        if expanded:
            if "t.co/" in expanded or "bit.ly/" in expanded:
                resolved = _resolve_tco(expanded)
                if resolved:
                    expanded = resolved
            if _is_article_url(expanded):
                urls.append(expanded)

    # Quoted tweet URLs (t.co links in quoted text)
    qt = bookmark.get("quoted_tweet")
    if qt and isinstance(qt, dict):
        qt_text = qt.get("text", "")
        tco_links = re.findall(r'https?://t\.co/\w+', qt_text)
        for tco in tco_links:
            resolved = _resolve_tco(tco)
            if resolved and _is_article_url(resolved):
                urls.append(resolved)

    return list(dict.fromkeys(urls))  # dedupe preserving order


def fetch_all_articles(bookmarks: list[dict]) -> list[dict]:
    """For each bookmark, collect URLs and fetch article content."""
    results = []
    for i, bm in enumerate(bookmarks):
        bm_copy = dict(bm)
        bm_copy["_fetched_articles"] = []

        urls = _collect_urls(bm)
        for url in urls:
            print(f"  [{i+1}/{len(bookmarks)}] Fetching: {url[:80]}...", file=sys.stderr)
            article = fetch_article(url)
            if article:
                bm_copy["_fetched_articles"].append(article)
                print(f"    OK: {article['word_count']} words via {article['fetch_method']}: {article['title'][:60]}", file=sys.stderr)
            else:
                print(f"    FAIL: no content extracted", file=sys.stderr)
            time.sleep(0.5)

        # Long-form tweets (>100 words) become articles themselves
        tweet_words = len(bm["text"].split())
        if not bm_copy["_fetched_articles"] and tweet_words > 100:
            print(f"  [{i+1}/{len(bookmarks)}] Long tweet ({tweet_words} words) → article: @{bm['author_username']}", file=sys.stderr)
            bm_copy["_fetched_articles"].append({
                "title": f"Thread by @{bm['author_username']}",
                "author": bm.get("author_name", bm["author_username"]),
                "date": bm.get("_parsed_date", ""),
                "text": bm["text"],
                "word_count": tweet_words,
                "source_url": bm.get("url", ""),
                "hostname": "twitter.com",
                "fetch_method": "tweet_text",
            })

        results.append(bm_copy)

    fetched = sum(1 for r in results if r["_fetched_articles"])
    print(f"  Fetched articles for {fetched}/{len(results)} bookmarks", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 3: Deduplicate (reused from existing pipeline)
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _text_similarity(a: str, b: str) -> float:
    words_a = set(_normalize_text(a).split())
    words_b = set(_normalize_text(b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _same_article_url(bm_a: dict, bm_b: dict) -> bool:
    urls_a = set()
    urls_b = set()
    for art in bm_a.get("_fetched_articles", []):
        urls_a.add(art.get("source_url", ""))
    for art in bm_b.get("_fetched_articles", []):
        urls_b.add(art.get("source_url", ""))
    urls_a.discard("")
    urls_b.discard("")
    return bool(urls_a & urls_b) if urls_a and urls_b else False


def deduplicate(bookmarks: list[dict]) -> list[dict]:
    n = len(bookmarks)
    assigned = set()
    groups = []
    for i in range(n):
        if i in assigned:
            continue
        group = [i]
        assigned.add(i)
        for j in range(i + 1, n):
            if j in assigned:
                continue
            if _same_article_url(bookmarks[i], bookmarks[j]):
                group.append(j)
                assigned.add(j)
                continue
            if _text_similarity(_get_full_text(bookmarks[i]), _get_full_text(bookmarks[j])) > 0.5:
                group.append(j)
                assigned.add(j)
        groups.append(group)

    results = []
    for group in groups:
        group.sort(key=lambda idx: -bookmarks[idx].get("_relevance_score", 0))
        primary = dict(bookmarks[group[0]])
        if len(group) > 1:
            primary["_related_tweets"] = [
                {"id": bookmarks[idx]["id"], "author_username": bookmarks[idx]["author_username"],
                 "text": bookmarks[idx]["text"][:280]}
                for idx in group[1:]
            ]
        results.append(primary)

    print(f"  Deduped: {n} → {len(results)} groups", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 4: Build articles with LLM processing
# ---------------------------------------------------------------------------

def _call_claude(prompt: str, timeout: int = 180) -> str | None:
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--max-turns", "1"],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"    claude error: {result.stderr[:200]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"    claude timed out after {timeout}s", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("    claude CLI not found", file=sys.stderr)
        return None


def _article_id(url: str, fallback: str = "") -> str:
    src = url or fallback
    return hashlib.sha256(src.encode()).hexdigest()[:12]


def _build_article_prompt(content: str, title: str) -> str:
    # Truncate very long content
    if len(content) > 12000:
        content = content[:12000] + "\n\n[... truncated ...]"

    return f"""Analyze this article for a progressive reading app. The reader will see this at multiple depth levels:
1. One-line summary (scanning a feed)
2. Full summary + key claims (30-second review)
3. Section-by-section reading (deep read)

Article title: {title}

Article content:
{content}

Return a JSON object:
{{
  "title": "cleaned/improved title",
  "one_line_summary": "single sentence, max 120 chars",
  "full_summary": "3-5 sentence summary covering all key points",
  "sections": [
    {{
      "heading": "section heading",
      "summary": "1-2 sentence summary of this section",
      "key_claims": ["specific factual claims from this section"]
    }}
  ],
  "key_claims": ["the 3-7 most important claims/insights across the whole article"],
  "topics": ["topic tags, e.g. prompt-caching, agents, mcp"],
  "estimated_read_minutes": 5,
  "content_type": "one of: analysis, tutorial, opinion, news, research, reference, announcement, discussion"
}}

If the article has clear sections/headings, use them. If not, divide into 2-5 logical sections.
Return ONLY valid JSON."""


def build_articles(bookmarks: list[dict], dry_run: bool = False) -> list[dict]:
    """Transform bookmark data into article-centric format with LLM processing."""
    articles = []

    for i, bm in enumerate(bookmarks):
        fetched = bm.get("_fetched_articles", [])

        # Skip items with no content at all
        if not fetched:
            tweet_words = len(bm.get("text", "").split())
            if tweet_words < 50:
                print(f"  [{i+1}/{len(bookmarks)}] Skipping short tweet: @{bm['author_username']} ({tweet_words} words)", file=sys.stderr)
                continue

        # Use the best fetched article, or the tweet itself
        if fetched:
            best = max(fetched, key=lambda a: a.get("word_count", 0))
        else:
            # This shouldn't happen given the skip above, but just in case
            continue

        article_id = _article_id(best["source_url"], bm.get("id", ""))

        # Build the source reference
        source = {
            "type": "twitter_bookmark",
            "tweet_id": bm.get("id", ""),
            "author_username": bm.get("author_username", ""),
            "tweet_text": bm.get("text", "")[:500],
            "bookmarked_at": bm.get("_parsed_date", ""),
        }

        # LLM processing
        if dry_run:
            print(f"  [{i+1}/{len(bookmarks)}] Would process: {best['title'][:60]} ({best['word_count']} words)", file=sys.stderr)
            llm = {
                "title": best["title"],
                "one_line_summary": "[dry run]",
                "full_summary": "[dry run]",
                "sections": [],
                "key_claims": [],
                "topics": [],
                "estimated_read_minutes": max(1, best["word_count"] // 200),
                "content_type": "unknown",
            }
        else:
            print(f"  [{i+1}/{len(bookmarks)}] Processing: {best['title'][:60]} ({best['word_count']} words)", file=sys.stderr)
            prompt = _build_article_prompt(best["text"], best["title"])
            response = _call_claude(prompt)

            if response:
                try:
                    cleaned = response
                    if cleaned.startswith("```"):
                        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                        cleaned = re.sub(r"\n?```$", "", cleaned)
                    llm = json.loads(cleaned)
                    print(f"    OK: {llm.get('content_type', '?')}, {len(llm.get('sections', []))} sections", file=sys.stderr)
                except json.JSONDecodeError:
                    print(f"    JSON parse failed, using fallback", file=sys.stderr)
                    llm = {
                        "title": best["title"],
                        "one_line_summary": best["text"][:120],
                        "full_summary": best["text"][:500],
                        "sections": [],
                        "key_claims": [],
                        "topics": [],
                        "estimated_read_minutes": max(1, best["word_count"] // 200),
                        "content_type": "unknown",
                    }
            else:
                llm = {
                    "title": best["title"],
                    "one_line_summary": best["text"][:120],
                    "full_summary": best["text"][:500],
                    "sections": [],
                    "key_claims": [],
                    "topics": [],
                    "estimated_read_minutes": max(1, best["word_count"] // 200),
                    "content_type": "unknown",
                }

            time.sleep(1)

        # Split content into sections for the reader
        section_contents = _split_into_sections(best["text"], llm.get("sections", []))

        article = {
            "id": article_id,
            "title": llm.get("title", best["title"]) or best["title"] or f"Post by @{bm.get('author_username', '?')}",
            "author": best.get("author", "") or bm.get("author_name", ""),
            "source_url": best["source_url"],
            "hostname": best.get("hostname", urlparse(best["source_url"]).netloc),
            "date": best.get("date", "") or bm.get("_parsed_date", "")[:10],
            "content_markdown": best["text"],
            "sections": section_contents,
            "one_line_summary": llm.get("one_line_summary", ""),
            "full_summary": llm.get("full_summary", ""),
            "key_claims": llm.get("key_claims", []),
            "topics": llm.get("topics", []),
            "estimated_read_minutes": llm.get("estimated_read_minutes", max(1, best["word_count"] // 200)),
            "content_type": llm.get("content_type", "unknown"),
            "word_count": best["word_count"],
            "sources": [source],
        }

        articles.append(article)

        # Save incrementally
        _save_json(articles, ARTICLES_PATH)

    return articles


def _split_into_sections(content: str, llm_sections: list[dict]) -> list[dict]:
    """Split article content into sections, using LLM headings if available."""
    # If LLM provided sections with headings, try to match them to content
    if llm_sections and len(llm_sections) > 1:
        # Try to split by markdown headings first
        heading_pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
        headings = list(heading_pattern.finditer(content))

        if headings:
            sections = []
            for j, match in enumerate(headings):
                start = match.end()
                end = headings[j + 1].start() if j + 1 < len(headings) else len(content)
                section_content = content[start:end].strip()
                heading = match.group(2).strip()

                # Find matching LLM section for summary/claims
                llm_match = None
                for ls in llm_sections:
                    if ls.get("heading", "").lower() in heading.lower() or heading.lower() in ls.get("heading", "").lower():
                        llm_match = ls
                        break

                sections.append({
                    "heading": heading,
                    "content": section_content,
                    "summary": (llm_match or {}).get("summary", ""),
                    "key_claims": (llm_match or {}).get("key_claims", []),
                })
            return sections if sections else _fallback_sections(content, llm_sections)

    return _fallback_sections(content, llm_sections)


def _fallback_sections(content: str, llm_sections: list[dict]) -> list[dict]:
    """Split content into roughly equal sections using LLM headings."""
    if not llm_sections:
        # Single section with all content
        return [{
            "heading": "Full Article",
            "content": content,
            "summary": "",
            "key_claims": [],
        }]

    # Split content roughly evenly among LLM sections
    paragraphs = content.split("\n\n")
    per_section = max(1, len(paragraphs) // len(llm_sections))
    sections = []

    for j, ls in enumerate(llm_sections):
        start = j * per_section
        end = (j + 1) * per_section if j < len(llm_sections) - 1 else len(paragraphs)
        section_content = "\n\n".join(paragraphs[start:end])
        sections.append({
            "heading": ls.get("heading", f"Section {j+1}"),
            "content": section_content,
            "summary": ls.get("summary", ""),
            "key_claims": ls.get("key_claims", []),
        })

    return sections


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _load_json(path: Path):
    if path.exists():
        return json.loads(path.read_text())
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STEPS = ["filter", "fetch", "dedup", "articles"]


def main():
    parser = argparse.ArgumentParser(description="Build articles.json from Twitter bookmarks")
    parser.add_argument("--fresh", action="store_true", help="Force fresh bookmark load")
    parser.add_argument("--from", dest="from_step", choices=STEPS,
                        help="Start from this step")
    parser.add_argument("--days", type=int, default=60, help="Days back to look (default: 60)")
    parser.add_argument("--min-score", type=float, default=0.8, help="Min relevance score")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start_idx = STEPS.index(args.from_step) if args.from_step else 0

    # Step 1: Filter
    if start_idx <= 0:
        print("\n=== Step 1: Filter Bookmarks ===", file=sys.stderr)
        if not OTAK_BOOKMARKS.exists():
            print(f"ERROR: No bookmarks at {OTAK_BOOKMARKS}", file=sys.stderr)
            sys.exit(1)
        bookmarks = json.loads(OTAK_BOOKMARKS.read_text())
        print(f"  Loaded {len(bookmarks)} raw bookmarks", file=sys.stderr)
        filtered = filter_bookmarks(bookmarks, days=args.days, min_score=args.min_score)
        _save_json(filtered, FILTERED_PATH)
    else:
        filtered = _load_json(FILTERED_PATH)
        if not filtered:
            print(f"ERROR: No cached data at {FILTERED_PATH}", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Step 1: Loaded {len(filtered)} cached filtered ===", file=sys.stderr)

    # Step 2: Fetch articles
    if start_idx <= 1:
        print(f"\n=== Step 2: Fetch Article Content ===", file=sys.stderr)
        fetched = fetch_all_articles(filtered)
        _save_json(fetched, FETCHED_PATH)
    else:
        fetched = _load_json(FETCHED_PATH)
        if not fetched:
            print(f"ERROR: No cached data at {FETCHED_PATH}", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Step 2: Loaded {len(fetched)} cached fetched ===", file=sys.stderr)

    # Step 3: Deduplicate
    if start_idx <= 2:
        print(f"\n=== Step 3: Deduplicate ===", file=sys.stderr)
        deduped = deduplicate(fetched)
    else:
        deduped = fetched  # If skipping to articles step, assume fetched = deduped

    # Step 4: Build articles with LLM
    print(f"\n=== Step 4: Build Articles ===", file=sys.stderr)
    if args.dry_run:
        print("  (dry run — no LLM calls)", file=sys.stderr)

    articles = build_articles(deduped, dry_run=args.dry_run)

    # Copy to app
    _save_json(articles, ARTICLES_PATH)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _save_json(articles, APP_DATA_DIR / "articles.json")

    print(f"\n=== Done ===", file=sys.stderr)
    print(f"  {len(articles)} articles", file=sys.stderr)
    print(f"  Output: {ARTICLES_PATH}", file=sys.stderr)
    print(f"  App data: {APP_DATA_DIR / 'articles.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
