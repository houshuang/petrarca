#!/usr/bin/env python3
"""Build articles.json from Twitter bookmarks and Readwise Reader.

Pipeline:
  1. Load items from sources (Twitter bookmarks, Readwise Reader)
  2. Filter and select candidates
  3. Fetch article content with 3-tier extraction
  4. Deduplicate by URL
  5. LLM processing: generate sections, summaries, claims per article
  6. Output articles.json

Usage:
    python3 scripts/build_articles.py                          # all sources
    python3 scripts/build_articles.py --source twitter         # Twitter only
    python3 scripts/build_articles.py --source readwise        # Readwise only
    python3 scripts/build_articles.py --source all             # all sources (default)
    python3 scripts/build_articles.py --from articles          # skip to LLM step
    python3 scripts/build_articles.py --dry-run                # skip LLM calls
    python3 scripts/build_articles.py --limit 50               # max articles to process
"""

import argparse
import hashlib
import json
import os
import random
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
OTAK_READWISE = Path.home() / "src" / "otak" / "data" / "readwise_reader.json"

FILTERED_PATH = DATA_DIR / "bookmarks_filtered.json"
FETCHED_PATH = DATA_DIR / "articles_fetched.json"
ARTICLES_PATH = DATA_DIR / "articles.json"
CONCEPTS_PATH = DATA_DIR / "concepts.json"

# ---------------------------------------------------------------------------
# Step 1: Collect candidates from sources
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
    "read.readwise.io",
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


def collect_twitter_candidates(days: int = 365) -> list[dict]:
    """Load all Twitter bookmarks with fetchable URLs (no topic filtering)."""
    if not OTAK_BOOKMARKS.exists():
        print(f"  WARNING: No bookmarks at {OTAK_BOOKMARKS}", file=sys.stderr)
        return []

    bookmarks = json.loads(OTAK_BOOKMARKS.read_text())
    print(f"  Loaded {len(bookmarks)} raw Twitter bookmarks", file=sys.stderr)

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []

    for bm in bookmarks:
        try:
            dt = datetime.strptime(bm["created_at"], "%a %b %d %H:%M:%S %z %Y")
        except (KeyError, ValueError):
            continue
        if dt < cutoff:
            continue

        # Collect article URLs from this bookmark
        urls = _collect_urls_from_bookmark(bm)
        tweet_words = len(bm.get("text", "").split())

        # Keep if it has fetchable URLs OR is a long tweet
        if not urls and tweet_words < 100:
            continue

        results.append({
            "_source_type": "twitter",
            "_urls": urls,
            "_date": dt.isoformat(),
            "_title": f"@{bm.get('author_username', '?')}: {bm.get('text', '')[:80]}",
            "_tweet_data": bm,
        })

    print(f"  Twitter candidates: {len(results)} bookmarks with fetchable content", file=sys.stderr)
    return results


def collect_readwise_candidates() -> list[dict]:
    """Load Readwise Reader items that have been engaged with."""
    if not OTAK_READWISE.exists():
        print(f"  WARNING: No Readwise data at {OTAK_READWISE}", file=sys.stderr)
        return []

    items = json.loads(OTAK_READWISE.read_text())
    print(f"  Loaded {len(items)} Readwise Reader items", file=sys.stderr)

    # Filter: article/rss, has source_url, has reading_progress > 0
    engaged = [
        item for item in items
        if item.get("category") in ("article", "rss")
        and item.get("source_url")
        and _is_article_url(item["source_url"])
        and (item.get("reading_progress") or 0) > 0
    ]
    print(f"  Readwise engaged article/rss with valid URLs: {len(engaged)}", file=sys.stderr)

    results = []
    for item in engaged:
        results.append({
            "_source_type": "readwise",
            "_urls": [item["source_url"]],
            "_date": item.get("saved_at", "") or item.get("created_at", ""),
            "_title": item.get("title", "Untitled"),
            "_reading_progress": item.get("reading_progress", 0),
            "_readwise_data": {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "author": item.get("author", ""),
                "site_name": item.get("site_name", ""),
                "word_count": item.get("word_count", 0),
                "reading_progress": item.get("reading_progress", 0),
                "category": item.get("category", ""),
                "saved_at": item.get("saved_at", ""),
                "summary": item.get("summary", ""),
            },
        })

    return results


def _sample_readwise_diverse(candidates: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Sample Readwise candidates for topic diversity.

    Strategy: sort by reading_progress (highest engagement first), then sample
    across different site_names to get topic diversity.
    """
    if len(candidates) <= n:
        return candidates

    # Group by site_name for diversity
    by_site: dict[str, list[dict]] = {}
    for c in candidates:
        site = c.get("_readwise_data", {}).get("site_name", "unknown")
        by_site.setdefault(site, []).append(c)

    # Sort each group by reading_progress descending
    for site in by_site:
        by_site[site].sort(key=lambda x: -(x.get("_reading_progress") or 0))

    # Round-robin sampling from sites, taking highest-engagement first
    selected = []
    rng = random.Random(seed)
    sites = list(by_site.keys())
    rng.shuffle(sites)

    idx_per_site = {site: 0 for site in sites}
    while len(selected) < n:
        added_any = False
        for site in sites:
            if len(selected) >= n:
                break
            items = by_site[site]
            idx = idx_per_site[site]
            if idx < len(items):
                selected.append(items[idx])
                idx_per_site[site] = idx + 1
                added_any = True
        if not added_any:
            break

    return selected


# ---------------------------------------------------------------------------
# Step 2: Extract article content
# ---------------------------------------------------------------------------

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


def _collect_urls_from_bookmark(bookmark: dict) -> list[str]:
    """Collect all article URLs from a Twitter bookmark."""
    urls = []

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

    qt = bookmark.get("quoted_tweet")
    if qt and isinstance(qt, dict):
        qt_text = qt.get("text", "")
        tco_links = re.findall(r'https?://t\.co/\w+', qt_text)
        for tco in tco_links:
            resolved = _resolve_tco(tco)
            if resolved and _is_article_url(resolved):
                urls.append(resolved)

    return list(dict.fromkeys(urls))


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


def fetch_all_candidates(candidates: list[dict], existing_urls: set[str]) -> list[dict]:
    """Fetch article content for each candidate. Skip URLs already processed."""
    results = []
    skipped = 0

    for i, cand in enumerate(candidates):
        urls = cand.get("_urls", [])

        # Skip if all URLs already exist
        if urls and all(u in existing_urls for u in urls):
            skipped += 1
            continue

        cand_copy = dict(cand)
        cand_copy["_fetched_articles"] = []

        for url in urls:
            if url in existing_urls:
                skipped += 1
                continue
            print(f"  [{i+1}/{len(candidates)}] Fetching: {url[:80]}...", file=sys.stderr)
            article = fetch_article(url)
            if article:
                cand_copy["_fetched_articles"].append(article)
                existing_urls.add(url)
                print(f"    OK: {article['word_count']} words via {article['fetch_method']}: {article['title'][:60]}", file=sys.stderr)
            else:
                print(f"    FAIL: no content extracted", file=sys.stderr)
            time.sleep(0.5)

        # Long-form tweets become articles themselves
        if cand["_source_type"] == "twitter":
            bm = cand.get("_tweet_data", {})
            tweet_words = len(bm.get("text", "").split())
            if not cand_copy["_fetched_articles"] and tweet_words > 100:
                print(f"  [{i+1}/{len(candidates)}] Long tweet ({tweet_words} words) -> article: @{bm.get('author_username', '?')}", file=sys.stderr)
                cand_copy["_fetched_articles"].append({
                    "title": f"Thread by @{bm['author_username']}",
                    "author": bm.get("author_name", bm.get("author_username", "")),
                    "date": cand.get("_date", ""),
                    "text": bm["text"],
                    "word_count": tweet_words,
                    "source_url": bm.get("url", ""),
                    "hostname": "twitter.com",
                    "fetch_method": "tweet_text",
                })

        if cand_copy["_fetched_articles"]:
            results.append(cand_copy)

    fetched_count = len(results)
    print(f"  Fetched: {fetched_count} items with content, {skipped} URLs skipped (already processed)", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 3: Deduplicate
# ---------------------------------------------------------------------------

def _normalize_url(url: str) -> str:
    """Normalize URL for dedup comparison."""
    url = url.rstrip("/")
    url = re.sub(r"\?utm_\w+=[^&]*", "", url)
    url = re.sub(r"[&?]$", "", url)
    return url.lower()


def deduplicate_fetched(fetched: list[dict]) -> list[dict]:
    """Deduplicate fetched items by article URL."""
    seen_urls: set[str] = set()
    results = []

    for item in fetched:
        dominated = False
        for art in item.get("_fetched_articles", []):
            norm = _normalize_url(art.get("source_url", ""))
            if norm in seen_urls:
                dominated = True
                break
            seen_urls.add(norm)

        if not dominated:
            results.append(item)

    print(f"  Deduped: {len(fetched)} -> {len(results)}", file=sys.stderr)
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


def _build_source_ref(candidate: dict, article: dict) -> dict:
    """Build source reference depending on source type."""
    if candidate["_source_type"] == "twitter":
        bm = candidate.get("_tweet_data", {})
        return {
            "type": "twitter_bookmark",
            "tweet_id": bm.get("id", ""),
            "author_username": bm.get("author_username", ""),
            "tweet_text": bm.get("text", "")[:500],
            "bookmarked_at": candidate.get("_date", ""),
        }
    elif candidate["_source_type"] == "readwise":
        rw = candidate.get("_readwise_data", {})
        return {
            "type": "readwise",
            "readwise_id": rw.get("id", ""),
            "reading_progress": rw.get("reading_progress", 0),
            "saved_at": rw.get("saved_at", ""),
            "category": rw.get("category", ""),
        }
    return {"type": "unknown"}


def build_articles(candidates: list[dict], existing_articles: list[dict],
                   dry_run: bool = False) -> list[dict]:
    """Transform fetched candidates into article-centric format with LLM processing."""
    articles = list(existing_articles)  # start with existing

    for i, cand in enumerate(candidates):
        fetched = cand.get("_fetched_articles", [])
        if not fetched:
            continue

        best = max(fetched, key=lambda a: a.get("word_count", 0))
        article_id = _article_id(best["source_url"], cand.get("_date", ""))

        # Skip if article ID already exists
        if any(a["id"] == article_id for a in articles):
            continue

        source = _build_source_ref(cand, best)

        # LLM processing
        if dry_run:
            print(f"  [{i+1}/{len(candidates)}] Would process: {best['title'][:60]} ({best['word_count']} words)", file=sys.stderr)
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
            title_hint = best["title"] or cand.get("_title", "Untitled")
            print(f"  [{i+1}/{len(candidates)}] Processing: {title_hint[:60]} ({best['word_count']} words)", file=sys.stderr)
            prompt = _build_article_prompt(best["text"], title_hint)
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
                    llm = _llm_fallback(best)
            else:
                llm = _llm_fallback(best)

            time.sleep(1)

        section_contents = _split_into_sections(best["text"], llm.get("sections", []))

        fallback_author = ""
        if cand["_source_type"] == "twitter":
            fallback_author = cand.get("_tweet_data", {}).get("author_name", "")
        elif cand["_source_type"] == "readwise":
            fallback_author = cand.get("_readwise_data", {}).get("author", "")

        article = {
            "id": article_id,
            "title": llm.get("title", best["title"]) or best["title"] or cand.get("_title", "Untitled"),
            "author": best.get("author", "") or fallback_author,
            "source_url": best["source_url"],
            "hostname": best.get("hostname", urlparse(best["source_url"]).netloc),
            "date": best.get("date", "") or cand.get("_date", "")[:10],
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


def _llm_fallback(best: dict) -> dict:
    return {
        "title": best["title"],
        "one_line_summary": best["text"][:120],
        "full_summary": best["text"][:500],
        "sections": [],
        "key_claims": [],
        "topics": [],
        "estimated_read_minutes": max(1, best["word_count"] // 200),
        "content_type": "unknown",
    }


def _is_valid_section(heading: str, content: str) -> bool:
    """Check if a section has a valid heading and sufficient content."""
    h = heading.strip()
    if h in ("[", "") or h.startswith("](#"):
        return False
    if len(content.strip()) < 20:
        return False
    return True


def _split_into_sections(content: str, llm_sections: list[dict]) -> list[dict]:
    """Split article content into sections, using LLM headings if available."""
    if llm_sections and len(llm_sections) > 1:
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        headings = list(heading_pattern.finditer(content))

        if headings:
            sections = []
            for j, match in enumerate(headings):
                start = match.end()
                end = headings[j + 1].start() if j + 1 < len(headings) else len(content)
                section_content = content[start:end].strip()
                heading = match.group(2).strip()

                if not _is_valid_section(heading, section_content):
                    continue

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
        return [{
            "heading": "Full Article",
            "content": content,
            "summary": "",
            "key_claims": [],
        }]

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
# Step 5: Extract concepts across articles
# ---------------------------------------------------------------------------

def _build_concept_extraction_prompt(articles_batch: list[dict]) -> str:
    """Build prompt for extracting and deduplicating concepts across articles."""
    articles_info = []
    for a in articles_batch:
        claims = a.get("key_claims", [])
        topics = a.get("topics", [])
        articles_info.append(
            f"Article ID: {a['id']}\n"
            f"Title: {a['title']}\n"
            f"Topics: {', '.join(topics)}\n"
            f"Key Claims:\n" + "\n".join(f"  - {c}" for c in claims)
        )

    return f"""Extract distinct concepts/ideas from these articles. A concept is a specific idea, technique, finding, or claim that a reader might already know or learn.

IMPORTANT:
- Deduplicate: if two articles express the same idea differently, produce ONE concept referencing both articles
- Each concept should be a concise statement (1-2 sentences max)
- Assign each concept ONE primary topic tag
- Include the article IDs where each concept appears

Articles:
{"---".join(articles_info)}

Return a JSON array:
[
  {{
    "text": "concise description of the concept",
    "topic": "primary topic tag",
    "source_article_ids": ["article_id_1", "article_id_2"]
  }}
]

Return ONLY valid JSON array. Extract 3-8 concepts per article, deduplicating across articles."""


def extract_concepts(articles: list[dict], dry_run: bool = False) -> list[dict]:
    """Extract and deduplicate concepts across all articles."""
    if dry_run:
        print("  (dry run -- skipping concept extraction)", file=sys.stderr)
        return []

    # Process in batches of 5 articles for better cross-article dedup
    batch_size = 5
    all_concepts = []
    concept_id_counter = 0

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        # Skip articles with no claims
        batch = [a for a in batch if a.get("key_claims")]
        if not batch:
            continue

        batch_num = i // batch_size + 1
        total_batches = (len(articles) + batch_size - 1) // batch_size
        print(f"  [{batch_num}/{total_batches}] Extracting concepts from {len(batch)} articles...", file=sys.stderr)

        prompt = _build_concept_extraction_prompt(batch)
        response = _call_claude(prompt, timeout=120)

        if response:
            try:
                cleaned = response
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned)
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for item in parsed:
                        concept_id_counter += 1
                        concept = {
                            "id": f"c{concept_id_counter:04d}",
                            "text": item.get("text", ""),
                            "topic": item.get("topic", ""),
                            "source_article_ids": item.get("source_article_ids", []),
                        }
                        if concept["text"]:
                            all_concepts.append(concept)
                    print(f"    Extracted {len(parsed)} concepts", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"    JSON parse failed for concept batch", file=sys.stderr)
        else:
            print(f"    LLM call failed for concept batch", file=sys.stderr)

        time.sleep(1)

    # Second pass: deduplicate similar concepts across batches
    if len(all_concepts) > 20:
        print(f"  Deduplicating {len(all_concepts)} concepts...", file=sys.stderr)
        all_concepts = _deduplicate_concepts(all_concepts)

    # Re-number after dedup
    for i, c in enumerate(all_concepts):
        c["id"] = f"c{i+1:04d}"

    print(f"  Final: {len(all_concepts)} concepts", file=sys.stderr)
    return all_concepts


def _deduplicate_concepts(concepts: list[dict]) -> list[dict]:
    """Simple word-overlap deduplication of concepts."""
    if not concepts:
        return concepts

    def _words(text: str) -> set[str]:
        return set(text.lower().split())

    deduped = []
    for c in concepts:
        c_words = _words(c["text"])
        merged = False
        for existing in deduped:
            e_words = _words(existing["text"])
            overlap = len(c_words & e_words)
            union = len(c_words | e_words)
            if union > 0 and overlap / union > 0.6:
                # Merge: keep longer text, combine source articles
                if len(c["text"]) > len(existing["text"]):
                    existing["text"] = c["text"]
                existing["source_article_ids"] = list(set(
                    existing["source_article_ids"] + c["source_article_ids"]
                ))
                merged = True
                break
        if not merged:
            deduped.append(c)

    return deduped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STEPS = ["collect", "fetch", "dedup", "articles"]


def main():
    parser = argparse.ArgumentParser(description="Build articles.json from Twitter bookmarks and Readwise Reader")
    parser.add_argument("--source", choices=["twitter", "readwise", "all"], default="all",
                        help="Source to process (default: all)")
    parser.add_argument("--fresh", action="store_true", help="Ignore existing articles, start fresh")
    parser.add_argument("--from", dest="from_step", choices=STEPS,
                        help="Start from this step (using cached data)")
    parser.add_argument("--days", type=int, default=365, help="Days back for Twitter bookmarks (default: 365)")
    parser.add_argument("--limit", type=int, default=50, help="Max new articles to process (default: 50)")
    parser.add_argument("--readwise-sample", type=int, default=40,
                        help="Max Readwise items to sample (default: 40)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    parser.add_argument("--concepts-only", action="store_true",
                        help="Only run concept extraction on existing articles")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Concepts-only mode: just extract concepts from existing articles
    if args.concepts_only:
        existing = _load_json(ARTICLES_PATH) or []
        if not existing:
            print("ERROR: No existing articles to extract concepts from", file=sys.stderr)
            sys.exit(1)
        print(f"  Extracting concepts from {len(existing)} existing articles", file=sys.stderr)
        concepts = extract_concepts(existing, dry_run=args.dry_run)
        _save_json(concepts, CONCEPTS_PATH)
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _save_json(concepts, APP_DATA_DIR / "concepts.json")
        print(f"  {len(concepts)} concepts saved", file=sys.stderr)
        return

    start_idx = STEPS.index(args.from_step) if args.from_step else 0

    # Load existing articles for incremental mode
    existing_articles = []
    existing_urls: set[str] = set()
    if not args.fresh and ARTICLES_PATH.exists():
        existing_articles = _load_json(ARTICLES_PATH) or []
        existing_urls = {a.get("source_url", "") for a in existing_articles}
        existing_urls.discard("")
        print(f"  Incremental mode: {len(existing_articles)} existing articles, {len(existing_urls)} URLs", file=sys.stderr)

    # Step 1: Collect candidates
    if start_idx <= 0:
        print("\n=== Step 1: Collect Candidates ===", file=sys.stderr)
        candidates = []

        if args.source in ("twitter", "all"):
            twitter_cands = collect_twitter_candidates(days=args.days)
            candidates.extend(twitter_cands)

        if args.source in ("readwise", "all"):
            readwise_cands = collect_readwise_candidates()
            # Sample for diversity
            readwise_sampled = _sample_readwise_diverse(readwise_cands, args.readwise_sample)
            print(f"  Readwise sampled: {len(readwise_sampled)} of {len(readwise_cands)}", file=sys.stderr)
            candidates.extend(readwise_sampled)

        # Filter out candidates whose URLs are all already processed
        new_candidates = []
        for c in candidates:
            urls = c.get("_urls", [])
            if not urls or not all(u in existing_urls for u in urls):
                new_candidates.append(c)
        print(f"  New candidates after URL dedup: {len(new_candidates)} (skipped {len(candidates) - len(new_candidates)} already processed)", file=sys.stderr)

        # Limit total
        if len(new_candidates) > args.limit:
            # Prioritize: Twitter first (fewer), then Readwise
            twitter_new = [c for c in new_candidates if c["_source_type"] == "twitter"]
            readwise_new = [c for c in new_candidates if c["_source_type"] == "readwise"]
            combined = twitter_new[:args.limit]
            remaining = args.limit - len(combined)
            if remaining > 0:
                combined.extend(readwise_new[:remaining])
            new_candidates = combined
            print(f"  Limited to {len(new_candidates)} candidates", file=sys.stderr)

        _save_json(new_candidates, FILTERED_PATH)
        candidates = new_candidates
    else:
        candidates = _load_json(FILTERED_PATH)
        if not candidates:
            print(f"ERROR: No cached data at {FILTERED_PATH}", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Step 1: Loaded {len(candidates)} cached candidates ===", file=sys.stderr)

    # Step 2: Fetch article content
    if start_idx <= 1:
        print(f"\n=== Step 2: Fetch Article Content ===", file=sys.stderr)
        fetched = fetch_all_candidates(candidates, existing_urls)
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
        deduped = deduplicate_fetched(fetched)
    else:
        deduped = fetched

    # Step 4: Build articles with LLM
    print(f"\n=== Step 4: Build Articles ===", file=sys.stderr)
    if args.dry_run:
        print("  (dry run -- no LLM calls)", file=sys.stderr)

    articles = build_articles(deduped, existing_articles, dry_run=args.dry_run)

    # Save final output
    _save_json(articles, ARTICLES_PATH)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _save_json(articles, APP_DATA_DIR / "articles.json")

    # Step 5: Extract concepts
    print(f"\n=== Step 5: Extract Concepts ===", file=sys.stderr)
    concepts = extract_concepts(articles, dry_run=args.dry_run)
    _save_json(concepts, CONCEPTS_PATH)
    _save_json(concepts, APP_DATA_DIR / "concepts.json")

    # Summary
    sources = {}
    for a in articles:
        src_type = a.get("sources", [{}])[0].get("type", "unknown")
        sources[src_type] = sources.get(src_type, 0) + 1

    print(f"\n=== Done ===", file=sys.stderr)
    print(f"  {len(articles)} total articles", file=sys.stderr)
    for src, count in sorted(sources.items()):
        print(f"    {src}: {count}", file=sys.stderr)
    print(f"  {len(concepts)} concepts extracted", file=sys.stderr)
    print(f"  Output: {ARTICLES_PATH}", file=sys.stderr)
    print(f"  Concepts: {CONCEPTS_PATH}", file=sys.stderr)
    print(f"  App data: {APP_DATA_DIR / 'articles.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
