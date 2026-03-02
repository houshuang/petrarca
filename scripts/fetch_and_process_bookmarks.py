#!/usr/bin/env python3
"""Fetch Twitter bookmarks and process Claude Code-related content.

Pipeline:
  1. Load bookmarks (from otak cache or fresh fetch)
  2. Filter for Claude Code-related tweets (smart keyword matching)
  3. Extract article content from linked URLs (via trafilatura)
  4. Deduplicate tweets/articles about the same topic
  5. Summarize and extract key claims via claude -p

Saves intermediate results after each step so work is resumable.

Usage:
    # Full pipeline (uses cached bookmarks if < 24h old)
    python3 scripts/fetch_and_process_bookmarks.py

    # Force fresh bookmark fetch
    python3 scripts/fetch_and_process_bookmarks.py --fresh

    # Run only specific steps (skip earlier steps if cache exists)
    python3 scripts/fetch_and_process_bookmarks.py --from filter
    python3 scripts/fetch_and_process_bookmarks.py --from extract
    python3 scripts/fetch_and_process_bookmarks.py --from dedup
    python3 scripts/fetch_and_process_bookmarks.py --from summarize

    # Adjust recency window (default: 21 days)
    python3 scripts/fetch_and_process_bookmarks.py --days 30

    # Dry run (show what would be processed, no LLM calls)
    python3 scripts/fetch_and_process_bookmarks.py --dry-run

Output:
    data/bookmarks_filtered.json    — Claude Code-related tweets
    data/bookmarks_extracted.json   — With article content added
    data/bookmarks_deduped.json     — Deduplicated/grouped
    data/bookmarks_final.json       — With summaries and key claims
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
OTAK_BOOKMARKS = Path.home() / "src" / "otak" / "data" / "twitter_bookmarks.json"
OTAK_FETCHER = Path.home() / "src" / "otak" / "scripts" / "fetch_twitter_bookmarks.py"
OTAK_VENV_PYTHON = Path.home() / "src" / "otak" / ".venv" / "bin" / "python3"

# Intermediate files
FILTERED_PATH = DATA_DIR / "bookmarks_filtered.json"
EXTRACTED_PATH = DATA_DIR / "bookmarks_extracted.json"
DEDUPED_PATH = DATA_DIR / "bookmarks_deduped.json"
FINAL_PATH = DATA_DIR / "bookmarks_final.json"

STEPS = ["filter", "extract", "dedup", "summarize"]

# ---------------------------------------------------------------------------
# Step 0: Load bookmarks
# ---------------------------------------------------------------------------


def load_bookmarks(fresh: bool = False, max_age_hours: int = 24) -> list[dict]:
    """Load bookmarks from otak cache, fetching fresh if needed."""
    need_fetch = fresh

    if not need_fetch and OTAK_BOOKMARKS.exists():
        age = time.time() - OTAK_BOOKMARKS.stat().st_mtime
        age_hours = age / 3600
        print(f"  Cached bookmarks age: {age_hours:.1f}h", file=sys.stderr)
        if age_hours > max_age_hours:
            print(f"  Cache older than {max_age_hours}h, fetching fresh...", file=sys.stderr)
            need_fetch = True
    elif not OTAK_BOOKMARKS.exists():
        print("  No cached bookmarks found, fetching...", file=sys.stderr)
        need_fetch = True

    if need_fetch:
        print("  Fetching bookmarks via otak...", file=sys.stderr)
        if not OTAK_VENV_PYTHON.exists():
            print(f"ERROR: otak venv not found at {OTAK_VENV_PYTHON}", file=sys.stderr)
            print("Run: python3 -m venv /Users/stian/src/otak/.venv && "
                  "/Users/stian/src/otak/.venv/bin/pip install twikit", file=sys.stderr)
            sys.exit(1)
        result = subprocess.run(
            [str(OTAK_VENV_PYTHON), str(OTAK_FETCHER), "--limit", "200", "--save"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"ERROR fetching bookmarks:\n{result.stderr}", file=sys.stderr)
            if "expired" in result.stderr.lower() or "unauthorized" in result.stderr.lower():
                print("Cookies expired. Run:", file=sys.stderr)
                print(f"  {OTAK_VENV_PYTHON} {OTAK_FETCHER} --extract-cookies", file=sys.stderr)
            sys.exit(1)
        print(f"  {result.stderr.strip()}", file=sys.stderr)

    bookmarks = json.loads(OTAK_BOOKMARKS.read_text())
    print(f"  Loaded {len(bookmarks)} bookmarks", file=sys.stderr)
    return bookmarks


# ---------------------------------------------------------------------------
# Step 1: Filter for Claude Code related tweets
# ---------------------------------------------------------------------------

# Strong signals: very likely about Claude Code / AI coding tools
STRONG_PATTERNS = [
    r"\bclaude\s+code\b",
    r"\bclaude\s+cli\b",
    r"\bclaude\s+-p\b",
    r"\bclaude\.ai\b",
    r"\b@claudeai\b",
    r"\banthrop(?:ic|ics)\b",
    r"\bclaude\s+(?:sonnet|haiku|opus)\b",
    r"\bclaude\s+agent\b",
    r"\bclaude\s+desktop\b",
    r"\bclaude\s+(?:3|4)\b",
    r"\bmodel\s*context\s*protocol\b",
    r"\bmcp\s+server\b",
    r"\bmcp\s+tool\b",
    r"\bclaude(?:code|_code)\b",
    r"\bCLAUDE\.md\b",
    r"\bAGENTS\.md\b",
]

# Medium signals: could be about Claude Code if combined with coding context
MEDIUM_PATTERNS = [
    r"\bclaude\b",
    r"\bmcp\b",
    r"\bagentic\s+cod(?:ing|er|e)\b",
    r"\bai\s+cod(?:ing|er|e)\b",
    r"\bcoding\s+agent\b",
    r"\bcode\s+agent\b",
    r"\bvibe\s*cod(?:ing|er|e)\b",
    r"\bllm\s+(?:cod(?:ing|er|e)|agent)\b",
]

# Coding context keywords (boost medium signals)
CODING_CONTEXT = [
    r"\bgithub\b", r"\bprompt\b", r"\bterminal\b", r"\beditor\b", r"\bvscode\b",
    r"\bcursor\b", r"\bcopilot\b", r"\bwindsurf\b", r"\bcodebase\b", r"\brefactor\b",
    r"\bdebug\b", r"\bpull\s+request\b", r"\bcommit\b", r"\bbranch\b", r"\brepo\b",
    r"\bdev\s+tool\b", r"\btool\s+use\b", r"\btool\s+calling\b",
    r"\bprogramm(?:ing|er)\b", r"\bdevelop(?:er|ment)\b",
    r"\bapi\b", r"\bsdk\b", r"\bopen\s*source\b",
]

# Negative signals: "claude" in non-code context
NEGATIVE_PATTERNS = [
    r"\bclaude\s+(?:monet|debussy|shannon|bernard|rains|giroux|levi.?strauss)\b",
    r"\bvan\s+damme\b",
]


def _get_full_text(bookmark: dict) -> str:
    """Get all searchable text from a bookmark."""
    parts = [bookmark.get("text", "")]
    qt = bookmark.get("quoted_tweet")
    if qt and isinstance(qt, dict):
        parts.append(qt.get("text", ""))
    # Include URL display text
    for u in bookmark.get("urls", []):
        parts.append(u.get("display_url", ""))
        parts.append(u.get("expanded_url", ""))
    return " ".join(parts)


def _score_relevance(bookmark: dict) -> tuple[float, list[str]]:
    """Score a bookmark for Claude Code relevance. Returns (score, matched_patterns)."""
    text = _get_full_text(bookmark).lower()
    matched = []

    # Check negative patterns first
    for pat in NEGATIVE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return 0.0, ["negative_match"]

    score = 0.0

    # Strong patterns: each adds 1.0
    for pat in STRONG_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            score += 1.0
            matched.append(f"strong:{pat}")

    # Medium patterns: each adds 0.4
    for pat in MEDIUM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            score += 0.4
            matched.append(f"medium:{pat}")

    # Coding context: each adds 0.15
    for pat in CODING_CONTEXT:
        if re.search(pat, text, re.IGNORECASE):
            score += 0.15
            matched.append(f"context:{pat}")

    # Known Claude Code authors get a small boost
    known_authors = {
        "trq212", "alexalbert__", "birch_labs", "aaborovkov",
        "simonw", "swyx", "karpathy", "nateberkopec", "arvidkahl",
    }
    if bookmark.get("author_username", "").lower() in known_authors:
        score += 0.3
        matched.append("known_author")

    return score, matched


def parse_twitter_date(date_str: str) -> datetime:
    """Parse Twitter's date format into timezone-aware datetime."""
    return datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")


def filter_bookmarks(bookmarks: list[dict], days: int = 21, min_score: float = 0.8) -> list[dict]:
    """Filter bookmarks for Claude Code relevance within recent time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []
    skipped_date = 0
    skipped_score = 0

    for bm in bookmarks:
        # Date filter
        try:
            dt = parse_twitter_date(bm["created_at"])
        except (KeyError, ValueError):
            continue
        if dt < cutoff:
            skipped_date += 1
            continue

        # Relevance scoring
        score, matched = _score_relevance(bm)
        if score < min_score:
            skipped_score += 1
            continue

        bm_copy = dict(bm)
        bm_copy["_relevance_score"] = round(score, 2)
        bm_copy["_matched_patterns"] = matched
        bm_copy["_parsed_date"] = dt.isoformat()
        results.append(bm_copy)

    # Sort by relevance score (descending), then date (newest first)
    results.sort(key=lambda x: (-x["_relevance_score"], x["_parsed_date"]), reverse=False)

    print(f"  Filtered: {len(results)} relevant (skipped {skipped_date} too old, "
          f"{skipped_score} below score threshold {min_score})", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 2: Extract article content from linked URLs
# ---------------------------------------------------------------------------


def _resolve_url(url: str) -> str | None:
    """Resolve t.co and other shorteners to final URL."""
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.url
    except Exception:
        # Try GET as fallback (some servers don't support HEAD)
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.url
        except Exception:
            return None


def _is_article_url(url: str) -> bool:
    """Check if a URL is likely a readable article (not an image, video, etc.)."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    # Skip social media, image/video hosting
    skip_domains = {
        "twitter.com", "x.com", "t.co",
        "youtube.com", "youtu.be",
        "instagram.com", "tiktok.com",
        "imgur.com", "giphy.com",
        "open.spotify.com",
    }
    if any(d in domain for d in skip_domains):
        return False

    # Skip obvious non-articles
    skip_extensions = {".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mp3", ".pdf", ".zip"}
    if any(path.endswith(ext) for ext in skip_extensions):
        return False

    return True


def _extract_article(url: str, timeout_sec: int = 20) -> dict | None:
    """Extract article text and metadata using trafilatura with timeout."""
    import signal
    import trafilatura

    class _Timeout(Exception):
        pass

    def _handler(signum, frame):
        raise _Timeout()

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout_sec)
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        result = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            output_format="json",
            with_metadata=True,
        )
        if not result:
            return None
        data = json.loads(result)
        text = data.get("text", "")
        # Only keep articles with substantial content
        if len(text) < 200:
            return None
        return {
            "title": data.get("title", ""),
            "author": data.get("author", ""),
            "date": data.get("date", ""),
            "text": text,
            "excerpt": text[:500] + ("..." if len(text) > 500 else ""),
            "word_count": len(text.split()),
            "source_url": url,
            "hostname": data.get("hostname", ""),
        }
    except _Timeout:
        print(f"    Timed out fetching {url} after {timeout_sec}s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    Failed to extract {url}: {e}", file=sys.stderr)
        return None
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def extract_articles(bookmarks: list[dict]) -> list[dict]:
    """For each bookmark with URLs, try to extract article content."""
    results = []
    for i, bm in enumerate(bookmarks):
        bm_copy = dict(bm)
        bm_copy["extracted_articles"] = []

        urls = bm.get("urls", [])
        if urls:
            for url_info in urls:
                expanded = url_info.get("expanded_url", "")
                if not expanded:
                    continue

                # Twitter stores expanded URLs directly; only resolve if still shortened
                if "t.co/" in expanded or "bit.ly/" in expanded:
                    resolved = _resolve_url(expanded)
                    if resolved:
                        expanded = resolved

                if not _is_article_url(expanded):
                    continue

                print(f"  [{i+1}/{len(bookmarks)}] Extracting: {expanded[:80]}...", file=sys.stderr)
                article = _extract_article(expanded)
                if article:
                    bm_copy["extracted_articles"].append(article)
                    print(f"    Got {article['word_count']} words: {article['title'][:60]}", file=sys.stderr)
                else:
                    print(f"    No article content extracted", file=sys.stderr)

                time.sleep(0.5)  # polite crawling

        results.append(bm_copy)

    articles_found = sum(1 for bm in results if bm["extracted_articles"])
    print(f"  Extracted articles for {articles_found}/{len(results)} bookmarks", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 3: Deduplicate / group related items
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """Normalize text for dedup comparison."""
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)  # remove URLs
    text = re.sub(r"@\w+", "", text)  # remove mentions
    text = re.sub(r"#\w+", "", text)  # remove hashtags
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _text_similarity(a: str, b: str) -> float:
    """Simple word-overlap Jaccard similarity."""
    words_a = set(_normalize_text(a).split())
    words_b = set(_normalize_text(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _same_article_url(bm_a: dict, bm_b: dict) -> bool:
    """Check if two bookmarks link to the same article."""
    urls_a = {u.get("expanded_url", "") for u in bm_a.get("urls", [])}
    urls_b = {u.get("expanded_url", "") for u in bm_b.get("urls", [])}
    # Remove empty strings
    urls_a.discard("")
    urls_b.discard("")
    if urls_a and urls_b:
        return bool(urls_a & urls_b)
    return False


def deduplicate(bookmarks: list[dict]) -> list[dict]:
    """Group bookmarks about the same topic/article.

    Strategy:
    - If two bookmarks share the same article URL, group them
    - If tweet text similarity > 0.5, group them
    - Keep the highest-scored bookmark as the primary in each group
    """
    n = len(bookmarks)
    groups = []  # list of lists of indices
    assigned = set()

    for i in range(n):
        if i in assigned:
            continue
        group = [i]
        assigned.add(i)

        for j in range(i + 1, n):
            if j in assigned:
                continue

            # Check URL overlap
            if _same_article_url(bookmarks[i], bookmarks[j]):
                group.append(j)
                assigned.add(j)
                continue

            # Check text similarity
            text_i = _get_full_text(bookmarks[i])
            text_j = _get_full_text(bookmarks[j])
            if _text_similarity(text_i, text_j) > 0.5:
                group.append(j)
                assigned.add(j)

        groups.append(group)

    # Build output: primary bookmark + related
    results = []
    for group in groups:
        # Sort by relevance score descending
        group.sort(key=lambda idx: -bookmarks[idx].get("_relevance_score", 0))
        primary = dict(bookmarks[group[0]])
        if len(group) > 1:
            primary["_related_tweets"] = [
                {
                    "id": bookmarks[idx]["id"],
                    "url": bookmarks[idx]["url"],
                    "author_username": bookmarks[idx]["author_username"],
                    "text": bookmarks[idx]["text"][:280],
                }
                for idx in group[1:]
            ]
        results.append(primary)

    print(f"  Deduped: {n} bookmarks -> {len(results)} groups", file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Step 4: Summarize via claude -p
# ---------------------------------------------------------------------------


def _call_claude(prompt: str, timeout: int = 120) -> str | None:
    """Call claude -p for LLM processing. Returns the response text."""
    try:
        # Unset CLAUDECODE env var to allow nested calls
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        result = subprocess.run(
            ["claude", "-p", prompt, "--max-turns", "1"],
            capture_output=True, text=True, timeout=timeout,
            env=env,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"    claude -p error: {result.stderr[:200]}", file=sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print(f"    claude -p timed out after {timeout}s", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("    claude CLI not found in PATH", file=sys.stderr)
        return None


def _build_summary_prompt(bookmark: dict) -> str:
    """Build a prompt for summarizing a bookmark and its article content."""
    parts = []
    parts.append(f"Tweet by @{bookmark['author_username']} ({bookmark.get('author_name', '')}):")
    parts.append(bookmark["text"])

    qt = bookmark.get("quoted_tweet")
    if qt and isinstance(qt, dict) and qt.get("text"):
        parts.append(f"\nQuoted tweet by @{qt.get('author_username', '?')}:")
        parts.append(qt["text"])

    articles = bookmark.get("extracted_articles", [])
    for art in articles:
        parts.append(f"\n--- Linked article: {art['title']} ---")
        # Truncate very long articles to keep prompt manageable
        text = art["text"]
        if len(text) > 8000:
            text = text[:8000] + "\n[... truncated ...]"
        parts.append(text)

    related = bookmark.get("_related_tweets", [])
    if related:
        parts.append("\n--- Related tweets about the same topic ---")
        for r in related:
            parts.append(f"@{r['author_username']}: {r['text']}")

    content = "\n".join(parts)

    prompt = f"""Analyze this tweet (and any linked article content) about Claude Code / AI coding tools.

Return a JSON object with these fields:
- "summary": A 2-3 sentence summary of the key point or insight (factual, no hype)
- "key_claims": An array of specific factual claims or insights (each a short string, max 5 items)
- "content_type": One of "tip", "opinion", "tutorial", "announcement", "experience_report", "tool_comparison", "workflow", "discussion"
- "topics": Array of relevant topic tags (e.g., "prompt-caching", "mcp", "agents", "workflow", "performance")
- "relevance": A score 1-5 for how relevant/useful this is to someone using Claude Code daily (5 = must read)
- "novelty": A score 1-5 for how novel/non-obvious the information is (5 = genuinely new insight)

Return ONLY valid JSON, no markdown formatting.

Content:
{content}"""

    return prompt


def summarize_bookmarks(bookmarks: list[dict], dry_run: bool = False) -> list[dict]:
    """Add LLM-generated summaries to each bookmark."""
    results = []

    for i, bm in enumerate(bookmarks):
        bm_copy = dict(bm)
        prompt = _build_summary_prompt(bm)

        if dry_run:
            print(f"  [{i+1}/{len(bookmarks)}] Would summarize: @{bm['author_username']}: "
                  f"{bm['text'][:80]}...", file=sys.stderr)
            bm_copy["_llm_summary"] = {"summary": "[dry run]", "key_claims": [], "content_type": "unknown",
                                       "topics": [], "relevance": 0, "novelty": 0}
            results.append(bm_copy)
            continue

        print(f"  [{i+1}/{len(bookmarks)}] Summarizing: @{bm['author_username']}: "
              f"{bm['text'][:80]}...", file=sys.stderr)

        response = _call_claude(prompt)
        if response:
            # Try to parse JSON from response
            try:
                # Handle case where response is wrapped in markdown code block
                cleaned = response
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                    cleaned = re.sub(r"\n?```$", "", cleaned)
                summary = json.loads(cleaned)
                bm_copy["_llm_summary"] = summary
                print(f"    -> {summary.get('content_type', '?')} "
                      f"(relevance={summary.get('relevance', '?')}, "
                      f"novelty={summary.get('novelty', '?')})", file=sys.stderr)
            except json.JSONDecodeError:
                print(f"    Failed to parse JSON response, saving raw", file=sys.stderr)
                bm_copy["_llm_summary"] = {"raw_response": response, "parse_error": True}
        else:
            bm_copy["_llm_summary"] = {"error": "claude -p call failed"}

        results.append(bm_copy)
        # Save after each item for resumability
        _save_json(results, FINAL_PATH)
        time.sleep(1)  # be nice to Claude

    return results


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _save_json(data: list | dict, path: Path):
    """Save data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _load_json(path: Path) -> list | dict | None:
    """Load JSON file if it exists."""
    if path.exists():
        return json.loads(path.read_text())
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Fetch and process Claude Code bookmarks")
    parser.add_argument("--fresh", action="store_true",
                        help="Force fresh bookmark fetch from Twitter")
    parser.add_argument("--from", dest="from_step", choices=STEPS,
                        help="Start from this step (uses cached results for earlier steps)")
    parser.add_argument("--days", type=int, default=21,
                        help="How many days back to look (default: 21)")
    parser.add_argument("--min-score", type=float, default=0.8,
                        help="Minimum relevance score for filtering (default: 0.8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be processed, skip LLM calls")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed matching info")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    start_idx = STEPS.index(args.from_step) if args.from_step else 0

    # Step 1: Filter
    if start_idx <= 0:
        print("\n=== Step 1: Load & Filter Bookmarks ===", file=sys.stderr)
        bookmarks = load_bookmarks(fresh=args.fresh)
        filtered = filter_bookmarks(bookmarks, days=args.days, min_score=args.min_score)

        if args.verbose:
            for bm in filtered:
                print(f"  [{bm['_relevance_score']:.1f}] @{bm['author_username']}: "
                      f"{bm['text'][:100]}...", file=sys.stderr)
                for m in bm["_matched_patterns"]:
                    print(f"        {m}", file=sys.stderr)

        _save_json(filtered, FILTERED_PATH)
        print(f"  Saved to {FILTERED_PATH}", file=sys.stderr)
    else:
        filtered = _load_json(FILTERED_PATH)
        if not filtered:
            print(f"ERROR: No cached data at {FILTERED_PATH}, run without --from", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Step 1: Loaded {len(filtered)} cached filtered bookmarks ===", file=sys.stderr)

    if not filtered:
        print("No relevant bookmarks found. Try increasing --days or lowering --min-score.", file=sys.stderr)
        sys.exit(0)

    # Step 2: Extract articles
    if start_idx <= 1:
        print(f"\n=== Step 2: Extract Article Content ===", file=sys.stderr)
        extracted = extract_articles(filtered)
        _save_json(extracted, EXTRACTED_PATH)
        print(f"  Saved to {EXTRACTED_PATH}", file=sys.stderr)
    else:
        extracted = _load_json(EXTRACTED_PATH)
        if not extracted:
            print(f"ERROR: No cached data at {EXTRACTED_PATH}, run from 'extract' step", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Step 2: Loaded {len(extracted)} cached extracted bookmarks ===", file=sys.stderr)

    # Step 3: Deduplicate
    if start_idx <= 2:
        print(f"\n=== Step 3: Deduplicate ===", file=sys.stderr)
        deduped = deduplicate(extracted)
        _save_json(deduped, DEDUPED_PATH)
        print(f"  Saved to {DEDUPED_PATH}", file=sys.stderr)
    else:
        deduped = _load_json(DEDUPED_PATH)
        if not deduped:
            print(f"ERROR: No cached data at {DEDUPED_PATH}, run from 'dedup' step", file=sys.stderr)
            sys.exit(1)
        print(f"\n=== Step 3: Loaded {len(deduped)} cached deduped bookmarks ===", file=sys.stderr)

    # Step 4: Summarize
    print(f"\n=== Step 4: Summarize & Extract Claims ===", file=sys.stderr)
    if args.dry_run:
        print("  (dry run — no LLM calls)", file=sys.stderr)

    # Check for partial results from interrupted run
    existing_final = _load_json(FINAL_PATH)
    if existing_final and start_idx >= 3:
        already_done = {item["id"] for item in existing_final if "_llm_summary" in item
                        and not item["_llm_summary"].get("error")}
        remaining = [bm for bm in deduped if bm["id"] not in already_done]
        if remaining:
            print(f"  Resuming: {len(existing_final)} done, {len(remaining)} remaining", file=sys.stderr)
            new_results = summarize_bookmarks(remaining, dry_run=args.dry_run)
            final = existing_final + new_results
        else:
            print(f"  All {len(existing_final)} already summarized", file=sys.stderr)
            final = existing_final
    else:
        final = summarize_bookmarks(deduped, dry_run=args.dry_run)

    _save_json(final, FINAL_PATH)

    # Print summary
    print(f"\n=== Done ===", file=sys.stderr)
    print(f"  Total items: {len(final)}", file=sys.stderr)
    articles_count = sum(1 for f in final if f.get("extracted_articles"))
    print(f"  With articles: {articles_count}", file=sys.stderr)

    if not args.dry_run:
        summaries = [f for f in final if "_llm_summary" in f and not f["_llm_summary"].get("error")]
        if summaries:
            by_type = {}
            for s in summaries:
                ct = s["_llm_summary"].get("content_type", "unknown")
                by_type.setdefault(ct, []).append(s)
            print(f"  By content type:", file=sys.stderr)
            for ct, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
                print(f"    {ct}: {len(items)}", file=sys.stderr)

            # Sort by relevance for final output
            final.sort(key=lambda x: -(x.get("_llm_summary", {}).get("relevance", 0)))
            _save_json(final, FINAL_PATH)

    print(f"\n  Output: {FINAL_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
