#!/usr/bin/env python3
"""Experiment: Cross-article claim linking for "related reading".

Tests whether claim embeddings can automatically identify interesting
connections between articles — claims that extend, complement, or
contradict each other across different articles.

This could power:
1. "If you liked this claim, also read..." suggestions
2. Cross-article knowledge webs
3. "This article extends what you read in..." annotations

Usage:
    python3 scripts/experiment_cross_article_links.py
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"


def load_data():
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    article_claims = defaultdict(list)

    for article in articles:
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claim_data = {**claim, "article_id": article.get("id", ""),
                          "article_title": article.get("title", "")}
            claims.append(claim_data)
            article_claims[article.get("id", "")].append(idx)

    data = np.load(DATA_DIR / "claim_embeddings_nomic.npz")
    embeddings = data["embeddings"]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    similarity = (embeddings / norms) @ (embeddings / norms).T

    return articles, claims, claim_to_idx, article_claims, similarity


def find_cross_article_links(claims, article_claims, similarity,
                              min_sim=0.68, max_sim=0.90):
    """Find meaningful cross-article claim connections."""
    links = []
    seen = set()

    for article_a, claim_indices_a in article_claims.items():
        for article_b, claim_indices_b in article_claims.items():
            if article_a >= article_b:  # Skip self and duplicates
                continue

            # Find best matching claims between these articles
            best_pairs = []
            for i in claim_indices_a:
                for j in claim_indices_b:
                    sim = float(similarity[i, j])
                    if min_sim <= sim <= max_sim:
                        pair_key = (min(i, j), max(i, j))
                        if pair_key not in seen:
                            seen.add(pair_key)
                            best_pairs.append((i, j, sim))

            best_pairs.sort(key=lambda x: -x[2])

            for i, j, sim in best_pairs[:5]:  # Top 5 per article pair
                relationship = "EXTENDS" if sim >= 0.78 else "RELATED"
                links.append({
                    "claim_a": {
                        "text": claims[i]["normalized_text"],
                        "type": claims[i]["claim_type"],
                        "article": claims[i]["article_title"][:50],
                        "article_id": claims[i]["article_id"],
                    },
                    "claim_b": {
                        "text": claims[j]["normalized_text"],
                        "type": claims[j]["claim_type"],
                        "article": claims[j]["article_title"][:50],
                        "article_id": claims[j]["article_id"],
                    },
                    "similarity": round(sim, 4),
                    "relationship": relationship,
                })

    links.sort(key=lambda x: -x["similarity"])
    return links


def compute_article_similarity(article_claims, claims, similarity):
    """Compute article-level similarity based on claim overlap."""
    articles = list(article_claims.keys())
    n = len(articles)
    article_sim = {}

    for i in range(n):
        for j in range(i + 1, n):
            a_indices = article_claims[articles[i]]
            b_indices = article_claims[articles[j]]

            if not a_indices or not b_indices:
                continue

            # Average best-match similarity
            best_matches_a = []
            for ai in a_indices:
                best = max(float(similarity[ai, bj]) for bj in b_indices)
                best_matches_a.append(best)

            best_matches_b = []
            for bj in b_indices:
                best = max(float(similarity[bj, ai]) for ai in a_indices)
                best_matches_b.append(best)

            # Symmetric: average of best matches from both directions
            avg_sim = (np.mean(best_matches_a) + np.mean(best_matches_b)) / 2

            # Also count high-similarity pairs
            high_pairs = sum(1 for ai in a_indices for bj in b_indices
                            if float(similarity[ai, bj]) >= 0.68)

            article_a_title = claims[a_indices[0]]["article_title"][:50]
            article_b_title = claims[b_indices[0]]["article_title"][:50]

            article_sim[(articles[i], articles[j])] = {
                "article_a": article_a_title,
                "article_b": article_b_title,
                "avg_similarity": round(float(avg_sim), 4),
                "high_pairs": high_pairs,
                "claims_a": len(a_indices),
                "claims_b": len(b_indices),
            }

    return article_sim


def build_reading_graph(article_sim, min_pairs=3):
    """Build a graph of connected articles for "related reading"."""
    graph = defaultdict(list)

    for (a, b), info in article_sim.items():
        if info["high_pairs"] >= min_pairs:
            graph[info["article_a"]].append({
                "article": info["article_b"],
                "shared_claims": info["high_pairs"],
                "similarity": info["avg_similarity"],
            })
            graph[info["article_b"]].append({
                "article": info["article_a"],
                "shared_claims": info["high_pairs"],
                "similarity": info["avg_similarity"],
            })

    # Sort connections by shared claims
    for k in graph:
        graph[k].sort(key=lambda x: -x["shared_claims"])

    return dict(graph)


def find_learning_paths(graph, start_article):
    """Find suggested reading paths from a starting article."""
    visited = {start_article}
    path = [start_article]
    current = start_article

    for _ in range(5):  # Max path length
        connections = graph.get(current, [])
        unvisited = [c for c in connections if c["article"] not in visited]
        if not unvisited:
            break
        next_article = unvisited[0]  # Best connection
        path.append(next_article["article"])
        visited.add(next_article["article"])
        current = next_article["article"]

    return path


def main():
    print("Loading data...", file=sys.stderr)
    articles, claims, claim_to_idx, article_claims, similarity = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    # Find cross-article links
    print("\nFinding cross-article claim links...", file=sys.stderr)
    links = find_cross_article_links(claims, article_claims, similarity)
    print(f"  Found {len(links)} cross-article links", file=sys.stderr)

    print(f"\n{'='*70}")
    print(f"  TOP CROSS-ARTICLE CONNECTIONS")
    print(f"{'='*70}")

    for link in links[:20]:
        print(f"\n  [{link['similarity']:.3f}] {link['relationship']}")
        print(f"    A: {link['claim_a']['text'][:70]}")
        print(f"       — {link['claim_a']['article']}")
        print(f"    B: {link['claim_b']['text'][:70]}")
        print(f"       — {link['claim_b']['article']}")

    # Article-level similarity
    print(f"\n{'='*70}")
    print(f"  ARTICLE-LEVEL SIMILARITY")
    print(f"{'='*70}")

    article_sim = compute_article_similarity(article_claims, claims, similarity)
    top_pairs = sorted(article_sim.values(), key=lambda x: -x["high_pairs"])[:15]

    print(f"\n  {'Pairs':>5} {'AvgSim':>7} {'Article A':<35} {'Article B'}")
    print(f"  {'─'*5} {'─'*7} {'─'*35} {'─'*35}")
    for pair in top_pairs:
        print(f"  {pair['high_pairs']:>5} {pair['avg_similarity']:>7.3f} "
              f"{pair['article_a'][:35]:<35} {pair['article_b'][:35]}")

    # Reading graph
    print(f"\n{'='*70}")
    print(f"  READING GRAPH (articles connected by 3+ shared claims)")
    print(f"{'='*70}")

    graph = build_reading_graph(article_sim, min_pairs=3)
    for article, connections in sorted(graph.items(), key=lambda x: -len(x[1])):
        if len(connections) < 2:
            continue
        print(f"\n  {article}")
        for conn in connections[:5]:
            print(f"    ├─ {conn['article']} ({conn['shared_claims']} shared, "
                  f"sim={conn['similarity']:.3f})")

    # Learning paths
    print(f"\n{'='*70}")
    print(f"  SUGGESTED LEARNING PATHS")
    print(f"{'='*70}")

    # Find articles with most connections
    hub_articles = sorted(graph.items(), key=lambda x: -len(x[1]))[:3]
    for hub, _ in hub_articles:
        path = find_learning_paths(graph, hub)
        print(f"\n  Starting from: {hub}")
        for i, article in enumerate(path):
            prefix = "  → " if i > 0 else "  ● "
            print(f"    {prefix}{article}")

    # Save results
    output = {
        "total_links": len(links),
        "top_links": links[:50],
        "article_similarity": [
            {**v, "article_a_id": k[0], "article_b_id": k[1]}
            for k, v in sorted(article_sim.items(), key=lambda x: -x[1]["high_pairs"])[:30]
        ],
        "reading_graph": graph,
        "learning_paths": [
            {"start": hub, "path": find_learning_paths(graph, hub)}
            for hub, _ in hub_articles
        ],
    }
    output_path = DATA_DIR / "experiment_cross_article_links.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
