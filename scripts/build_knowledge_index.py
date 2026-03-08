#!/usr/bin/env python3
"""Build the pre-computed knowledge index served to the Petrarca mobile app.

Loads articles + claim embeddings, computes pairwise similarities,
article-level novelty matrix, paragraph mappings, and optional LLM-generated
delta reports per topic.

Output: data/knowledge_index.json

Usage:
    python3 scripts/build_knowledge_index.py                # full build with delta reports
    python3 scripts/build_knowledge_index.py --skip-delta   # skip LLM calls
"""

import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH_NOMIC = DATA_DIR / "claim_embeddings_nomic.npz"
EMBEDDINGS_PATH_GEMINI = DATA_DIR / "claim_embeddings.npz"
OUTPUT_PATH = DATA_DIR / "knowledge_index.json"

# Thresholds validated by experiments
THRESHOLD_KNOWN = 0.78
THRESHOLD_EXTENDS = 0.68


def normalize_topic(topic: str) -> str:
    """Normalize a topic string: hyphens to spaces, lowercase, strip whitespace."""
    return re.sub(r"\s+", " ", topic.replace("-", " ")).strip().lower()

# Load env from .env file if present
for env_path in [PROJECT_DIR / ".env", Path("/opt/petrarca/.env")]:
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key, value = key.strip(), value.strip()
                    if key not in os.environ:
                        os.environ[key] = value


def log(msg: str):
    print(msg, file=sys.stderr)


def load_articles_and_claims() -> tuple[list[dict], list[dict], dict[str, int]]:
    """Load articles.json, extract all claims, and build claim-to-index mapping."""
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    for article in articles:
        article_id = article.get("id", "")
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claims.append({
                "id": claim["id"],
                "normalized_text": claim["normalized_text"],
                "original_text": claim.get("original_text", ""),
                "claim_type": claim.get("claim_type", "factual"),
                "source_paragraphs": claim.get("source_paragraphs", []),
                "topics": [normalize_topic(t) for t in claim.get("topics", [])],
                "article_id": article_id,
            })

    return articles, claims, claim_to_idx


def load_embeddings(expected_count: int) -> np.ndarray:
    """Load pre-computed embeddings and verify dimensions.

    Tries Nomic embeddings first (calibrated thresholds), falls back to Gemini.
    """
    embeddings_path = None
    if EMBEDDINGS_PATH_NOMIC.exists():
        embeddings_path = EMBEDDINGS_PATH_NOMIC
        log(f"  Using Nomic embeddings: {embeddings_path}")
    elif EMBEDDINGS_PATH_GEMINI.exists():
        embeddings_path = EMBEDDINGS_PATH_GEMINI
        log(f"  Using Gemini embeddings: {embeddings_path}")
    else:
        log(f"ERROR: No embeddings found. Expected {EMBEDDINGS_PATH_NOMIC} or {EMBEDDINGS_PATH_GEMINI}")
        log("Run build_claim_embeddings.py to generate embeddings.")
        sys.exit(1)

    data = np.load(embeddings_path)
    embeddings = data["embeddings"]

    if len(embeddings) != expected_count:
        log(f"ERROR: Embedding count ({len(embeddings)}) != claim count ({expected_count})")
        log("Re-run build_claim_embeddings.py to regenerate embeddings.")
        sys.exit(1)

    return embeddings


def compute_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity matrix (normalized dot product)."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    return normalized @ normalized.T


def extract_cross_article_pairs(similarity: np.ndarray, claims: list[dict],
                                threshold: float = 0.68) -> list[dict]:
    """Extract all cross-article pairs with similarity >= threshold."""
    n = len(claims)
    pairs = []

    # Build article_id lookup for fast same-article check
    article_ids = [c["article_id"] for c in claims]

    for i in range(n):
        for j in range(i + 1, n):
            if article_ids[i] == article_ids[j]:
                continue
            sim = float(similarity[i, j])
            if sim >= threshold:
                pairs.append({
                    "a": claims[i]["id"],
                    "b": claims[j]["id"],
                    "score": round(sim, 3),
                })

    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs


def build_article_claims_map(articles: list[dict], claims: list[dict]) -> dict[str, list[str]]:
    """Map article_id -> list of claim IDs."""
    result = {}
    for article in articles:
        aid = article.get("id", "")
        result[aid] = [c["id"] for c in claims if c["article_id"] == aid]
    return result


def build_paragraph_mapping(articles: list[dict], claims: list[dict]) -> dict[str, dict[int, list[str]]]:
    """For each article, map paragraph index -> claim IDs."""
    result = {}
    for article in articles:
        aid = article.get("id", "")
        article_claims = [c for c in claims if c["article_id"] == aid]
        para_map: dict[int, list[str]] = {}
        for claim in article_claims:
            for pi in claim.get("source_paragraphs", []):
                if pi not in para_map:
                    para_map[pi] = []
                para_map[pi].append(claim["id"])
        if para_map:
            # Convert int keys to str for JSON serialization
            result[aid] = {str(k): v for k, v in sorted(para_map.items())}
    return result


def compute_article_novelty_matrix(articles: list[dict], claims: list[dict],
                                   claim_to_idx: dict[str, int],
                                   similarity: np.ndarray) -> dict:
    """For every pair of articles (target, read), compute novelty breakdown.

    For each claim in the target article, find the max similarity to any claim
    in the read article and classify as NEW/EXTENDS/KNOWN.
    """
    # Pre-build article -> claim indices mapping
    article_claim_indices: dict[str, list[int]] = {}
    for article in articles:
        aid = article.get("id", "")
        indices = []
        for c in claims:
            if c["article_id"] == aid:
                idx = claim_to_idx.get(c["id"])
                if idx is not None:
                    indices.append(idx)
        article_claim_indices[aid] = indices

    matrix = {}
    article_ids = [a.get("id", "") for a in articles]

    for target_id in article_ids:
        target_indices = article_claim_indices.get(target_id, [])
        if not target_indices:
            continue

        target_entry = {}
        for read_id in article_ids:
            if read_id == target_id:
                continue
            read_indices = article_claim_indices.get(read_id, [])
            if not read_indices:
                continue

            # For each target claim, find max similarity to any read claim
            new_count = 0
            extends_count = 0
            known_count = 0

            # Vectorized: extract the sub-matrix for target x read
            target_arr = np.array(target_indices)
            read_arr = np.array(read_indices)
            sub_sim = similarity[np.ix_(target_arr, read_arr)]
            max_sims = sub_sim.max(axis=1)

            for max_sim in max_sims:
                if max_sim >= THRESHOLD_KNOWN:
                    known_count += 1
                elif max_sim >= THRESHOLD_EXTENDS:
                    extends_count += 1
                else:
                    new_count += 1

            # Only store if there's any overlap (extends or known)
            if known_count > 0 or extends_count > 0:
                target_entry[read_id] = {
                    "new": new_count,
                    "extends": extends_count,
                    "known": known_count,
                }

        if target_entry:
            matrix[target_id] = target_entry

    return matrix


def generate_delta_reports(claims: list[dict], min_claims: int = 5) -> dict:
    """Generate LLM-synthesized delta reports per topic (parallel)."""
    import litellm
    from concurrent.futures import ThreadPoolExecutor, as_completed

    gemini_key = os.environ.get("GEMINI_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        log("  No GEMINI_KEY found, skipping delta reports")
        return {}

    # Group claims by topic
    topic_claims: dict[str, list[dict]] = defaultdict(list)
    topic_articles: dict[str, set] = defaultdict(set)
    for claim in claims:
        for topic in claim.get("topics", []):
            topic_claims[topic].append(claim)
            topic_articles[topic].add(claim["article_id"])

    # Filter to topics with enough claims
    eligible = {t: cs for t, cs in topic_claims.items() if len(cs) >= min_claims}
    log(f"  {len(eligible)} topics with >= {min_claims} claims")

    def _synthesize_topic(topic: str, t_claims: list[dict], index: int) -> tuple[str, dict]:
        claim_texts = "\n".join(f"- {c['normalized_text']}" for c in t_claims[:50])
        prompt = (
            f"Synthesize these claims about '{topic}' into a 3-5 sentence summary "
            f"of what a reader would learn. Be specific and informative, not generic.\n\n"
            f"{claim_texts}"
        )

        try:
            response = litellm.completion(
                model="gemini/gemini-2.0-flash",
                messages=[{"role": "user", "content": prompt}],
                api_key=gemini_key,
                temperature=0.3,
                max_tokens=300,
            )
            try:
                from llm_audit import audit_llm_call
                audit_llm_call(response, script="build_knowledge_index.py", purpose="delta_report")
            except Exception:
                pass
            summary = response.choices[0].message.content.strip()
        except Exception as e:
            log(f"    LLM error for topic '{topic}': {e}")
            summary = ""

        top_claims = [
            {
                "text": c["normalized_text"],
                "article_id": c["article_id"],
                "claim_type": c["claim_type"],
            }
            for c in t_claims[:5]
        ]

        return topic, {
            "topic": topic,
            "summary": summary,
            "claim_count": len(t_claims),
            "article_count": len(topic_articles[topic]),
            "top_claims": top_claims,
        }

    reports = {}
    sorted_topics = sorted(eligible.items())
    completed = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_synthesize_topic, topic, t_claims, i): topic
            for i, (topic, t_claims) in enumerate(sorted_topics)
        }
        for future in as_completed(futures):
            completed += 1
            topic, report = future.result()
            reports[topic] = report
            if completed % 25 == 0 or completed == len(futures):
                log(f"  [{completed}/{len(futures)}] delta reports done")

    return reports


def main():
    parser = argparse.ArgumentParser(description="Build the Petrarca knowledge index")
    parser.add_argument("--skip-delta", action="store_true",
                        help="Skip LLM-generated delta reports")
    args = parser.parse_args()

    log("=== Building Petrarca Knowledge Index ===")
    log("")

    # 1. Load data
    log("Loading articles and claims...")
    articles, claims, claim_to_idx = load_articles_and_claims()
    log(f"  {len(articles)} articles, {len(claims)} claims")

    if not claims:
        log("ERROR: No claims found. Run build_articles.py --claims-only first.")
        sys.exit(1)

    log("Loading embeddings...")
    embeddings = load_embeddings(len(claims))
    log(f"  {embeddings.shape[0]} embeddings, {embeddings.shape[1]} dimensions")

    # 2. Compute similarities
    log("Computing similarity matrix...")
    similarity = compute_similarity_matrix(embeddings)

    log("Extracting cross-article similarity pairs (>= 0.68)...")
    pairs = extract_cross_article_pairs(similarity, claims)
    log(f"  {len(pairs)} cross-article pairs found")

    # 3. Build paragraph mapping
    log("Building paragraph mappings...")
    paragraph_map = build_paragraph_mapping(articles, claims)
    log(f"  {len(paragraph_map)} articles with paragraph mappings")

    # 4. Build claims dict
    log("Building claims index...")
    claims_dict = {}
    for c in claims:
        claims_dict[c["id"]] = {
            "text": c["normalized_text"],
            "article_id": c["article_id"],
            "claim_type": c["claim_type"],
            "source_paragraphs": c["source_paragraphs"],
            "topics": c["topics"],
        }

    # 5. Build article_claims map
    article_claims = build_article_claims_map(articles, claims)

    # 6. Compute article novelty matrix
    log("Computing article novelty matrix...")
    novelty_matrix = compute_article_novelty_matrix(
        articles, claims, claim_to_idx, similarity
    )
    total_entries = sum(len(v) for v in novelty_matrix.values())
    log(f"  {len(novelty_matrix)} target articles, {total_entries} pair entries")

    # 7. Generate delta reports (optional)
    delta_reports = {}
    if args.skip_delta:
        log("Skipping delta reports (--skip-delta)")
    else:
        log("Generating delta reports...")
        delta_reports = generate_delta_reports(claims)
        log(f"  {len(delta_reports)} delta reports generated")

    # Collect topic stats
    all_topics = set()
    for c in claims:
        all_topics.update(c.get("topics", []))

    # 8. Build and write output
    log("Building output...")
    output = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stats": {
            "total_articles": len(articles),
            "total_claims": len(claims),
            "total_similarity_pairs": len(pairs),
            "total_topics": len(all_topics),
            "delta_report_count": len(delta_reports),
        },
        "claims": claims_dict,
        "article_claims": article_claims,
        "paragraph_map": paragraph_map,
        "similarities": pairs,
        "article_novelty_matrix": novelty_matrix,
        "delta_reports": delta_reports,
    }

    log(f"Writing {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    file_size = OUTPUT_PATH.stat().st_size
    log(f"  {file_size:,} bytes ({file_size / 1024:.1f} KB)")

    # Human-readable summary to stdout
    print(f"\n{'='*60}")
    print(f"  Petrarca Knowledge Index")
    print(f"{'='*60}")
    print(f"  Generated: {output['generated_at']}")
    print(f"  Articles:  {output['stats']['total_articles']}")
    print(f"  Claims:    {output['stats']['total_claims']}")
    print(f"  Topics:    {output['stats']['total_topics']}")
    print(f"  Sim pairs: {output['stats']['total_similarity_pairs']} (>= 0.68)")
    print(f"  Delta rpts:{output['stats']['delta_report_count']}")
    print(f"  File size: {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    print()

    # Similarity distribution
    thresholds = [0.90, 0.85, 0.80, 0.78, 0.75, 0.68, 0.60, 0.50]
    print("  Similarity distribution (cross-article pairs):")
    for t in thresholds:
        count = sum(1 for p in pairs if p["score"] >= t)
        label = ""
        if t == THRESHOLD_KNOWN:
            label = " <- KNOWN threshold"
        elif t == THRESHOLD_EXTENDS:
            label = " <- EXTENDS threshold"
        print(f"    >= {t:.2f}: {count:>5} pairs{label}")
    print()

    # Novelty matrix summary
    if novelty_matrix:
        all_known = sum(
            entry.get("known", 0)
            for target in novelty_matrix.values()
            for entry in target.values()
        )
        all_extends = sum(
            entry.get("extends", 0)
            for target in novelty_matrix.values()
            for entry in target.values()
        )
        print(f"  Novelty matrix: {len(novelty_matrix)} articles have cross-article overlap")
        print(f"    Total KNOWN entries: {all_known}")
        print(f"    Total EXTENDS entries: {all_extends}")
        print()

    # Top topics
    topic_counts: dict[str, int] = defaultdict(int)
    for c in claims:
        for t in c.get("topics", []):
            topic_counts[t] += 1
    top = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    print("  Top topics:")
    for topic, count in top:
        delta = " [delta]" if topic in delta_reports else ""
        print(f"    {topic}: {count} claims{delta}")
    print()

    # Delta report summaries
    if delta_reports:
        print("  Delta reports:")
        for topic, report in sorted(delta_reports.items()):
            summary_preview = report["summary"][:80] + "..." if len(report["summary"]) > 80 else report["summary"]
            print(f"    {topic} ({report['claim_count']} claims, {report['article_count']} articles)")
            print(f"      {summary_preview}")
        print()

    log("Done.")


if __name__ == "__main__":
    main()
