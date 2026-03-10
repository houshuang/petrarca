#!/usr/bin/env python3
"""Build articles.json from Twitter bookmarks and Readwise Reader.

Pipeline:
  1. Load items from sources (Twitter bookmarks, Readwise Reader)
  2. Filter and select candidates
  3. Fetch article content with 3-tier extraction
  4. Deduplicate by URL
  5. LLM processing: generate sections, summaries, claims per article
  6. Atomic claim decomposition (optional, --claims / --claims-only)
  7. Output articles.json

Usage:
    python3 scripts/build_articles.py                          # all sources
    python3 scripts/build_articles.py --source twitter         # Twitter only
    python3 scripts/build_articles.py --source readwise        # Readwise only
    python3 scripts/build_articles.py --source all             # all sources (default)
    python3 scripts/build_articles.py --from articles          # skip to LLM step
    python3 scripts/build_articles.py --dry-run                # skip LLM calls
    python3 scripts/build_articles.py --limit 50               # max articles to process

Note: logs per-article events to /opt/petrarca/data/logs/ for activity feed.
    python3 scripts/build_articles.py --claims                 # include atomic claim extraction
    python3 scripts/build_articles.py --claims-only            # only run claim extraction on existing articles
    python3 scripts/build_articles.py --skip-claims            # explicitly skip claim extraction
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests as _requests
import trafilatura
from lxml import html as lxml_html
from xml.etree import ElementTree

from server_log import log_server_event
from topic_normalizer import (
    load_registry, save_registry, normalize_article_topics, to_slug,
    normalize_entity, run_normalization_pass, registry_needs_defrag,
    defragment_registry, REGISTRY_PATH,
)

# ---------------------------------------------------------------------------
# Topic normalization
# ---------------------------------------------------------------------------

# Module-level registry — loaded once, updated as articles are processed
_topic_registry: dict | None = None


def _get_topic_registry() -> dict:
    global _topic_registry
    if _topic_registry is None:
        _topic_registry = load_registry()
    return _topic_registry


def normalize_topic(topic) -> str | dict:
    """Normalize a topic string or dict: hyphens to spaces, lowercase, strip whitespace."""
    if isinstance(topic, dict):
        # interest_topics come as {"broad": "...", "specific": "...", "entity": "..."}
        return {k: normalize_topic(v) if isinstance(v, str) else v for k, v in topic.items()}
    return re.sub(r"\s+", " ", topic.replace("-", " ")).strip().lower()


def normalize_interest_topics(raw_topics: list, article_title: str = "") -> list[dict]:
    """Normalize interest_topics against the canonical registry with LLM verification."""
    registry = _get_topic_registry()
    try:
        from gemini_llm import call_llm as _gemini_call_llm
        llm_fn = _gemini_call_llm
    except ImportError:
        llm_fn = None
    return normalize_article_topics(raw_topics, registry, article_title, call_llm=llm_fn)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
SOURCES_DIR = Path(os.environ.get("PETRARCA_SOURCES", str(Path.home() / "src" / "otak" / "data")))
OTAK_BOOKMARKS = SOURCES_DIR / "twitter_bookmarks.json"
OTAK_READWISE = SOURCES_DIR / "readwise_reader.json"

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


def collect_entity_tweets(days: int = 30) -> list[dict]:
    """Find short tweets without URLs that mention books, people, products, etc.
    These are the tweets that the normal pipeline drops."""
    if not OTAK_BOOKMARKS.exists():
        return []

    bookmarks = json.loads(OTAK_BOOKMARKS.read_text())
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    entity_tweets = []

    # Load already-researched tweet IDs
    researched_path = DATA_DIR / "researched_tweets.json"
    researched_ids: set[str] = set()
    if researched_path.exists():
        researched_ids = set(json.loads(researched_path.read_text()))

    for bm in bookmarks:
        try:
            dt = datetime.strptime(bm["created_at"], "%a %b %d %H:%M:%S %z %Y")
        except (KeyError, ValueError):
            continue
        if dt < cutoff:
            continue

        tweet_id = bm.get("id", "")
        if tweet_id in researched_ids:
            continue

        urls = _collect_urls_from_bookmark(bm)
        tweet_words = len(bm.get("text", "").split())

        # We want tweets that were DROPPED by the normal pipeline
        if urls or tweet_words >= 100:
            continue
        if tweet_words < 10:
            continue  # Too short to have meaningful entities

        entity_tweets.append({
            "id": tweet_id,
            "text": bm.get("text", ""),
            "author": bm.get("author_username", ""),
            "date": dt.isoformat(),
            "quoted_text": bm.get("quoted_tweet", {}).get("text", "") if bm.get("quoted_tweet") else "",
        })

    print(f"  Entity tweet candidates: {len(entity_tweets)} (short tweets without URLs)", file=sys.stderr)
    return entity_tweets


def extract_entities_from_tweets(tweets: list[dict], limit: int = 5) -> list[dict]:
    """Use LLM to identify researchable entities in short tweets."""
    if not tweets:
        return []

    # Batch the tweets for efficient LLM usage
    tweets_batch = tweets[:limit * 3]  # Send more than needed, LLM will filter
    tweets_text = "\n---\n".join(
        f"Tweet {i+1} (by @{t['author']}):\n{t['text']}"
        + (f"\nQuoted: {t['quoted_text']}" if t['quoted_text'] else "")
        for i, t in enumerate(tweets_batch)
    )

    prompt = f"""Analyze these bookmarked tweets. For each tweet that mentions a specific book, article, paper, person, company, product, tool, TV show, podcast, or other researchable entity that the user likely wants to learn more about, extract the entity.

Only include tweets where there's a CLEAR entity worth researching. Skip tweets that are just opinions, jokes, or general commentary with no specific entity to look up.

{tweets_text}

Return JSON:
{{
  "entities": [
    {{
      "tweet_index": 1,
      "entity_name": "The Attention Merchants",
      "entity_type": "book",
      "author_or_creator": "Tim Wu",
      "context": "Recommended by the tweeter as important reading on attention economy",
      "search_query": "The Attention Merchants Tim Wu book summary key arguments"
    }}
  ]
}}

If no tweets have clear researchable entities, return {{"entities": []}}."""

    response = _call_llm(prompt, purpose="entity_extraction_tweets")
    if not response:
        return []

    try:
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start < 0:
            return []
        parsed = json.loads(response[json_start:json_end])
        entities = parsed.get("entities", [])

        # Map back to tweet data
        results = []
        for ent in entities[:limit]:
            idx = ent.get("tweet_index", 0) - 1
            if 0 <= idx < len(tweets_batch):
                tweet = tweets_batch[idx]
                results.append({
                    **ent,
                    "tweet_id": tweet["id"],
                    "tweet_text": tweet["text"],
                    "tweet_author": tweet["author"],
                    "tweet_date": tweet["date"],
                })

        print(f"  Found {len(results)} researchable entities in tweets", file=sys.stderr)
        return results
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Entity extraction parse error: {e}", file=sys.stderr)
        return []


def research_entity(entity: dict) -> dict | None:
    """Use LLM to research an entity and synthesize a mini-article."""
    entity_name = entity.get("entity_name", "")
    entity_type = entity.get("entity_type", "")
    context = entity.get("context", "")
    tweet_text = entity.get("tweet_text", "")

    prompt = f"""You are a research assistant. A user bookmarked this tweet:

"{tweet_text}"

They want to learn about: {entity_name} ({entity_type})
Context: {context}

Write a concise but informative article (300-800 words) covering:
1. What it is and why it matters
2. Key facts, arguments, or features
3. How it connects to the tweet's context
4. 2-3 follow-up questions or related topics worth exploring

Be factual and specific — include dates, names, numbers where relevant.

IMPORTANT: Return JSON with these exact fields. Use \\n for newlines inside the content_markdown string (do NOT use actual newlines inside JSON string values):
- "title": article title
- "content_markdown": the article body in markdown (use \\n for line breaks, \\n\\n for paragraph breaks)
- "topics": array of 2-4 topic strings
- "one_line_summary": one sentence summary"""

    from gemini_llm import call_with_search
    response = call_with_search(prompt)
    if not response:
        return None

    try:
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        if json_start < 0:
            print(f"    Could not parse research output for {entity_name}", file=sys.stderr)
            return None

        json_str = response[json_start:json_end]
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to fix common LLM JSON issues: unescaped newlines in strings
            json_str = re.sub(r'(?<=: ")(.*?)(?="[,\}])', lambda m: m.group(0).replace('\n', '\\n').replace('\t', '\\t'), json_str, flags=re.DOTALL)
            parsed = json.loads(json_str)

        parsed["_entity"] = entity
        return parsed

    except Exception as e:
        print(f"    Research parse error for {entity_name}: {e}", file=sys.stderr)
        return None


def process_entity_tweets(limit: int = 3):
    """Full pipeline: find entity tweets → extract entities → research → ingest."""
    print("\n=== Resourceful Bookmark Pipeline ===", file=sys.stderr)

    tweets = collect_entity_tweets()
    if not tweets:
        print("  No entity tweets to process", file=sys.stderr)
        return

    entities = extract_entities_from_tweets(tweets, limit=limit)
    if not entities:
        print("  No researchable entities found", file=sys.stderr)
        return

    # Load existing articles for dedup
    existing_titles: set[str] = set()
    if ARTICLES_PATH.exists():
        for art in json.loads(ARTICLES_PATH.read_text()):
            existing_titles.add(art.get("title", "").lower())

    # Track researched tweet IDs
    researched_path = DATA_DIR / "researched_tweets.json"
    researched_ids: list[str] = []
    if researched_path.exists():
        researched_ids = json.loads(researched_path.read_text())

    articles = []
    if ARTICLES_PATH.exists():
        articles = json.loads(ARTICLES_PATH.read_text())

    ingested = 0
    for ent in entities:
        entity_name = ent.get("entity_name", "")
        print(f"  Researching: {entity_name} ({ent.get('entity_type', '')})", file=sys.stderr)

        result = research_entity(ent)
        if not result:
            continue

        title = result.get("title", entity_name)
        if title.lower() in existing_titles:
            print(f"    Skipping (already exists): {title}", file=sys.stderr)
            continue

        # Build article from research
        content_md = result.get("content_markdown", "")
        word_count = len(content_md.split())
        if word_count < 50:
            print(f"    Skipping (too short): {title} ({word_count} words)", file=sys.stderr)
            continue

        article_id = hashlib.sha256(f"entity:{entity_name}:{ent.get('tweet_id', '')}".encode()).hexdigest()[:12]

        article = {
            "id": article_id,
            "title": title,
            "author": f"Research on @{ent.get('tweet_author', '')} bookmark",
            "date": ent.get("tweet_date", ""),
            "hostname": "petrarca-research",
            "source_url": f"tweet:{ent.get('tweet_id', '')}",
            "content_type": "research_synthesis",
            "word_count": word_count,
            "estimated_read_minutes": max(1, word_count // 200),
            "content_markdown": content_md,
            "one_line_summary": result.get("one_line_summary", ""),
            "topics": result.get("topics", []),
            "sections": [],
            "key_claims": [],
            "novelty_claims": [],
            "fetch_method": "entity_research",
            "_source_tweet": ent.get("tweet_text", ""),
            "_entity_name": entity_name,
            "_entity_type": ent.get("entity_type", ""),
        }

        articles.append(article)
        existing_titles.add(title.lower())
        ingested += 1
        print(f"    Ingested: {title} ({word_count} words)", file=sys.stderr)

        # Mark tweet as researched
        tweet_id = ent.get("tweet_id", "")
        if tweet_id and tweet_id not in researched_ids:
            researched_ids.append(tweet_id)

    if ingested > 0:
        ARTICLES_PATH.write_text(json.dumps(articles, indent=2, ensure_ascii=False))
        print(f"  Ingested {ingested} entity research articles", file=sys.stderr)

    # Save researched tweet IDs
    researched_path.write_text(json.dumps(researched_ids))
    print(f"  Total researched tweets: {len(researched_ids)}", file=sys.stderr)


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


def _xml_to_markdown(xml_str: str) -> str:
    """Convert trafilatura XML to markdown with proper paragraph breaks.

    Trafilatura's built-in markdown serializer merges paragraphs at link
    boundaries and sometimes joins separate <p> blocks. The XML output
    preserves the original paragraph structure, so we convert it ourselves.
    """
    try:
        root = ElementTree.fromstring(xml_str)
    except ElementTree.ParseError:
        return ""

    def _elem_text(elem) -> str:
        """Get full text content including children, with links as markdown."""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            if child.tag == "ref" and child.get("target"):
                link_text = "".join(child.itertext()).strip()
                if link_text:
                    parts.append(f"[{link_text}]({child.get('target')})")
                else:
                    parts.append(child.get("target"))
            elif child.tag == "hi":
                hi_text = "".join(child.itertext()).strip()
                rend = child.get("rend", "")
                if "#b" in rend or "bold" in rend:
                    parts.append(f"**{hi_text}**")
                elif "#i" in rend or "italic" in rend:
                    parts.append(f"*{hi_text}*")
                else:
                    parts.append(hi_text)
            else:
                parts.append("".join(child.itertext()))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts).strip()

    blocks = []
    for main in root.iter("main"):
        for elem in main:
            tag = elem.tag

            if tag == "head":
                rend = elem.get("rend", "h2")
                level = int(rend[1]) if rend.startswith("h") and len(rend) > 1 and rend[1:].isdigit() else 2
                text = _elem_text(elem)
                if text:
                    blocks.append("#" * level + " " + text)

            elif tag == "p":
                text = _elem_text(elem)
                if text and len(text) > 10:
                    blocks.append(text)

            elif tag == "quote":
                text = _elem_text(elem)
                if text:
                    # Prefix each line with >
                    lines = text.split("\n")
                    blocks.append("\n".join("> " + l for l in lines))

            elif tag == "list":
                items = []
                for item in elem.findall("item"):
                    text = _elem_text(item)
                    if text:
                        items.append("- " + text)
                if items:
                    blocks.append("\n".join(items))

            elif tag == "code":
                text = "".join(elem.itertext()).strip()
                if text:
                    blocks.append("```\n" + text + "\n```")

    return "\n\n".join(blocks)


def _split_long_paragraphs(text: str, max_words: int = 200) -> str:
    """Split paragraphs that exceed max_words at sentence boundaries.

    Some articles have genuinely long paragraphs that should be multiple.
    This splits them at the most balanced sentence boundary.
    """
    blocks = text.split("\n\n")
    result = []
    for block in blocks:
        words = block.split()
        # Skip headings, lists, code, blockquotes
        if (block.startswith("#") or block.startswith("- ") or
            block.startswith("* ") or block.startswith("> ") or
            block.startswith("```") or block.startswith("|")):
            result.append(block)
            continue
        if len(words) <= max_words:
            result.append(block)
            continue
        # Split at sentence boundaries (. followed by uppercase letter or quote)
        # Use \p{Lu} equivalent via Unicode range to handle Greek, Cyrillic, etc.
        sentences = re.split(r'(?<=[.!?;·])\s+(?=[A-Z\u00c0-\u024f\u0386-\u03ab\u0400-\u042f\u4e00-\u9fff"\u201c])', block)
        if len(sentences) <= 1:
            result.append(block)
            continue
        # Group sentences into paragraphs of roughly max_words
        current = []
        current_wc = 0
        for sent in sentences:
            swc = len(sent.split())
            if current_wc + swc > max_words and current:
                result.append(" ".join(current))
                current = [sent]
                current_wc = swc
            else:
                current.append(sent)
                current_wc += swc
        if current:
            result.append(" ".join(current))
    return "\n\n".join(result)


def fetch_article(url: str) -> dict | None:
    """3-tier article extraction. Returns dict with title, text (markdown), author, etc."""
    downloaded = None
    text = None
    meta = None
    fetch_method = None

    # Tier 1: trafilatura XML → custom markdown (best paragraph preservation)
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception:
        pass
    if downloaded:
        meta = trafilatura.extract_metadata(downloaded)
        try:
            xml_str = trafilatura.extract(downloaded, output_format="xml", include_links=True)
            if xml_str:
                text = _xml_to_markdown(xml_str)
                if text and len(text.split()) >= 50:
                    fetch_method = "trafilatura+xml"
        except Exception:
            pass
        # Fallback to trafilatura markdown if XML conversion produced too little
        if not text or len(text.split()) < 50:
            text = trafilatura.extract(downloaded, output_format="markdown", include_links=True)
            if text:
                fetch_method = "trafilatura"

    # Tier 2: requests + trafilatura with favor_recall
    if not text:
        try:
            html_str = _fetch_html_requests(url)
            meta = trafilatura.extract_metadata(html_str)
            try:
                xml_str = trafilatura.extract(html_str, output_format="xml",
                                               include_links=True, favor_recall=True)
                if xml_str:
                    text = _xml_to_markdown(xml_str)
                    if text and len(text.split()) >= 50:
                        fetch_method = "requests+trafilatura+xml"
            except Exception:
                pass
            if not text or len(text.split()) < 50:
                text = trafilatura.extract(html_str, output_format="markdown",
                                           include_links=True, favor_recall=True)
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
                # Use thread text if available; normalize single newlines to paragraphs
                tweet_text = bm.get("thread_full_text", bm["text"])
                if "\n\n" not in tweet_text:
                    tweet_text = "\n\n".join(line for line in tweet_text.split("\n") if line.strip())
                cand_copy["_fetched_articles"].append({
                    "title": f"Thread by @{bm['author_username']}",
                    "author": bm.get("author_name", bm.get("author_username", "")),
                    "date": cand.get("_date", ""),
                    "text": tweet_text,
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

from gemini_llm import call_llm as _gemini_call

# Bridge env var for other tools that may use GEMINI_API_KEY
if os.environ.get("GEMINI_KEY") and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GEMINI_KEY"]


def _call_llm(prompt: str, model: str | None = None, purpose: str = "") -> str | None:
    """Call Gemini via google.genai SDK."""
    return _gemini_call(prompt, model=model)


# Aliases for backwards compatibility
def _call_gemini(prompt: str, system_instruction: str = None, purpose: str = "") -> str | None:
    return _call_llm(prompt, purpose=purpose)

def _call_claude(prompt: str, timeout: int = 180, purpose: str = "") -> str | None:
    return _call_llm(prompt, purpose=purpose)




def clean_markdown(text: str) -> str:
    """Clean extracted markdown content for reading.

    Handles: Wikipedia artifacts, nav menus, cookie banners, subscribe cruft,
    heading normalization, social sharing buttons, related articles sections.
    """
    # Remove Wikipedia [edit] section links (various bracket patterns)
    # Must handle [[edit]](URL) first — double-bracket with URL outside
    text = re.sub(r'\s*\[\[edit\]\]\([^)]*\)', '', text)
    text = re.sub(r'\s*\[?\[edit\]\([^)]*\)\]?', '', text)
    text = re.sub(r'\s*\[\[?edit\]?\]', '', text)

    # Fix run-together markdown links: )[  →  ) [  (add space between adjacent links)
    text = re.sub(r'\)\[', ') [', text)

    # Fix run-together link-then-text: ](...) followed immediately by [ or letter
    text = re.sub(r'(\])\(([^)]+)\)([A-Za-z\[])', r'\1(\2) \3', text)

    # Strip inline citation markers like [1], [23], [citation needed]
    text = re.sub(r'\[(\d{1,3})\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)

    # Remove empty link references like [](/wiki/...) or [ ](/wiki/...)
    text = re.sub(r'\[\s*\]\([^)]+\)', '', text)

    # Strip arXiv / academic nav links
    text = re.sub(r'(?im)^\s*\[View PDF\]\([^)]*\)\s*$', '', text)
    text = re.sub(r'(?im)^\s*\[HTML[^\]]*\]\([^)]*\)\s*$', '', text)
    text = re.sub(r'(?im)^\s*\[Download PDF\]\([^)]*\)\s*$', '', text)
    text = re.sub(r'(?im)^\s*\[Full Text[^\]]*\]\([^)]*\)\s*$', '', text)

    # Strip forwarded email header blocks (must come before arXiv metadata
    # stripping, since Subjects?: also matches email Subject: headers)
    text = re.sub(
        r'^-{3,}\s*Forwarded message\s*-{3,}\s*\n'
        r'(?:(?:From|Date|Subject|To|Cc|Bcc):.*\n)*',
        '', text)

    # Strip arXiv metadata lines and PDF artifacts
    text = re.sub(r'(?im)^Subjects?:.*$', '', text)
    text = re.sub(r'(?im)^Cite as:.*arXiv.*$', '', text)
    text = re.sub(r'(?im)^\[Submitted on[^\]]*\]\s*$', '', text)
    text = re.sub(r'(?im)^arXiv:\d{4}\.\d{4,5}(?:v\d+)?\s*\[.*$', '', text)

    # Strip PDF page headers/footers (Author et al. — N — Month Year)
    text = re.sub(r'(?im)^\w+(?:\s+\w+)?\s+et\s+al\.\s+—\s+\d+\s+—\s+\w+\s+\d{4}\s*$', '', text)

    # Strip author affiliation/correspondence lines
    text = re.sub(r'(?im)^[∗\*]?Corresponding author.*$', '', text)

    # Strip nav menus, cookie banners, and subscribe/follow cruft
    _cruft_patterns = [
        # Cookie banners
        r'(?im)^.*cookie\s*(policy|notice|consent|banner|settings?).*$',
        r'(?im)^.*accept\s*(all\s*)?cookies.*$',
        r'(?im)^.*we\s+use\s+cookies.*$',
        r'(?im)^.*manage\s+cookies.*$',
        r'(?im)^.*do\s+not\s+s(ell|hare)\s+my\s+personal.*$',
        # Subscribe / newsletter / sign-up
        r'(?im)^.*subscribe\s+(to\s+)?(our\s+)?(newsletter|mailing\s+list).*$',
        r'(?im)^.*sign\s+up\s+for\s+(our\s+)?(free\s+)?(newsletter|updates).*$',
        r'(?im)^.*enter\s+your\s+email.*$',
        # Follow / share / social
        r'(?im)^.*follow\s+us\s+on\s+(twitter|facebook|instagram|x|linkedin).*$',
        r'(?im)^.*share\s+(this|on)\s+(twitter|facebook|linkedin|x|email).*$',
        r'(?im)^.*(tweet|share|pin|email)\s+this\s*(article|post|story)?.*$',
        r'(?im)^\*{0,2}Share:?\*{0,2}\s+.*(?:Twitter|Facebook|LinkedIn|Reddit).*$',
        # Navigation / chrome
        r'(?im)^.*skip\s+to\s+(main\s+)?content.*$',
        r'(?im)^.*(home|about|contact|privacy|terms)\s*[|/]\s*(home|about|contact|privacy|terms).*$',
        r'(?im)^Menu\s*[☰≡]?\s*$',
        r'(?im)^Toggle\s+navigation\s*$',
        r'(?im)^Navigation\s+Menu\s*$',
        r'(?im)^Search\s*[🔍🔎]?\s*$',
        r'(?im)^Trending:?\s*\[.*$',
        # Sign in / login / subscribe (standalone or as link)
        r'(?im)^Sign\s+in\s*$',
        r'(?im)^Sign\s+up\s*$',
        r'(?im)^Log\s+in\s*$',
        r'(?im)^Subscribe\s*$',
        r'(?im)^\[Sign\s+(?:in|up)\]\(.*\)\s*$',
        r'(?im)^\[Log\s+in\]\(.*\)\s*$',
        r'(?im)^\[Subscribe[^\]]*\]\(.*\)\s*$',
        # Platform-specific chrome (Substack, Medium, Reddit, GitHub)
        r'(?im)^Open\s+in\s+app\s*$',
        r'(?im)^Member[\s-]+only\s+story\s*$',
        r'(?im)^This\s+post\s+is\s+for\s+paid\s+subscribers?\s*$',
        r'(?im)^Already\s+a\s+(paid\s+)?subscriber\?.*$',
        r'(?im)^.*(?:Start\s+Writing|Get\s+the\s+app)\s*$',
        r'(?im)^.*(?:Substack|Medium)\s+is\s+the\s+home.*$',
        r'(?im)^(?:Write|Listen|Share|More)\s*$',
        r'(?im)^.*(?:clapping|clap)\s+up\s+to\s+\d+.*$',
        r'(?im)^.*\d+\s+(?:Likes?|Claps?)\s*·\s*\d+\s+Comments?.*$',
        r'(?im)^.*(?:Get\s+the\s+\w+\s+app|Download\s+on\s+the\s+App\s+Store|Get\s+it\s+on.+Google\s+Play).*$',
        r'(?im)^(?:Reddit\s+app|Reddit\s+coins|Reddit\s+premium).*$',
        r'(?im)^Text\s+to\s+speech\s*$',
        r'(?im)^.*View\s+remaining\s+\d+\s+comments?.*$',
        r'(?im)^.*\[?See\s+all\s+from\b.*$',
        r'(?im)^Recommended\s+from\s+\w.*$',
        r'(?im)^More\s+from\s+\w.*$',
        # Engagement CTA lines with emoji
        r'(?im)^[👏💬🔔📧]\s+.{0,60}$',
        # Follower counts, engagement stats
        r'(?im)^\d[\d,.]*[KMkm]?\s+Followers?\b.*$',
        r'(?im)^.*\d[\d,.]*\s+Followers?\s*·\s*Writer\s+for\b.*$',
        r'(?im)^Written\s+by\s+\w.*$',
        # Paywall indicators
        r'(?im)^[∙·•]\s*Paid\s*$',
        r'(?im)^--\s*$',
        # "· Follow" or "Follow" after author info
        r'(?im)^(?:\w[\w\s]*·\s*)?Follow\s*$',
        # Stray image placeholders (image link with no useful alt text)
        r'(?im)^\[!\]\(.*\)\s*$',
        r'(?im)^\[!\[.*\]\(.*\)\]\(.*\)\s*$',
        # Ad markers
        r'(?im)^ADVERTIS[EI]MENT\s*$',
        r'(?im)^SPONSORED\s*$',
        r'(?im)^AD\s*$',
        # App store badge images
        r'(?im)^\[!\[.*(?:App\s+Store|Google\s+Play).*\]\(.*\)\]\(.*\)\s*$',
        # Vote / award lines (Reddit-style)
        r'(?im)^[⬆⬇]\s*[\d,]+\s*[⬆⬇]?\s*$',
        r'(?im)^[🏅🥈🥉💎]\s+.*$',
        r'(?im)^Sort\s+by:.*$',
        # Author follow lines
        r'(?im)^.*\[Follow\s+@\w+\].*$',
        # Email footer and unsubscribe
        r'(?im)^.*\bunsubscribe\b.*$',
        r'(?im)^.*\bopt[\s-]?out\b.*$',
        r'(?im)^.*view\s+in\s+browser.*$',
        r'(?im)^.*you\s+received\s+this\s+(email|message|newsletter).*$',
        r'(?im)^.*sent\s+from\s+my\s+\w+.*$',
        r'(?im)^.*manage\s+(your\s+)?(email\s+)?preferences.*$',
        # Boilerplate / funding appeals
        r'(?im)^.*buy\s+me\s+a\s+coffee.*$',
        r'(?im)^.*(?:support|donate|back)\s+(?:us|me)\s+on\s+(?:patreon|ko-?fi|open\s*collective).*$',
        r'(?im)^.*(?:patreon|buymeacoffee|ko-fi)\.com/.*$',
        r'(?im)^copyright\s+\d{4}.*$',
        r'(?im)^.*all\s+rights\s+reserved.*$',
        # Universal copyright symbol
        r'(?im)^©\s*\d{4}.*$',
        # Multilingual subscribe/follow/newsletter (NO/SV/DA/DE/FR/ES/IT/ID/ZH)
        r'(?im)^.*(?:abonner|prenumerera|abonnér|abonnieren|abonnez|suscríbete|iscriviti|berlangganan)\b.*(?:nyhetsbrev|nyhetsbrevet|newsletter|noticias|notizie).*$',
        r'(?im)^.*(?:følg|följ|folgen|suivez|síguenos|seguici|ikuti)\b.*(?:facebook|twitter|instagram|linkedin|x\.com).*$',
        r'(?im)^.*关注我们.*$',
        r'(?im)^.*(?:alle\s+rettigheter|alla\s+rättigheter|alle\s+rechte|tous\s+droits|todos\s+los\s+derechos|tutti\s+i\s+diritti)\s+(?:forbeholdt|förbehållna|vorbehalten|réservés|reservados|riservati).*$',
        # Multilingual nav footers (privacy|terms|about|contact equivalents)
        r'(?im)^.*(?:personvern|integritet|datenschutz|confidentialité|privacidad|privacy)\s*[|/].*(?:vilkår|villkor|nutzung|conditions|términos|condizioni|terms).*$',
    ]
    for pattern in _cruft_patterns:
        text = re.sub(pattern, '', text)

    # Strip "Related articles" / "Read Next" / "Recommended" sections (and everything after)
    text = re.sub(
        r'(?im)\n#{1,3}\s*(related\s+(articles?|posts?|stories?|reading)|'
        r'you\s+might\s+also\s+like|recommended(\s+from)?|more\s+from|'
        r'also\s+on|popular\s+(articles?|posts?)|trending|'
        r'read\s+next|star\s+history|comments?\s*\(\d+\)).*$',
        '', text, flags=re.DOTALL
    )

    # Strip social sharing button text blocks
    text = re.sub(r'(?im)^(facebook|twitter|linkedin|reddit|email|copy\s+link|share)\s*$', '', text)

    # Normalize heading hierarchy: strip duplicate H1s (keep first), normalize to H2/H3
    lines = text.split('\n')
    seen_h1 = False
    cleaned_lines = []
    for line in lines:
        h1_match = re.match(r'^#\s+(.+)$', line)
        if h1_match:
            if seen_h1:
                # Demote duplicate H1 to H2
                cleaned_lines.append(f'## {h1_match.group(1)}')
            else:
                seen_h1 = True
                cleaned_lines.append(line)
        else:
            cleaned_lines.append(line)
    text = '\n'.join(cleaned_lines)

    # Clean up blockquote formatting (ensure space after >)
    text = re.sub(r'^>([^ \n])', r'> \1', text, flags=re.MULTILINE)

    # Ensure code blocks have proper newlines around them
    text = re.sub(r'([^\n])(\n```)', r'\1\n\2', text)
    text = re.sub(r'(```\n)([^\n])', r'\1\n\2', text)

    # Strip residual HTML tags that survived markdown conversion
    text = re.sub(r'<(?:div|span|aside|section|header|nav|figure|figcaption)[^>]*>', '', text)
    text = re.sub(r'</(?:div|span|aside|section|header|nav|figure|figcaption)>', '', text)
    text = re.sub(r'<(?:footer|script|style|noscript|iframe)[^>]*>.*?</(?:footer|script|style|noscript|iframe)>', '', text, flags=re.DOTALL)
    text = re.sub(r'<img\s+[^>]*/?>', '', text)
    text = re.sub(r'<input[^>]*/?\s*>', '', text)
    text = re.sub(r'<button[^>]*>[^<]*</button>', '', text)
    # Strip markdown CSS class annotations {.class-name}
    text = re.sub(r'\{[.#][\w-]+\}', '', text)
    # Strip "MENU CLOSE" / "OPEN MENU" / "CLOSE" nav toggles
    text = re.sub(r'(?im)^(?:MENU\s*(?:CLOSE|OPEN)|(?:OPEN|CLOSE)\s*MENU)\s*$', '', text)
    # Strip HN-style footers (Guidelines | FAQ | Lists | ...)
    text = re.sub(r'(?im)^(?:Guidelines|FAQ|Lists|API|Security|Legal).*$', '', text)
    # Strip bare "Search:" prompts
    text = re.sub(r'(?im)^Search:?\s*$', '', text)
    # Strip "Powered by X" lines
    text = re.sub(r'(?im)^Powered\s+by\s+\w.*$', '', text)
    # Strip duplicate heading markers (# # Title → # Title)
    text = re.sub(r'^(#{1,6})\s+\1\s+', r'\1 ', text, flags=re.MULTILINE)

    # Collapse multiple spaces left by removals
    text = re.sub(r'  +', ' ', text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Split long paragraphs at sentence boundaries
    text = _split_long_paragraphs(text, max_words=200)

    return text.strip()


def _is_bibliography_section(heading: str, content: str) -> bool:
    """Check if a section is a bibliography/reference-only section with no reading value."""
    bib_headings = {
        'bibliography', 'references', 'further reading', 'external links',
        'see also', 'notes', 'footnotes', 'citations', 'sources',
        'note e riferimenti', 'riferimenti bibliografici', 'bibliografia',
        'collegamenti esterni', 'voci correlate',
    }
    h_lower = heading.lower().strip()
    for bib in bib_headings:
        if bib in h_lower:
            return True
    return False


def _article_id(url: str, fallback: str = "") -> str:
    src = url or fallback
    return hashlib.sha256(src.encode()).hexdigest()[:12]


def _get_topic_hint() -> str:
    """Build a hint for the LLM with existing canonical topic categories."""
    registry = _get_topic_registry()
    broad_keys = sorted(registry.get("broad", {}).keys())
    if not broad_keys:
        return ""
    specific_by_broad: dict[str, list[str]] = {}
    for slug, info in registry.get("specific", {}).items():
        parent = info.get("broad", "")
        specific_by_broad.setdefault(parent, []).append(slug)
    lines = ["\nPrefer these existing categories when they fit (create new ones only if none match):"]
    for b in broad_keys[:20]:
        specs = sorted(specific_by_broad.get(b, []))[:8]
        if specs:
            lines.append(f"  {b}: {', '.join(specs)}")
        else:
            lines.append(f"  {b}")
    return "\n".join(lines)


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
  "interest_topics": [
    {{"broad": "artificial-intelligence", "specific": "ai-orchestration", "entity": "Claude Code"}}
  ],
  "novelty_claims": [
    {{"claim": "Claude Code now supports background agents", "specificity": "high"}}
  ],
  "entities": [
    {{"name": "Claude Code", "type": "technology", "synthesis": "Anthropic's CLI tool for interacting with Claude models directly from the terminal.", "mentions": ["Claude Code", "claude-code"]}}
  ],
  "follow_up_questions": [
    {{"question": "How does this compare to other approaches in the field?", "connects_to": "broader topic area"}}
  ],
  "estimated_read_minutes": 5,
  "content_type": "one of: analysis, tutorial, opinion, news, research, reference, announcement, discussion"
}}

interest_topics: hierarchical topic tags with kebab-case broad/specific categories and optional entity names.{_get_topic_hint()}
novelty_claims: what's genuinely new or surprising in this article. specificity is "high", "medium", or "low".
entities: extract 3-8 notable entities (people, books, companies, concepts, places, events, technologies) mentioned in the article. Include a 1-2 sentence synthesis and all name variations used in the text.
follow_up_questions: generate 4 curiosity-driven questions that a thoughtful reader might want to explore after reading this article. Include a mix: some that go deeper into the article's core topic, and some that connect to adjacent domains, historical parallels, or contrasting perspectives.

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
            response = _call_llm(prompt, purpose="article_processing")

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
            "content_markdown": clean_markdown(best["text"]),
            "sections": section_contents,
            "one_line_summary": llm.get("one_line_summary", ""),
            "full_summary": llm.get("full_summary", ""),
            "key_claims": llm.get("key_claims", []),
            "topics": llm.get("topics", []),
            "estimated_read_minutes": llm.get("estimated_read_minutes", max(1, best["word_count"] // 200)),
            "content_type": llm.get("content_type", "unknown"),
            "interest_topics": normalize_interest_topics(llm.get("interest_topics", []), llm.get("title", "")),
            "novelty_claims": llm.get("novelty_claims", []),
            "entities": llm.get("entities", []),
            "follow_up_questions": llm.get("follow_up_questions", []),
            "word_count": best["word_count"],
            "fetch_method": best.get("fetch_method", "unknown"),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "sources": [source],
        }

        articles.append(article)

        # Save incrementally
        _save_json(articles, ARTICLES_PATH)

        log_server_event('article_processed',
                         title=article['title'][:100],
                         article_id=article_id,
                         word_count=best['word_count'],
                         content_type=article.get('content_type', 'unknown'))

    return articles


def _llm_fallback(best: dict) -> dict:
    title = best["title"]
    # Replace unhelpful "Thread by @username" titles with first line of content
    if re.match(r'^Thread by @', title, re.IGNORECASE):
        first_line = best["text"].split('\n')[0].strip()[:120]
        if first_line:
            title = first_line

    # Extract basic claims from first sentences as fallback
    sentences = [s.strip() for s in re.split(r'[.!?]\s+', best["text"][:1000]) if len(s.strip()) > 20]
    fallback_claims = sentences[:3]

    return {
        "title": title,
        "one_line_summary": best["text"][:120],
        "full_summary": best["text"][:500],
        "sections": [],
        "key_claims": fallback_claims,
        "topics": [],
        "estimated_read_minutes": max(1, best["word_count"] // 200),
        "content_type": "unknown",
        "entities": [],
        "follow_up_questions": [],
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
                if _is_bibliography_section(heading, section_content):
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

import fcntl

def _save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _load_json(path: Path):
    if path.exists():
        return json.loads(path.read_text())
    return None


def _locked_append_article(article: dict, articles_path: Path, app_data_path: Path | None = None):
    """Append an article to articles.json with file locking to prevent write contention.

    Uses fcntl.flock so multiple concurrent import_url.py processes don't overwrite
    each other's changes.
    """
    lock_path = articles_path.parent / '.articles.lock'
    lock_path.touch(exist_ok=True)

    with open(lock_path, 'r') as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            articles = _load_json(articles_path) or []
            # Check for duplicate by id
            existing_ids = {a['id'] for a in articles}
            if article['id'] not in existing_ids:
                articles.append(article)
                _save_json(articles, articles_path)
                if app_data_path:
                    _save_json(articles, app_data_path)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


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
        response = _call_llm(prompt, purpose="concept_extraction")

        if response:
            try:
                cleaned = response
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned)
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for item in parsed:
                        concept_text = item.get("text", "")
                        concept = {
                            "id": hashlib.sha256(concept_text.encode()).hexdigest()[:10],
                            "text": concept_text,
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

    print(f"  Final: {len(all_concepts)} concepts", file=sys.stderr)
    return all_concepts


def detect_similar_articles(articles: list[dict]) -> list[dict]:
    """Add similar_articles field to articles with Jaccard similarity > 0.5."""
    def _article_words(article):
        words = set()
        for t in article.get("topics", []):
            words.update(t.lower().split())
        for c in article.get("key_claims", []):
            words.update(w.lower() for w in c.split() if len(w) > 3)
        return words

    word_sets = [(a["id"], a["title"], _article_words(a)) for a in articles]

    for i, article in enumerate(articles):
        if not article.get("key_claims"):
            continue
        words_i = word_sets[i][2]
        if not words_i:
            continue

        similar = []
        for j, (aid, title, words_j) in enumerate(word_sets):
            if i == j or not words_j:
                continue
            intersection = len(words_i & words_j)
            union = len(words_i | words_j)
            if union == 0:
                continue
            score = intersection / union
            if score > 0.5:
                similar.append({"id": aid, "title": title, "score": round(score, 2)})

        if similar:
            similar.sort(key=lambda x: -x["score"])
            article["similar_articles"] = similar[:3]

    return articles


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
# Step 6: Atomic claim decomposition
# ---------------------------------------------------------------------------

def _build_atomic_decomposition_prompt(content: str, title: str, topics: list[str]) -> str:
    """Build prompt for extracting atomic claims from an article."""
    if len(content) > 12000:
        content = content[:12000] + "\n\n[... truncated ...]"

    topics_hint = ""
    if topics:
        topics_hint = f"\nExisting topic tags for this article: {', '.join(topics)}\nPrefer these topic tags where applicable, but add new ones if needed.\n"

    return f"""Given this article, extract all knowledge contributions as atomic claims.

Each claim should be:
- MINIMAL: one single assertion (not compound sentences with "and")
- SELF-CONTAINED: understandable without the article context (resolve ALL pronouns, add context)
- NEVER start a claim with: It, This, They, He, She, These, Those, The paper, The author, The study.
  Always use the specific noun, name, or subject instead. Examples:
  BAD: "This paper presents..." → GOOD: "The Codified Context paper presents..."
  BAD: "It is recommended to..." → GOOD: "Users should..." or "Deploying X behind a proxy is recommended"
  BAD: "It makes sense to..." → GOOD: "Trading cost for external quality is worthwhile..."
  BAD: "They found that..." → GOOD: "Researchers at MIT found that..."
- TYPED: classify as factual/causal/comparative/procedural/evaluative/predictive/experiential

Claim types:
- factual: A verifiable statement of fact ("Claude Code supports background agents")
- causal: Cause-and-effect relationship ("Larger context windows reduce hallucination rates")
- comparative: Comparison between entities ("GPT-4 outperforms Claude on math benchmarks")
- procedural: How-to or process description ("To fine-tune a model, first prepare labeled data")
- evaluative: Judgment or assessment ("Gambetta's protection-industry framework is more practical than cultural explanations")
- predictive: Forecast or expectation ("AI agents will replace most SaaS tools by 2027")
- experiential: First-hand experience or observation ("We found that users preferred the simpler UI")

For each claim, provide:
- normalized_text: the claim in canonical, self-contained form (resolve all pronouns, add context)
- original_text: the claim as it appears in the article (exact or near-exact quote)
- claim_type: one of the types above
- source_paragraphs: which paragraph numbers (0-indexed) contain this claim
- topics: relevant topic tags in kebab-case
{topics_hint}
Article title: {title}

Article content (paragraphs separated by blank lines):
{content}

Return a JSON array of claims:
[
  {{
    "normalized_text": "self-contained claim text",
    "original_text": "text as it appears in article",
    "claim_type": "factual",
    "source_paragraphs": [0, 1],
    "topics": ["topic-tag"]
  }}
]

Extract 10-30 claims depending on article length. Focus on substantive knowledge contributions, not obvious statements or filler.
Return ONLY valid JSON array."""


_PRONOUN_START_RE = re.compile(r"^(It|They|This|He|She|These|Those|That)\s", re.IGNORECASE)

_PRONOUN_REWRITES = [
    # "It is recommended to X" → "X is recommended"
    (re.compile(r"^It is (recommended|not recommended|suggested|advisable) to (.+)", re.IGNORECASE),
     lambda m: m.group(2)[0].upper() + m.group(2)[1:].rstrip(".") + " is " + m.group(1) + "."),
    # "It is [adj] for X to Y" → "Y is [adj] for X"
    (re.compile(r"^It is (\w+) for (.+?) to (.+)", re.IGNORECASE),
     lambda m: m.group(3)[0].upper() + m.group(3)[1:].rstrip(".") + " is " + m.group(1) + " for " + m.group(2) + "."),
    # "It is important/necessary/difficult to X" → "X is important"
    (re.compile(r"^It is (important|necessary|useful|helpful|possible|common|difficult|worth noting) (?:to |that )(.+)", re.IGNORECASE),
     lambda m: m.group(2)[0].upper() + m.group(2)[1:].rstrip(".") + " is " + m.group(1) + "."),
    # "It makes sense to X" → capitalize rest
    (re.compile(r"^It makes sense to (.+)", re.IGNORECASE),
     lambda m: m.group(1)[0].upper() + m.group(1)[1:]),
]


def _fix_pronoun_starts(claims: list[dict]) -> list[dict]:
    """Post-process claims to fix pronoun-started claims that the LLM didn't rewrite."""
    for claim in claims:
        text = claim.get("normalized_text", "")
        if not _PRONOUN_START_RE.match(text):
            continue
        for pattern, rewriter in _PRONOUN_REWRITES:
            m = pattern.match(text)
            if m:
                claim["normalized_text"] = rewriter(m)
                break
    return claims


def _claim_id(normalized_text: str) -> str:
    """Generate a stable ID for a claim from its normalized text."""
    return hashlib.sha256(normalized_text.encode()).hexdigest()[:12]


def _extract_claims_for_article(article: dict, index: int, total: int) -> None:
    """Extract atomic claims for a single article. Modifies article in-place."""
    title = article.get("title", "Untitled")
    content = article.get("content_markdown", "")
    topics = article.get("topics", [])

    if not content or len(content.split()) < 50:
        print(f"  [{index}/{total}] Skipping (too short): {title[:60]}", file=sys.stderr)
        article["atomic_claims"] = []
        return

    print(f"  [{index}/{total}] Extracting claims: {title[:60]}", file=sys.stderr)
    prompt = _build_atomic_decomposition_prompt(content, title, topics)
    response = _call_llm(prompt, purpose="claims_extraction")

    if response:
        try:
            cleaned = response
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                claims = []
                for raw_claim in parsed:
                    normalized = raw_claim.get("normalized_text", "").strip()
                    if not normalized:
                        continue
                    claims.append({
                        "normalized_text": normalized,
                        "original_text": raw_claim.get("original_text", "").strip(),
                        "claim_type": raw_claim.get("claim_type", "factual"),
                        "source_paragraphs": raw_claim.get("source_paragraphs", []),
                        "topics": raw_claim.get("topics", []),
                    })
                for c in claims:
                    c["topics"] = [normalize_topic(t) for t in c["topics"]]
                claims = _fix_pronoun_starts(claims)
                for c in claims:
                    c["id"] = _claim_id(c["normalized_text"])
                article["atomic_claims"] = claims
                print(f"    OK: {len(claims)} claims extracted", file=sys.stderr)
            else:
                print(f"    Unexpected response format (not array), skipping", file=sys.stderr)
                article["atomic_claims"] = []
        except json.JSONDecodeError:
            print(f"    JSON parse failed for claims extraction", file=sys.stderr)
            article["atomic_claims"] = []
    else:
        print(f"    LLM call failed for claims extraction", file=sys.stderr)
        article["atomic_claims"] = []


def enrich_articles(articles: list[dict], dry_run: bool = False) -> list[dict]:
    """Add entities, follow_up_questions, and interest_topics to articles that lack them."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    to_process = [a for a in articles
                  if not a.get("entities") or not a.get("follow_up_questions") or not a.get("interest_topics")]
    if not to_process:
        print("  All articles already have entities + follow_up_questions + interest_topics, skipping", file=sys.stderr)
        return articles

    needs_entities = sum(1 for a in to_process if not a.get("entities"))
    needs_topics = sum(1 for a in to_process if not a.get("interest_topics"))
    print(f"  Enriching {len(to_process)} articles (needs entities: {needs_entities}, needs topics: {needs_topics})", file=sys.stderr)

    if dry_run:
        for i, article in enumerate(to_process):
            missing = []
            if not article.get("entities"): missing.append("entities")
            if not article.get("follow_up_questions"): missing.append("questions")
            if not article.get("interest_topics"): missing.append("topics")
            print(f"  [{i+1}/{len(to_process)}] Would enrich ({', '.join(missing)}): {article.get('title', 'Untitled')[:60]}", file=sys.stderr)
        return articles

    topic_hint = _get_topic_hint()

    def _enrich_one(article, index, total):
        title = article.get("title", "Untitled")
        content = article.get("content_markdown", "")
        topics = article.get("topics", [])

        need_entities = not article.get("entities")
        need_questions = not article.get("follow_up_questions")
        need_interest_topics = not article.get("interest_topics")

        if not content or len(content.split()) < 50:
            print(f"  [{index}/{total}] Skipping (too short): {title[:60]}", file=sys.stderr)
            article.setdefault("entities", [])
            article.setdefault("follow_up_questions", [])
            article.setdefault("interest_topics", [])
            return

        # Build prompt requesting only the missing fields
        fields_needed = []
        schema_parts = []
        instructions = []

        if need_entities:
            fields_needed.append("entities")
            schema_parts.append("""  "entities": [
    {{"name": "Entity Name", "type": "person|book|company|concept|event|place|technology", "synthesis": "1-2 sentence description of this entity in context of the article.", "mentions": ["Entity Name", "alternate name"]}}
  ]""")
            instructions.append("entities: extract 3-8 notable entities (people, books, companies, concepts, places, events, technologies) mentioned in the article. Include a 1-2 sentence synthesis and all name variations used in the text.")

        if need_questions:
            fields_needed.append("follow_up_questions")
            schema_parts.append("""  "follow_up_questions": [
    {{"question": "A curiosity-driven question a thoughtful reader might explore after reading this article?", "connects_to": "related topic area"}}
  ]""")
            instructions.append("follow_up_questions: generate 4 curiosity-driven questions that a thoughtful reader might want to explore after reading this article. Include a mix: some that go deeper into the article's core topic, and some that connect to adjacent domains, historical parallels, or contrasting perspectives.")

        if need_interest_topics:
            fields_needed.append("interest_topics")
            schema_parts.append("""  "interest_topics": [
    {{"broad": "broad-category", "specific": "specific-topic", "entity": "Optional Entity Name"}}
  ]""")
            instructions.append(f"interest_topics: hierarchical topic tags with kebab-case broad/specific categories and optional entity names.{topic_hint}")

        missing_str = ", ".join(fields_needed)
        print(f"  [{index}/{total}] Enriching ({missing_str}): {title[:60]}", file=sys.stderr)

        prompt = f"""Analyze this article and extract the following: {missing_str}

Article title: {title}
Topics: {', '.join(topics[:5])}

Article content:
{content[:8000]}

Return a JSON object with these fields:
{{
{','.join(chr(10) + p for p in schema_parts)}
}}

{chr(10).join(instructions)}

Return ONLY valid JSON."""

        response = _call_llm(prompt, purpose="enrich")
        if response:
            try:
                cleaned = response
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned)
                parsed = json.loads(cleaned)
                if need_entities:
                    article["entities"] = parsed.get("entities", [])
                if need_questions:
                    article["follow_up_questions"] = parsed.get("follow_up_questions", [])
                if need_interest_topics:
                    raw_topics = parsed.get("interest_topics", [])
                    article["interest_topics"] = normalize_interest_topics(raw_topics, title)
                counts = []
                if need_entities: counts.append(f"{len(article.get('entities', []))} entities")
                if need_questions: counts.append(f"{len(article.get('follow_up_questions', []))} questions")
                if need_interest_topics: counts.append(f"{len(article.get('interest_topics', []))} topics")
                print(f"    OK: {', '.join(counts)}", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"    JSON parse failed for enrichment", file=sys.stderr)
                article.setdefault("entities", [])
                article.setdefault("follow_up_questions", [])
                article.setdefault("interest_topics", [])
        else:
            print(f"    LLM call failed for enrichment", file=sys.stderr)
            article.setdefault("entities", [])
            article.setdefault("follow_up_questions", [])
            article.setdefault("interest_topics", [])

    max_workers = min(10, len(to_process))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_enrich_one, article, i + 1, len(to_process)): article
            for i, article in enumerate(to_process)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                article = futures[future]
                print(f"    Error enriching {article.get('title', '')[:40]}: {e}", file=sys.stderr)
                article.setdefault("entities", [])
                article.setdefault("follow_up_questions", [])
                article.setdefault("interest_topics", [])

    total_entities = sum(len(a.get("entities", [])) for a in articles)
    total_questions = sum(len(a.get("follow_up_questions", [])) for a in articles)
    total_topics = sum(len(a.get("interest_topics", [])) for a in articles)
    print(f"  Total: {total_entities} entities, {total_questions} follow-up questions, {total_topics} interest topics across all articles", file=sys.stderr)
    return articles


def extract_atomic_claims(articles: list[dict], dry_run: bool = False) -> list[dict]:
    """Extract atomic claims for each article. Modifies articles in-place and returns them."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    to_process = [a for a in articles if not a.get("atomic_claims")]
    if not to_process:
        print("  All articles already have atomic_claims, skipping", file=sys.stderr)
        return articles

    print(f"  Extracting atomic claims for {len(to_process)} articles (skipping {len(articles) - len(to_process)} already done)", file=sys.stderr)

    if dry_run:
        for i, article in enumerate(to_process):
            print(f"  [{i+1}/{len(to_process)}] Would extract claims: {article.get('title', 'Untitled')[:60]}", file=sys.stderr)
            article["atomic_claims"] = []
    else:
        max_workers = min(10, len(to_process))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_extract_claims_for_article, article, i + 1, len(to_process)): article
                for i, article in enumerate(to_process)
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    article = futures[future]
                    print(f"    Error processing {article.get('title', '')[:40]}: {e}", file=sys.stderr)
                    article["atomic_claims"] = []

    total_claims = sum(len(a.get("atomic_claims", [])) for a in articles)
    print(f"  Total atomic claims across all articles: {total_claims}", file=sys.stderr)
    return articles


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
    parser.add_argument("--claims", action="store_true",
                        help="Include atomic claim extraction step")
    parser.add_argument("--claims-only", action="store_true",
                        help="Only run atomic claim extraction on existing articles")
    parser.add_argument("--skip-claims", action="store_true",
                        help="Explicitly skip atomic claim extraction")
    parser.add_argument("--enrich", action="store_true",
                        help="Add entities, follow-up questions, and interest_topics to existing articles that lack them")
    parser.add_argument("--entities", action="store_true",
                        help="Run resourceful entity research on short tweets without URLs")
    parser.add_argument("--entity-limit", type=int, default=3,
                        help="Max entities to research per run (default: 3)")
    parser.add_argument("--normalize-topics", action="store_true",
                        help="Re-normalize interest_topics on all existing articles against the canonical registry")
    parser.add_argument("--defrag-topics", action="store_true",
                        help="Consolidate overpopulated topic categories by merging similar topics via LLM")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Entity research mode: find and research entity mentions in tweets
    if args.entities:
        process_entity_tweets(limit=args.entity_limit)
        return

    # Normalize topics mode: re-normalize all interest_topics against canonical registry
    if args.normalize_topics:
        existing = _load_json(ARTICLES_PATH) or []
        if not existing:
            print("ERROR: No existing articles to normalize topics for", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Topic Normalization ===", file=sys.stderr)
        print(f"  Processing {len(existing)} articles against canonical registry", file=sys.stderr)
        try:
            from gemini_llm import call_llm as _gemini_call_llm
            llm_fn = _gemini_call_llm
        except ImportError:
            print("  WARNING: gemini_llm not available, normalizing without LLM verification", file=sys.stderr)
            llm_fn = None
        articles = run_normalization_pass(existing, call_llm=llm_fn, dry_run=args.dry_run)
        if not args.dry_run:
            _save_json(articles, ARTICLES_PATH)
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _save_json(articles, APP_DATA_DIR / "articles.json")
            save_registry(_get_topic_registry())
            print(f"  Registry saved to {REGISTRY_PATH}", file=sys.stderr)
        return

    # Defrag topics mode: consolidate overpopulated categories
    if args.defrag_topics:
        existing = _load_json(ARTICLES_PATH) or []
        if not existing:
            print("ERROR: No existing articles for defrag", file=sys.stderr)
            sys.exit(1)
        registry = load_registry()
        if not registry_needs_defrag(registry):
            print("  Registry within limits, no defrag needed", file=sys.stderr)
            return
        print(f"\n=== Topic Defragmentation ===", file=sys.stderr)
        try:
            from gemini_llm import call_llm as _gemini_call_llm
            llm_fn = _gemini_call_llm
        except ImportError:
            print("  ERROR: gemini_llm required for defrag", file=sys.stderr)
            sys.exit(1)
        merge_map = defragment_registry(registry, existing, call_llm=llm_fn, dry_run=args.dry_run)
        if merge_map and not args.dry_run:
            save_registry(registry)
            _save_json(existing, ARTICLES_PATH)
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _save_json(existing, APP_DATA_DIR / "articles.json")
            print(f"  Registry and articles saved", file=sys.stderr)
        return

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
        manifest = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "article_count": len(existing),
            "concept_count": len(concepts),
            "articles_hash": hashlib.sha256(json.dumps(existing, sort_keys=True).encode()).hexdigest()[:16],
            "concepts_hash": hashlib.sha256(json.dumps(concepts, sort_keys=True).encode()).hexdigest()[:16],
        }
        _save_json(manifest, DATA_DIR / "manifest.json")
        print(f"  {len(concepts)} concepts saved", file=sys.stderr)
        return

    # Claims-only mode: just extract atomic claims from existing articles
    if args.claims_only:
        existing = _load_json(ARTICLES_PATH) or []
        if not existing:
            print("ERROR: No existing articles to extract claims from", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Atomic Claim Extraction (claims-only mode) ===", file=sys.stderr)
        articles = extract_atomic_claims(existing, dry_run=args.dry_run)
        _save_json(articles, ARTICLES_PATH)
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _save_json(articles, APP_DATA_DIR / "articles.json")
        total_claims = sum(len(a.get("atomic_claims", [])) for a in articles)
        print(f"  Done: {total_claims} total claims across {len(articles)} articles", file=sys.stderr)
        return

    # Enrich mode: add entities + follow_up_questions to existing articles
    if args.enrich:
        existing = _load_json(ARTICLES_PATH) or []
        if not existing:
            print("ERROR: No existing articles to enrich", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Enrich Articles (entities + follow-up questions) ===", file=sys.stderr)
        articles = enrich_articles(existing, dry_run=args.dry_run)
        _save_json(articles, ARTICLES_PATH)
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _save_json(articles, APP_DATA_DIR / "articles.json")
        manifest = _load_json(DATA_DIR / "manifest.json") or {}
        manifest["articles_hash"] = hashlib.sha256(json.dumps(articles, sort_keys=True).encode()).hexdigest()[:16]
        manifest["last_updated"] = datetime.now(timezone.utc).isoformat()
        _save_json(manifest, DATA_DIR / "manifest.json")
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

    # Detect similar articles before saving
    print(f"\n=== Step 4b: Detect Similar Articles ===", file=sys.stderr)
    articles = detect_similar_articles(articles)
    similar_count = sum(1 for a in articles if a.get("similar_articles"))
    print(f"  {similar_count} articles have similar matches", file=sys.stderr)

    # Step 4c: Atomic claim extraction (opt-in via --claims)
    if args.claims and not args.skip_claims:
        print(f"\n=== Step 4c: Atomic Claim Extraction ===", file=sys.stderr)
        articles = extract_atomic_claims(articles, dry_run=args.dry_run)

    # Save final output
    _save_json(articles, ARTICLES_PATH)
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _save_json(articles, APP_DATA_DIR / "articles.json")

    # Save topic registry if it was updated during processing
    if _topic_registry is not None:
        save_registry(_topic_registry)

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

    # Step 6: Generate manifest
    manifest = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "concept_count": len(concepts),
        "articles_hash": hashlib.sha256(json.dumps(articles, sort_keys=True).encode()).hexdigest()[:16],
        "concepts_hash": hashlib.sha256(json.dumps(concepts, sort_keys=True).encode()).hexdigest()[:16],
    }
    _save_json(manifest, DATA_DIR / "manifest.json")

    print(f"\n=== Done ===", file=sys.stderr)
    print(f"  {len(articles)} total articles", file=sys.stderr)
    for src, count in sorted(sources.items()):
        print(f"    {src}: {count}", file=sys.stderr)
    print(f"  {len(concepts)} concepts extracted", file=sys.stderr)
    total_claims = sum(len(a.get("atomic_claims", [])) for a in articles)
    if total_claims:
        print(f"  {total_claims} atomic claims extracted", file=sys.stderr)
    print(f"  Output: {ARTICLES_PATH}", file=sys.stderr)
    print(f"  Concepts: {CONCEPTS_PATH}", file=sys.stderr)
    print(f"  App data: {APP_DATA_DIR / 'articles.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
