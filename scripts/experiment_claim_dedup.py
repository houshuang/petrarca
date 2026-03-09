#!/usr/bin/env python3
"""Experiment: Claim deduplication via embedding similarity.

Finds duplicate and near-duplicate claims across the entire corpus using
Nomic embeddings and cosine similarity. Uses union-find to cluster
duplicates, picks canonical representatives, and reports statistics.

Thresholds:
  - KNOWN (>= 0.78): considered duplicate, clustered together
  - NEAR  (0.72-0.78): near-duplicates, candidates for manual review/merge

Usage:
    python3 scripts/experiment_claim_dedup.py
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
EMBEDDINGS_PATH = DATA_DIR / "claim_embeddings_nomic.npz"

KNOWN_THRESHOLD = 0.78
NEAR_THRESHOLD = 0.72


def load_data():
    """Load articles, claims, and precomputed embeddings."""
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    # Build article lookup
    article_lookup = {}
    for i, article in enumerate(articles):
        article_lookup[article.get("id", "")] = {
            "title": article.get("title", ""),
            "date": article.get("date", ""),
            "order": i,
        }

    # Build flat claims list (same order as embeddings)
    claims = []
    for article in articles:
        article_id = article.get("id", "")
        article_title = article.get("title", "")
        article_date = article.get("date", "")
        article_order = article_lookup[article_id]["order"]
        for claim in article.get("atomic_claims", []):
            claims.append({
                **claim,
                "article_id": article_id,
                "article_title": article_title,
                "article_date": article_date,
                "article_order": article_order,
            })

    # Load embeddings and compute normalized versions
    data = np.load(EMBEDDINGS_PATH)
    embeddings = data["embeddings"]
    assert len(claims) == embeddings.shape[0], \
        f"Mismatch: {len(claims)} claims vs {embeddings.shape[0]} embeddings"

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = embeddings / norms

    return articles, claims, normed, article_lookup


class UnionFind:
    """Union-Find data structure for clustering."""

    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


def build_similarity_graph(normed, threshold):
    """Find all pairs above threshold using matrix multiplication."""
    similarity = normed @ normed.T
    # Zero out diagonal (self-similarity)
    np.fill_diagonal(similarity, 0)
    return similarity


def cluster_duplicates(claims, similarity, threshold):
    """Cluster claims using complete-linkage: ALL pairs in a cluster must be above threshold.

    Single-linkage (union-find) creates runaway transitive chains. Complete-linkage
    ensures every member of a cluster is genuinely similar to every other member.
    """
    n = len(claims)

    # Build adjacency list of pairs above threshold
    pairs = []
    adj = defaultdict(set)
    rows, cols = np.where(similarity >= threshold)
    for r, c in zip(rows, cols):
        if r < c:
            adj[int(r)].add(int(c))
            adj[int(c)].add(int(r))
            pairs.append((int(r), int(c), float(similarity[r, c])))

    # Greedy complete-linkage: grow clusters where all members are pairwise above threshold
    assigned = set()
    clusters = []

    # Sort nodes by degree (most connections first) for better clusters
    nodes_by_degree = sorted(adj.keys(), key=lambda x: -len(adj[x]))

    for seed in nodes_by_degree:
        if seed in assigned:
            continue

        # Start cluster with seed
        cluster = {seed}
        candidates = adj[seed] - assigned

        # Try adding each candidate — must be above threshold with ALL current members
        for candidate in sorted(candidates, key=lambda c: -float(similarity[seed, c])):
            if candidate in assigned:
                continue
            # Check complete linkage: candidate must be similar to ALL cluster members
            if all(float(similarity[candidate, m]) >= threshold for m in cluster):
                cluster.add(candidate)

        if len(cluster) >= 2:
            clusters.append(sorted(cluster))
            assigned.update(cluster)

    clusters.sort(key=lambda x: -len(x))
    return clusters, pairs


def pick_canonical(cluster_indices, claims):
    """Pick canonical claim: prefer longest text, break ties by earliest article."""
    best = None
    best_score = (-1, float("inf"))
    for idx in cluster_indices:
        claim = claims[idx]
        text_len = len(claim.get("normalized_text", ""))
        article_order = claim["article_order"]
        score = (text_len, -article_order)  # Longest text, then earliest article
        if score > best_score:
            best_score = score
            best = idx
    return best


def find_near_duplicates(claims, similarity, low, high):
    """Find pairs in the near-duplicate range (not already in a cluster)."""
    near_pairs = []
    rows, cols = np.where((similarity >= low) & (similarity < high))
    for r, c in zip(rows, cols):
        if r < c:
            near_pairs.append({
                "idx_a": int(r),
                "idx_b": int(c),
                "similarity": round(float(similarity[r, c]), 4),
                "text_a": claims[r]["normalized_text"],
                "text_b": claims[c]["normalized_text"],
                "article_a": claims[r]["article_title"][:50],
                "article_b": claims[c]["article_title"][:50],
                "same_article": claims[r]["article_id"] == claims[c]["article_id"],
            })
    near_pairs.sort(key=lambda x: -x["similarity"])
    return near_pairs


def format_cluster(cluster_indices, claims, similarity, canonical_idx):
    """Format a cluster for display and JSON output."""
    members = []
    for idx in cluster_indices:
        claim = claims[idx]
        members.append({
            "idx": int(idx),
            "claim_id": claim["id"],
            "text": claim["normalized_text"],
            "claim_type": claim.get("claim_type", ""),
            "topics": claim.get("topics", []),
            "article_title": claim["article_title"][:60],
            "article_id": claim["article_id"],
            "is_canonical": idx == canonical_idx,
        })

    # Compute pairwise similarities within cluster
    pair_sims = []
    for i, a in enumerate(cluster_indices):
        for b in cluster_indices[i + 1:]:
            pair_sims.append(float(similarity[a, b]))

    # Count unique articles
    unique_articles = len(set(claims[i]["article_id"] for i in cluster_indices))

    return {
        "size": len(cluster_indices),
        "unique_articles": unique_articles,
        "canonical_idx": int(canonical_idx),
        "canonical_text": claims[canonical_idx]["normalized_text"],
        "avg_internal_similarity": round(np.mean(pair_sims), 4) if pair_sims else 1.0,
        "min_internal_similarity": round(min(pair_sims), 4) if pair_sims else 1.0,
        "members": members,
    }


def print_report(claims, clusters, cluster_data, near_pairs, similarity):
    """Print a formatted terminal report."""
    total_claims = len(claims)
    total_in_clusters = sum(c["size"] for c in cluster_data)
    unique_after_dedup = total_claims - total_in_clusters + len(cluster_data)

    # Cluster size distribution
    size_counts = defaultdict(int)
    for c in cluster_data:
        size_counts[c["size"]] += 1

    # Cross-article vs intra-article clusters
    cross_article = sum(1 for c in cluster_data if c["unique_articles"] > 1)
    intra_article = len(cluster_data) - cross_article

    print(f"\n{'=' * 70}")
    print(f"  CLAIM DEDUPLICATION REPORT")
    print(f"{'=' * 70}")

    print(f"\n  OVERVIEW")
    print(f"  {'─' * 40}")
    print(f"  Total claims:              {total_claims}")
    print(f"  Claims in dup clusters:    {total_in_clusters}")
    print(f"  Duplicate clusters:        {len(cluster_data)}")
    print(f"  Unique after dedup:        {unique_after_dedup} "
          f"({100 * unique_after_dedup / total_claims:.1f}%)")
    print(f"  Reduction:                 {total_claims - unique_after_dedup} claims "
          f"({100 * (total_claims - unique_after_dedup) / total_claims:.1f}%)")

    print(f"\n  CLUSTER SIZE DISTRIBUTION")
    print(f"  {'─' * 40}")
    for size in sorted(size_counts.keys()):
        bar = "█" * size_counts[size]
        print(f"  Size {size:>2}: {size_counts[size]:>3} clusters  {bar}")

    print(f"\n  CLUSTER TYPES")
    print(f"  {'─' * 40}")
    print(f"  Cross-article clusters:    {cross_article}")
    print(f"  Intra-article clusters:    {intra_article}")

    print(f"\n{'=' * 70}")
    print(f"  TOP 10 LARGEST DUPLICATE CLUSTERS")
    print(f"{'=' * 70}")

    for i, cluster in enumerate(cluster_data[:10]):
        print(f"\n  Cluster {i + 1} — {cluster['size']} claims, "
              f"{cluster['unique_articles']} article(s), "
              f"avg sim={cluster['avg_internal_similarity']:.3f}")
        print(f"  Canonical: {cluster['canonical_text'][:90]}")
        print(f"  {'─' * 60}")
        for m in cluster["members"]:
            marker = " ★" if m["is_canonical"] else "  "
            print(f"  {marker} [{m['claim_type'][:4]:>4}] {m['text'][:75]}")
            print(f"          — {m['article_title']}")

    print(f"\n{'=' * 70}")
    print(f"  NEAR-DUPLICATES (sim {NEAR_THRESHOLD:.2f}–{KNOWN_THRESHOLD:.2f})")
    print(f"{'=' * 70}")

    cross_near = [p for p in near_pairs if not p["same_article"]]
    intra_near = [p for p in near_pairs if p["same_article"]]
    print(f"\n  Total near-duplicate pairs: {len(near_pairs)}")
    print(f"  Cross-article:             {len(cross_near)}")
    print(f"  Intra-article:             {len(intra_near)}")

    print(f"\n  Top 15 near-duplicate pairs:")
    for p in near_pairs[:15]:
        cross = "CROSS" if not p["same_article"] else "INTRA"
        print(f"\n  [{p['similarity']:.3f}] {cross}")
        print(f"    A: {p['text_a'][:80]}")
        print(f"       — {p['article_a']}")
        print(f"    B: {p['text_b'][:80]}")
        print(f"       — {p['article_b']}")

    # Claim type breakdown in clusters
    type_counts = defaultdict(int)
    for c in cluster_data:
        for m in c["members"]:
            type_counts[m["claim_type"]] += 1

    print(f"\n{'=' * 70}")
    print(f"  CLAIM TYPES IN DUPLICATE CLUSTERS")
    print(f"{'=' * 70}")
    for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ct:<20} {count:>4}")


def main():
    print("Loading data...", file=sys.stderr)
    articles, claims, normed, article_lookup = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    print("Computing full similarity matrix...", file=sys.stderr)
    similarity = build_similarity_graph(normed, KNOWN_THRESHOLD)

    print(f"Clustering duplicates (threshold={KNOWN_THRESHOLD})...", file=sys.stderr)
    clusters, dup_pairs = cluster_duplicates(claims, similarity, KNOWN_THRESHOLD)
    print(f"  {len(clusters)} clusters from {len(dup_pairs)} pairs", file=sys.stderr)

    # Build cluster data with canonical picks
    cluster_data = []
    for cluster_indices in clusters:
        canonical = pick_canonical(cluster_indices, claims)
        cd = format_cluster(cluster_indices, claims, similarity, canonical)
        cluster_data.append(cd)

    print(f"Finding near-duplicates ({NEAR_THRESHOLD}-{KNOWN_THRESHOLD})...",
          file=sys.stderr)
    near_pairs = find_near_duplicates(claims, similarity, NEAR_THRESHOLD, KNOWN_THRESHOLD)
    print(f"  {len(near_pairs)} near-duplicate pairs", file=sys.stderr)

    # Print report
    print_report(claims, clusters, cluster_data, near_pairs, similarity)

    # Save results
    output = {
        "config": {
            "known_threshold": KNOWN_THRESHOLD,
            "near_threshold": NEAR_THRESHOLD,
            "total_claims": len(claims),
            "total_articles": len(articles),
        },
        "summary": {
            "duplicate_clusters": len(cluster_data),
            "claims_in_clusters": sum(c["size"] for c in cluster_data),
            "unique_after_dedup": len(claims) - sum(c["size"] for c in cluster_data) + len(cluster_data),
            "near_duplicate_pairs": len(near_pairs),
        },
        "clusters": cluster_data,
        "near_duplicates": near_pairs[:100],  # Top 100 near-dups
    }
    output_path = DATA_DIR / "experiment_claim_dedup.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
