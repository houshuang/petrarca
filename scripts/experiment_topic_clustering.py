#!/usr/bin/env python3
"""Experiment: Topic clustering using embeddings (BERTopic-style).

Tests whether unsupervised clustering of claim embeddings produces better
topic groupings than the LLM-assigned topic tags.

Approach:
1. Use Nomic embeddings + UMAP dimensionality reduction + HDBSCAN clustering
2. Compare clusters with LLM-assigned topics
3. Identify topic groupings that LLM missed
4. Test whether embedding clusters could replace/augment LLM topic assignment

Usage:
    python3 scripts/experiment_topic_clustering.py
    python3 scripts/experiment_topic_clustering.py --model gemini
"""

import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict, Counter

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"


def load_data(model: str = "nomic"):
    """Load claims and embeddings."""
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    for article in articles:
        for claim in article.get("atomic_claims", []):
            claims.append({
                **claim,
                "article_id": article.get("id", ""),
                "article_title": article.get("title", ""),
            })

    emb_path = DATA_DIR / f"claim_embeddings{'_nomic' if model == 'nomic' else ''}.npz"
    data = np.load(emb_path)
    embeddings = data["embeddings"]

    return claims, embeddings


def cluster_with_umap_hdbscan(embeddings, min_cluster_size=5, n_neighbors=15):
    """UMAP + HDBSCAN clustering (BERTopic-style)."""
    try:
        import umap
        import hdbscan
    except ImportError:
        print("Installing umap-learn and hdbscan...", file=sys.stderr)
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                              "umap-learn", "hdbscan", "-q"])
        import umap
        import hdbscan

    print("  Running UMAP dimensionality reduction...", file=sys.stderr)
    reducer = umap.UMAP(
        n_components=5,
        n_neighbors=n_neighbors,
        min_dist=0.0,
        metric="cosine",
        random_state=42,
    )
    reduced = reducer.fit_transform(embeddings)

    print("  Running HDBSCAN clustering...", file=sys.stderr)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=3,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(reduced)

    # Also get 2D for visualization
    reducer_2d = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    coords_2d = reducer_2d.fit_transform(embeddings)

    return labels, reduced, coords_2d


def analyze_clusters(claims, labels, embeddings):
    """Analyze discovered clusters vs LLM-assigned topics."""
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = sum(1 for l in labels if l == -1)

    print(f"\n  Clusters found: {n_clusters}", file=sys.stderr)
    print(f"  Noise points: {n_noise}/{len(claims)} ({n_noise/len(claims)*100:.1f}%)", file=sys.stderr)

    # Analyze each cluster
    cluster_analysis = {}
    for cluster_id in sorted(set(labels)):
        if cluster_id == -1:
            continue

        member_indices = [i for i, l in enumerate(labels) if l == cluster_id]
        members = [claims[i] for i in member_indices]

        # What LLM topics appear in this cluster?
        topic_counts = Counter()
        for m in members:
            for t in m.get("topics", []):
                topic_counts[t] += 1

        # What articles are represented?
        article_counts = Counter(m["article_title"][:40] for m in members)

        # Representative claims (closest to cluster centroid)
        cluster_embeddings = embeddings[member_indices]
        centroid = cluster_embeddings.mean(axis=0)
        distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
        closest_idx = np.argsort(distances)[:3]
        representative = [members[i]["normalized_text"][:100] for i in closest_idx]

        # Claim types
        type_counts = Counter(m["claim_type"] for m in members)

        cluster_analysis[int(cluster_id)] = {
            "size": len(members),
            "top_topics": topic_counts.most_common(5),
            "top_articles": article_counts.most_common(3),
            "representatives": representative,
            "claim_types": dict(type_counts),
        }

    return cluster_analysis, n_clusters, n_noise


def compare_llm_vs_embedding_topics(claims, labels):
    """Compare LLM-assigned topics with embedding clusters."""
    # Build LLM topic → claim indices
    llm_topics = defaultdict(set)
    for i, claim in enumerate(claims):
        for t in claim.get("topics", []):
            llm_topics[t].add(i)

    # Build embedding cluster → claim indices
    emb_clusters = defaultdict(set)
    for i, l in enumerate(labels):
        if l >= 0:
            emb_clusters[l].add(i)

    # For each LLM topic, check if it maps cleanly to an embedding cluster
    topic_cluster_mapping = {}
    for topic, topic_indices in sorted(llm_topics.items(), key=lambda x: -len(x[1])):
        if len(topic_indices) < 3:
            continue

        # Find which cluster(s) contain most of this topic's claims
        cluster_overlaps = {}
        for cluster_id, cluster_indices in emb_clusters.items():
            overlap = len(topic_indices & cluster_indices)
            if overlap > 0:
                cluster_overlaps[cluster_id] = overlap

        if cluster_overlaps:
            best_cluster = max(cluster_overlaps, key=cluster_overlaps.get)
            purity = cluster_overlaps[best_cluster] / len(topic_indices)
            completeness = cluster_overlaps[best_cluster] / len(emb_clusters[best_cluster])
        else:
            best_cluster = -1
            purity = 0
            completeness = 0

        topic_cluster_mapping[topic] = {
            "topic_size": len(topic_indices),
            "best_cluster": int(best_cluster),
            "purity": round(purity, 3),  # what fraction of topic maps to one cluster
            "completeness": round(completeness, 3),  # what fraction of cluster is this topic
            "fragmentation": len(cluster_overlaps),  # spread across how many clusters
        }

    return topic_cluster_mapping


def find_emergent_topics(claims, labels, cluster_analysis):
    """Find clusters that don't map to any single LLM topic — emergent groupings."""
    emergent = []
    for cluster_id, analysis in cluster_analysis.items():
        top_topics = analysis["top_topics"]
        size = analysis["size"]

        if not top_topics:
            emergent.append({
                "cluster_id": cluster_id,
                "size": size,
                "reason": "no LLM topics assigned",
                "representatives": analysis["representatives"],
            })
        elif top_topics[0][1] / size < 0.5:
            # No single topic covers > 50% of the cluster — it's a cross-cutting theme
            emergent.append({
                "cluster_id": cluster_id,
                "size": size,
                "reason": "cross-cutting theme (no dominant LLM topic)",
                "top_topics": top_topics[:3],
                "representatives": analysis["representatives"],
            })

    return emergent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nomic", choices=["gemini", "nomic"])
    parser.add_argument("--min-cluster", type=int, default=5)
    args = parser.parse_args()

    print(f"Loading data (embeddings: {args.model})...", file=sys.stderr)
    claims, embeddings = load_data(args.model)
    print(f"  {len(claims)} claims, {embeddings.shape[1]} dimensions", file=sys.stderr)

    # Cluster
    labels, reduced, coords_2d = cluster_with_umap_hdbscan(
        embeddings, min_cluster_size=args.min_cluster
    )

    # Analyze
    cluster_analysis, n_clusters, n_noise = analyze_clusters(claims, labels, embeddings)

    print(f"\n{'='*60}")
    print(f"  CLUSTER ANALYSIS")
    print(f"{'='*60}")

    for cluster_id, analysis in sorted(cluster_analysis.items()):
        top_topic = analysis["top_topics"][0] if analysis["top_topics"] else ("none", 0)
        print(f"\n  Cluster {cluster_id} ({analysis['size']} claims):")
        print(f"    Top topics: {', '.join(f'{t}({c})' for t, c in analysis['top_topics'][:3])}")
        print(f"    Articles: {', '.join(f'{a}({c})' for a, c in analysis['top_articles'][:2])}")
        print(f"    Types: {analysis['claim_types']}")
        for r in analysis["representatives"]:
            print(f"    → {r}")

    # Compare with LLM topics
    print(f"\n{'='*60}")
    print(f"  LLM TOPIC vs EMBEDDING CLUSTER ALIGNMENT")
    print(f"{'='*60}")

    mapping = compare_llm_vs_embedding_topics(claims, labels)
    for topic, info in sorted(mapping.items(), key=lambda x: -x[1]["topic_size"]):
        status = "✓" if info["purity"] > 0.6 else "△" if info["purity"] > 0.3 else "✗"
        print(f"  {status} {topic} ({info['topic_size']} claims) → "
              f"cluster {info['best_cluster']} "
              f"(purity={info['purity']:.2f}, completeness={info['completeness']:.2f}, "
              f"fragmented across {info['fragmentation']} clusters)")

    # Find emergent topics
    emergent = find_emergent_topics(claims, labels, cluster_analysis)
    if emergent:
        print(f"\n{'='*60}")
        print(f"  EMERGENT TOPICS (embedding clusters without clear LLM topic)")
        print(f"{'='*60}")
        for e in emergent:
            print(f"\n  Cluster {e['cluster_id']} ({e['size']} claims) — {e['reason']}")
            if e.get("top_topics"):
                print(f"    Closest topics: {e['top_topics']}")
            for r in e["representatives"]:
                print(f"    → {r}")

    # Save results
    output = {
        "model": args.model,
        "n_claims": len(claims),
        "n_clusters": n_clusters,
        "n_noise": n_noise,
        "cluster_analysis": {str(k): v for k, v in cluster_analysis.items()},
        "topic_cluster_mapping": mapping,
        "emergent_topics": emergent,
        "coords_2d": coords_2d.tolist(),
        "labels": labels.tolist(),
    }
    output_path = DATA_DIR / "experiment_topic_clustering.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
