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

LLM_MODEL = os.environ.get("PETRARCA_LLM_MODEL", "gemini/gemini-2.0-flash")

# litellm expects GEMINI_API_KEY; bridge from our GEMINI_KEY if needed
if os.environ.get("GEMINI_KEY") and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GEMINI_KEY"]


def _call_llm(prompt: str, model: str | None = None) -> str | None:
    """Call LLM via litellm. Model defaults to PETRARCA_LLM_MODEL env var."""
    try:
        from litellm import completion
        response = completion(
            model=model or LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"    LLM error ({model or LLM_MODEL}): {e}", file=sys.stderr)
        return None


# Aliases for backwards compatibility
def _call_gemini(prompt: str, system_instruction: str = None) -> str | None:
    return _call_llm(prompt)

def _call_claude(prompt: str, timeout: int = 180) -> str | None:
    return _call_llm(prompt)




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
  "estimated_read_minutes": 5,
  "content_type": "one of: analysis, tutorial, opinion, news, research, reference, announcement, discussion"
}}

interest_topics: hierarchical topic tags with kebab-case broad/specific categories and optional entity names.
novelty_claims: what's genuinely new or surprising in this article. specificity is "high", "medium", or "low".

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
            response = _call_llm(prompt)

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
            "interest_topics": llm.get("interest_topics", []),
            "novelty_claims": llm.get("novelty_claims", []),
            "word_count": best["word_count"],
            "sources": [source],
        }

        articles.append(article)

        # Save incrementally
        _save_json(articles, ARTICLES_PATH)

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
        response = _call_llm(prompt)

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
    response = _call_llm(prompt)

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
