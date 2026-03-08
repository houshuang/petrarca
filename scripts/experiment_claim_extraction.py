#!/usr/bin/env python3
"""Experiment 0: Atomic claim extraction on overlapping articles.

Validates core assumption of the novelty-aware reading system:
Can we extract atomic claims from articles and detect duplicates across them?

Uses the organized-crime / sicilian-mafia article cluster (12 articles)
for maximum overlap testing.

Usage:
    python3 scripts/experiment_claim_extraction.py
    python3 scripts/experiment_claim_extraction.py --limit 5    # only first N articles
    python3 scripts/experiment_claim_extraction.py --skip-llm   # reuse cached claims
"""

import argparse
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = APP_DATA_DIR / "articles.json"
OUTPUT_PATH = DATA_DIR / "experiment_claims.json"
ENV_PATH = PROJECT_DIR / ".env"

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file into os.environ."""
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

load_env()

# Bridge GEMINI_KEY -> GEMINI_API_KEY for litellm
if os.environ.get("GEMINI_KEY") and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GEMINI_KEY"]

LLM_MODEL = os.environ.get("PETRARCA_LLM_MODEL", "gemini/gemini-2.0-flash")

# ---------------------------------------------------------------------------
# LLM call (same pattern as build_articles.py)
# ---------------------------------------------------------------------------

def call_llm(prompt: str) -> str | None:
    """Call LLM via litellm."""
    try:
        from litellm import completion
        response = completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
        return None

# ---------------------------------------------------------------------------
# Article selection
# ---------------------------------------------------------------------------

TARGET_TOPICS = {"organized-crime", "sicilian-mafia"}

def load_mafia_articles(limit: int | None = None) -> list[dict]:
    """Load articles from the organized-crime / sicilian-mafia cluster."""
    with open(ARTICLES_PATH) as f:
        all_articles = json.load(f)

    matches = []
    for a in all_articles:
        topics = set(a.get("topics", []))
        if topics & TARGET_TOPICS:
            matches.append(a)

    # Sort by word count descending — process meatier articles first
    matches.sort(key=lambda a: a.get("word_count", 0), reverse=True)

    if limit:
        matches = matches[:limit]

    return matches

# ---------------------------------------------------------------------------
# Claim extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """Given this article, extract all knowledge contributions as atomic claims.

Each claim should be:
- MINIMAL: one single assertion (not compound sentences with "and")
- SELF-CONTAINED: understandable without the article context (resolve pronouns, add context)
- TYPED: classify as one of: factual, causal, comparative, procedural, evaluative, predictive, experiential

For each claim, provide:
- normalized_text: the claim rewritten in canonical, self-contained form
- claim_type: one of the types above
- source_paragraphs: which paragraph numbers (1-indexed) contain this claim
- topics: relevant topic tags (lowercase, hyphenated, e.g. "sicilian-mafia", "anti-mafia-movement")

Return valid JSON — an array of claim objects. No markdown fencing, no explanation, just the JSON array.

Example format:
[
  {{
    "normalized_text": "The Sicilian Mafia originated in the mid-19th century during the unification of Italy.",
    "claim_type": "factual",
    "source_paragraphs": [2, 3],
    "topics": ["sicilian-mafia", "italian-unification"]
  }}
]

Target 10-30 claims depending on article length. Focus on substantive knowledge claims, not trivial statements.

Article title: {title}

Article text:
{content}"""

# ---------------------------------------------------------------------------
# Extract claims from one article
# ---------------------------------------------------------------------------

def extract_claims(article: dict) -> list[dict] | None:
    """Send article to LLM and parse extracted claims."""
    title = article.get("title", "Untitled")
    content = article.get("content_markdown", "")

    if not content or len(content) < 100:
        print(f"  Skipping '{title}' — too short ({len(content)} chars)")
        return None

    # Truncate very long articles to ~8000 words to stay within context
    words = content.split()
    if len(words) > 8000:
        content = " ".join(words[:8000])
        print(f"  Truncated to 8000 words (was {len(words)})")

    prompt = EXTRACTION_PROMPT.format(title=title, content=content)

    print(f"  Calling LLM for '{title}' ({len(words)} words)...")
    t0 = time.time()
    raw = call_llm(prompt)
    elapsed = time.time() - t0
    print(f"  LLM responded in {elapsed:.1f}s")

    if not raw:
        return None

    # Parse JSON — strip markdown fencing if present
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        claims = json.loads(text)
        if isinstance(claims, list):
            return claims
        print(f"  Warning: expected list, got {type(claims)}")
        return None
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        print(f"  Raw response (first 500 chars): {text[:500]}")
        return None

# ---------------------------------------------------------------------------
# Deduplication analysis (text similarity)
# ---------------------------------------------------------------------------

def text_similarity(a: str, b: str) -> float:
    """Compute similarity between two claim texts using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def analyze_duplicates(results: list[dict], threshold: float = 0.6) -> dict:
    """Find potential duplicate claims across articles.

    Returns analysis dict with duplicate pairs and statistics.
    """
    # Collect all claims with their article info
    all_claims = []
    for r in results:
        article_id = r["article_id"]
        article_title = r["article_title"]
        for i, claim in enumerate(r["claims"]):
            all_claims.append({
                "article_id": article_id,
                "article_title": article_title,
                "claim_index": i,
                "text": claim["normalized_text"],
                "claim_type": claim.get("claim_type", "unknown"),
                "topics": claim.get("topics", []),
            })

    print(f"\nComparing {len(all_claims)} claims across {len(results)} articles...")

    # Compare all cross-article pairs
    duplicate_pairs = []
    high_similarity_pairs = []  # >= 0.8

    for i in range(len(all_claims)):
        for j in range(i + 1, len(all_claims)):
            # Skip same-article pairs
            if all_claims[i]["article_id"] == all_claims[j]["article_id"]:
                continue

            sim = text_similarity(all_claims[i]["text"], all_claims[j]["text"])

            if sim >= threshold:
                pair = {
                    "similarity": round(sim, 3),
                    "claim_a": {
                        "article": all_claims[i]["article_title"][:50],
                        "text": all_claims[i]["text"],
                    },
                    "claim_b": {
                        "article": all_claims[j]["article_title"][:50],
                        "text": all_claims[j]["text"],
                    },
                }
                duplicate_pairs.append(pair)

                if sim >= 0.8:
                    high_similarity_pairs.append(pair)

    # Sort by similarity descending
    duplicate_pairs.sort(key=lambda p: p["similarity"], reverse=True)
    high_similarity_pairs.sort(key=lambda p: p["similarity"], reverse=True)

    # Per-article stats
    article_stats = []
    for r in results:
        claim_texts = [c["normalized_text"] for c in r["claims"]]
        unique_to_article = 0
        shared_with_other = 0
        for ci, claim in enumerate(r["claims"]):
            found_dup = False
            for pair in duplicate_pairs:
                if (pair["claim_a"]["text"] == claim["normalized_text"] or
                    pair["claim_b"]["text"] == claim["normalized_text"]):
                    found_dup = True
                    break
            if found_dup:
                shared_with_other += 1
            else:
                unique_to_article += 1

        article_stats.append({
            "article_id": r["article_id"],
            "title": r["article_title"][:60],
            "total_claims": len(r["claims"]),
            "unique_claims": unique_to_article,
            "shared_claims": shared_with_other,
        })

    return {
        "total_claims": len(all_claims),
        "total_cross_article_pairs_checked": sum(
            1 for i in range(len(all_claims))
            for j in range(i + 1, len(all_claims))
            if all_claims[i]["article_id"] != all_claims[j]["article_id"]
        ),
        "duplicate_pairs_found": len(duplicate_pairs),
        "high_similarity_pairs": len(high_similarity_pairs),
        "threshold": threshold,
        "article_stats": article_stats,
        "top_duplicates": duplicate_pairs[:30],
    }

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(analysis: dict, results: list[dict]):
    """Print a human-readable summary report."""
    print("\n" + "=" * 72)
    print("EXPERIMENT 0: ATOMIC CLAIM EXTRACTION — RESULTS")
    print("=" * 72)

    print(f"\nArticles processed: {len(results)}")
    print(f"Total claims extracted: {analysis['total_claims']}")
    print(f"Cross-article pairs checked: {analysis['total_cross_article_pairs_checked']}")
    print(f"Potential duplicates (>={analysis['threshold']} similarity): {analysis['duplicate_pairs_found']}")
    print(f"High-confidence duplicates (>=0.8 similarity): {analysis['high_similarity_pairs']}")

    print("\n--- Claims per Article ---")
    for s in analysis["article_stats"]:
        bar = "█" * s["total_claims"]
        print(f"  {s['total_claims']:3d} claims ({s['unique_claims']:2d} unique, {s['shared_claims']:2d} shared)  {s['title']}")

    if analysis["top_duplicates"]:
        print(f"\n--- Top Duplicate Pairs (showing up to 15) ---")
        for pair in analysis["top_duplicates"][:15]:
            print(f"\n  Similarity: {pair['similarity']}")
            print(f"  A [{pair['claim_a']['article']}]:")
            print(f"    {pair['claim_a']['text']}")
            print(f"  B [{pair['claim_b']['article']}]:")
            print(f"    {pair['claim_b']['text']}")

    # Claim type distribution
    type_counts = {}
    for r in results:
        for c in r["claims"]:
            ct = c.get("claim_type", "unknown")
            type_counts[ct] = type_counts.get(ct, 0) + 1

    print("\n--- Claim Type Distribution ---")
    for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ct:15s}: {count}")

    # Topic distribution across claims
    topic_counts = {}
    for r in results:
        for c in r["claims"]:
            for t in c.get("topics", []):
                topic_counts[t] = topic_counts.get(t, 0) + 1

    print("\n--- Top Claim Topics ---")
    for t, count in sorted(topic_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"  {t:30s}: {count}")

    print("\n" + "=" * 72)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Experiment 0: Atomic claim extraction")
    parser.add_argument("--limit", type=int, help="Max articles to process")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip LLM calls, load from cached output")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="Similarity threshold for duplicate detection (default: 0.6)")
    args = parser.parse_args()

    # Load or extract claims
    if args.skip_llm and OUTPUT_PATH.exists():
        print(f"Loading cached claims from {OUTPUT_PATH}...")
        with open(OUTPUT_PATH) as f:
            data = json.load(f)
        results = data["results"]
        print(f"Loaded {len(results)} articles with claims.")
    else:
        articles = load_mafia_articles(limit=args.limit)
        print(f"Found {len(articles)} articles in the organized-crime / sicilian-mafia cluster")

        if not articles:
            print("No articles found! Check articles.json path.")
            sys.exit(1)

        for a in articles:
            print(f"  - {a['title'][:70]} ({a.get('word_count', '?')} words)")

        print(f"\nExtracting atomic claims using {LLM_MODEL}...\n")

        results = []
        for i, article in enumerate(articles):
            print(f"[{i+1}/{len(articles)}] Processing: {article['title'][:60]}")
            claims = extract_claims(article)
            if claims:
                results.append({
                    "article_id": article["id"],
                    "article_title": article["title"],
                    "word_count": article.get("word_count", 0),
                    "topics": article.get("topics", []),
                    "claims": claims,
                    "claim_count": len(claims),
                })
                print(f"  Extracted {len(claims)} claims")
            else:
                print(f"  FAILED to extract claims")

            # Brief pause between LLM calls
            if i < len(articles) - 1:
                time.sleep(1)

        # Save results
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        output = {
            "experiment": "atomic_claim_extraction_v0",
            "model": LLM_MODEL,
            "articles_processed": len(results),
            "total_claims": sum(r["claim_count"] for r in results),
            "results": results,
        }
        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nSaved claims to {OUTPUT_PATH}")

    # Run deduplication analysis
    analysis = analyze_duplicates(results, threshold=args.threshold)

    # Print report
    print_report(analysis, results)

    # Save analysis alongside claims
    analysis_path = DATA_DIR / "experiment_claims_analysis.json"
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\nAnalysis saved to {analysis_path}")


if __name__ == "__main__":
    main()
