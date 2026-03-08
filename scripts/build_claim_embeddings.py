#!/usr/bin/env python3
"""Build embeddings for all atomic claims and compute similarity matrix.

Usage:
    python3 scripts/build_claim_embeddings.py              # embed all claims
    python3 scripts/build_claim_embeddings.py --analyze     # embed + run analysis
    python3 scripts/build_claim_embeddings.py --skip-embed  # analysis only (if embeddings exist)
"""

import json
import os
import sys
import time
import argparse
import hashlib
from pathlib import Path

import numpy as np

# Setup
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH = DATA_DIR / "claim_embeddings.npz"
CLAIMS_INDEX_PATH = DATA_DIR / "claims_index.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY", "")
EMBEDDING_MODEL = "models/gemini-embedding-001"
BATCH_SIZE = 100  # Gemini supports up to 100 per batch


def load_all_claims(articles_path: Path) -> tuple[list[dict], list[dict]]:
    """Load articles and extract all claims with article references."""
    with open(articles_path) as f:
        articles = json.load(f)

    claims = []
    for article in articles:
        article_id = article.get("id", "")
        article_title = article.get("title", "Untitled")
        for claim in article.get("atomic_claims", []):
            claims.append({
                "id": claim["id"],
                "normalized_text": claim["normalized_text"],
                "original_text": claim.get("original_text", ""),
                "claim_type": claim.get("claim_type", "factual"),
                "topics": claim.get("topics", []),
                "source_paragraphs": claim.get("source_paragraphs", []),
                "article_id": article_id,
                "article_title": article_title,
            })

    return articles, claims


def embed_claims(claims: list[dict], batch_size: int = BATCH_SIZE) -> np.ndarray:
    """Embed all claims using Gemini embedding API. Returns numpy array of shape (n, dim)."""
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)

    texts = [c["normalized_text"] for c in claims]
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1} "
              f"({len(batch)} claims)...", file=sys.stderr)

        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=batch,
        )
        all_embeddings.extend(result["embedding"])
        time.sleep(0.5)  # rate limiting

    return np.array(all_embeddings, dtype=np.float32)


def compute_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute cosine similarity matrix between all embeddings."""
    # Normalize embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1  # avoid division by zero
    normalized = embeddings / norms

    # Cosine similarity = dot product of normalized vectors
    similarity = normalized @ normalized.T
    return similarity


def find_similar_pairs(similarity: np.ndarray, claims: list[dict],
                       threshold: float = 0.85) -> list[dict]:
    """Find pairs of claims with cosine similarity above threshold."""
    n = len(claims)
    pairs = []

    for i in range(n):
        for j in range(i + 1, n):
            sim = float(similarity[i, j])
            if sim >= threshold:
                # Skip same-article pairs (expected to be similar)
                if claims[i]["article_id"] == claims[j]["article_id"]:
                    continue
                pairs.append({
                    "claim_a": {
                        "id": claims[i]["id"],
                        "text": claims[i]["normalized_text"],
                        "article": claims[i]["article_title"][:50],
                        "type": claims[i]["claim_type"],
                    },
                    "claim_b": {
                        "id": claims[j]["id"],
                        "text": claims[j]["normalized_text"],
                        "article": claims[j]["article_title"][:50],
                        "type": claims[j]["claim_type"],
                    },
                    "similarity": round(sim, 4),
                })

    pairs.sort(key=lambda p: p["similarity"], reverse=True)
    return pairs


def find_topic_clusters(claims: list[dict]) -> dict[str, list[int]]:
    """Group claims by topic, returning topic -> list of claim indices."""
    topic_map: dict[str, list[int]] = {}
    for i, claim in enumerate(claims):
        for topic in claim.get("topics", []):
            if topic not in topic_map:
                topic_map[topic] = []
            topic_map[topic].append(i)
    return topic_map


def analyze_results(claims: list[dict], embeddings: np.ndarray,
                    similarity: np.ndarray) -> dict:
    """Run comprehensive analysis on the embedded claims."""
    n = len(claims)

    # Basic stats
    stats = {
        "total_claims": n,
        "embedding_dimensions": int(embeddings.shape[1]),
        "articles_count": len(set(c["article_id"] for c in claims)),
    }

    # Type distribution
    type_dist: dict[str, int] = {}
    for c in claims:
        ct = c["claim_type"]
        type_dist[ct] = type_dist.get(ct, 0) + 1
    stats["type_distribution"] = type_dist

    # Topic analysis
    topic_clusters = find_topic_clusters(claims)
    stats["unique_topics"] = len(topic_clusters)
    stats["top_topics"] = sorted(
        [(t, len(idxs)) for t, idxs in topic_clusters.items()],
        key=lambda x: x[1], reverse=True
    )[:20]

    # Similarity analysis at different thresholds
    for threshold in [0.95, 0.90, 0.85, 0.80, 0.75]:
        pairs = find_similar_pairs(similarity, claims, threshold)
        stats[f"similar_pairs_above_{threshold}"] = len(pairs)

    # Near-duplicate pairs (>= 0.90)
    near_dupes = find_similar_pairs(similarity, claims, 0.90)
    stats["near_duplicate_pairs"] = near_dupes[:20]

    # High-similarity cross-article pairs (0.80-0.90) — potential EXTENDS relationships
    extends_candidates = find_similar_pairs(similarity, claims, 0.80)
    extends_candidates = [p for p in extends_candidates if p["similarity"] < 0.90]
    stats["extends_candidates"] = extends_candidates[:20]

    return stats


def simulate_reading_journey(claims: list[dict], articles: list[dict],
                             similarity: np.ndarray) -> dict:
    """Simulate a user reading articles and track knowledge state."""
    # Knowledge ledger: claim_id -> status
    ledger: dict[str, str] = {}  # "unknown" | "encountered" | "absorbed"

    # Pick a reading order: read first 5 articles
    read_order = articles[:5]
    journey = {
        "articles_read": [],
        "knowledge_growth": [],
    }

    for article in read_order:
        article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]
        new_claims = 0
        known_claims = 0

        for claim in article_claims:
            claim_idx = next((i for i, c in enumerate(claims) if c["id"] == claim["id"]), None)
            if claim_idx is None:
                continue

            # Check if similar to any already-known claim
            is_familiar = False
            for known_id, status in ledger.items():
                if status in ("encountered", "absorbed"):
                    known_idx = next((i for i, c in enumerate(claims) if c["id"] == known_id), None)
                    if known_idx is not None:
                        sim = float(similarity[claim_idx, known_idx])
                        if sim >= 0.72:
                            is_familiar = True
                            break

            if is_familiar:
                known_claims += 1
                ledger[claim["id"]] = "encountered"  # already known via similar claim
            else:
                new_claims += 1
                ledger[claim["id"]] = "encountered"

        total = new_claims + known_claims
        novelty_pct = (new_claims / total * 100) if total > 0 else 0

        journey["articles_read"].append({
            "title": article.get("title", "")[:60],
            "total_claims": total,
            "new_claims": new_claims,
            "familiar_claims": known_claims,
            "novelty_pct": round(novelty_pct, 1),
        })
        journey["knowledge_growth"].append(len(ledger))

    return journey


def generate_delta_report(claims: list[dict], topic: str,
                          known_claim_ids: set[str],
                          similarity: np.ndarray) -> dict:
    """Generate a delta report for a topic given known claims."""
    # Get all claims in this topic
    topic_claims = [c for c in claims if topic in c.get("topics", [])]
    if not topic_claims:
        return {"topic": topic, "error": "no claims for topic"}

    new_claims = []
    known_claims = []
    extends_claims = []

    for claim in topic_claims:
        claim_idx = next((i for i, c in enumerate(claims) if c["id"] == claim["id"]), None)
        if claim_idx is None:
            continue

        if claim["id"] in known_claim_ids:
            known_claims.append(claim)
            continue

        # Check similarity to known claims
        max_sim = 0.0
        most_similar_known = None
        for kid in known_claim_ids:
            kidx = next((i for i, c in enumerate(claims) if c["id"] == kid), None)
            if kidx is not None:
                sim = float(similarity[claim_idx, kidx])
                if sim > max_sim:
                    max_sim = sim
                    most_similar_known = kid

        if max_sim >= 0.72:
            extends_claims.append({
                **claim,
                "similarity_to_known": round(max_sim, 3),
                "similar_to": most_similar_known,
            })
        elif max_sim >= 0.62:
            extends_claims.append({
                **claim,
                "similarity_to_known": round(max_sim, 3),
                "similar_to": most_similar_known,
                "relationship": "EXTENDS",
            })
        else:
            new_claims.append(claim)

    return {
        "topic": topic,
        "total_claims": len(topic_claims),
        "new": [{"text": c["normalized_text"], "article": c["article_title"][:50],
                 "type": c["claim_type"]} for c in new_claims],
        "extends": [{"text": c["normalized_text"], "article": c["article_title"][:50],
                     "similarity": c.get("similarity_to_known", 0)}
                    for c in extends_claims],
        "known": len(known_claims),
    }


def main():
    parser = argparse.ArgumentParser(description="Build claim embeddings and analyze")
    parser.add_argument("--analyze", action="store_true", help="Run full analysis")
    parser.add_argument("--skip-embed", action="store_true", help="Skip embedding, use cached")
    parser.add_argument("--journey", action="store_true", help="Simulate reading journey")
    parser.add_argument("--delta", type=str, help="Generate delta report for topic")
    args = parser.parse_args()

    if not GEMINI_API_KEY and not args.skip_embed:
        print("Error: GEMINI_KEY or GEMINI_API_KEY required", file=sys.stderr)
        sys.exit(1)

    # Load claims
    print("Loading articles and claims...", file=sys.stderr)
    articles, claims = load_all_claims(ARTICLES_PATH)
    print(f"  {len(claims)} claims from {len(articles)} articles", file=sys.stderr)

    if not claims:
        print("No claims found. Run --claims-only first.", file=sys.stderr)
        sys.exit(1)

    # Embed (or load cached)
    if args.skip_embed and EMBEDDINGS_PATH.exists():
        print("Loading cached embeddings...", file=sys.stderr)
        data = np.load(EMBEDDINGS_PATH)
        embeddings = data["embeddings"]
        # Verify dimensions match
        if len(embeddings) != len(claims):
            print(f"  Warning: cached embeddings ({len(embeddings)}) != claims ({len(claims)}). Re-embedding.", file=sys.stderr)
            embeddings = embed_claims(claims)
            np.savez_compressed(EMBEDDINGS_PATH, embeddings=embeddings)
    else:
        print("Embedding claims...", file=sys.stderr)
        embeddings = embed_claims(claims)
        np.savez_compressed(EMBEDDINGS_PATH, embeddings=embeddings)
        print(f"  Saved {EMBEDDINGS_PATH} ({embeddings.shape})", file=sys.stderr)

    # Save claims index for cross-referencing
    index = [{"id": c["id"], "text": c["normalized_text"][:100],
              "article_id": c["article_id"], "topics": c["topics"]}
             for c in claims]
    with open(CLAIMS_INDEX_PATH, "w") as f:
        json.dump(index, f, indent=2)

    # Compute similarity
    print("Computing similarity matrix...", file=sys.stderr)
    similarity = compute_similarity_matrix(embeddings)

    if args.analyze or (not args.journey and not args.delta):
        print("\n=== Claim Embedding Analysis ===\n", file=sys.stderr)
        results = analyze_results(claims, embeddings, similarity)

        print(f"Total claims: {results['total_claims']}")
        print(f"Embedding dimensions: {results['embedding_dimensions']}")
        print(f"Articles: {results['articles_count']}")
        print(f"\nType distribution:")
        for ct, count in sorted(results['type_distribution'].items()):
            print(f"  {ct}: {count}")

        print(f"\nUnique topics: {results['unique_topics']}")
        print(f"Top topics:")
        for topic, count in results['top_topics']:
            print(f"  {topic}: {count} claims")

        print(f"\nSimilarity analysis (cross-article pairs):")
        for threshold in [0.95, 0.90, 0.85, 0.80, 0.75]:
            count = results[f"similar_pairs_above_{threshold}"]
            print(f"  >= {threshold}: {count} pairs")

        if results["near_duplicate_pairs"]:
            print(f"\nNear-duplicate pairs (>= 0.90):")
            for p in results["near_duplicate_pairs"][:10]:
                print(f"  [{p['similarity']:.3f}] {p['claim_a']['text'][:60]}")
                print(f"         ↔ {p['claim_b']['text'][:60]}")
                print(f"         ({p['claim_a']['article']} ↔ {p['claim_b']['article']})")
                print()

        if results["extends_candidates"]:
            print(f"\nExtends candidates (0.80-0.90):")
            for p in results["extends_candidates"][:10]:
                print(f"  [{p['similarity']:.3f}] {p['claim_a']['text'][:60]}")
                print(f"         ↔ {p['claim_b']['text'][:60]}")
                print()

        # Save full results
        analysis_path = DATA_DIR / "claim_analysis.json"
        with open(analysis_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nFull analysis saved to {analysis_path}", file=sys.stderr)

    if args.journey:
        print("\n=== Reading Journey Simulation ===\n")
        journey = simulate_reading_journey(claims, articles, similarity)
        for step in journey["articles_read"]:
            pct = step["novelty_pct"]
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"  {step['title'][:50]}")
            print(f"    {bar} {pct}% new ({step['new_claims']} new, {step['familiar_claims']} familiar)")
        print(f"\n  Knowledge growth: {' → '.join(str(g) for g in journey['knowledge_growth'])}")

        journey_path = DATA_DIR / "reading_journey.json"
        with open(journey_path, "w") as f:
            json.dump(journey, f, indent=2)

    if args.delta:
        print(f"\n=== Delta Report: {args.delta} ===\n")
        # Simulate: user has read first 3 articles
        known_ids = set()
        for article in articles[:3]:
            for claim in article.get("atomic_claims", []):
                known_ids.add(claim["id"])

        report = generate_delta_report(claims, args.delta, known_ids, similarity)
        print(f"Topic: {report['topic']}")
        print(f"Total claims: {report['total_claims']}")
        print(f"Known: {report['known']}")
        print(f"\nNew ({len(report['new'])}):")
        for c in report["new"][:10]:
            print(f"  [{c['type']}] {c['text'][:80]}")
            print(f"           — {c['article']}")
        print(f"\nExtends ({len(report['extends'])}):")
        for c in report["extends"][:10]:
            print(f"  [{c['similarity']:.2f}] {c['text'][:80]}")


if __name__ == "__main__":
    main()
