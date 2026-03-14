#!/usr/bin/env python3
"""Build concept clusters from the Petrarca knowledge index.

Groups related articles into clusters based on shared claims (EXTENDS + KNOWN)
from the article novelty matrix. Detects near-duplicate articles and generates
LLM-synthesized cluster labels.

Output: data/concept_clusters.json

Usage:
    python3 scripts/build_concept_clusters.py                # full build with LLM labels
    python3 scripts/build_concept_clusters.py --dry-run      # analyze clusters without writing output
    python3 scripts/build_concept_clusters.py --verbose       # show detailed cluster info
    python3 scripts/build_concept_clusters.py --skip-llm      # skip LLM label generation
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
KNOWLEDGE_INDEX_PATH = DATA_DIR / "knowledge_index.json"
OUTPUT_PATH = DATA_DIR / "concept_clusters.json"

# Clustering parameters
MIN_EDGE_WEIGHT = 3          # Minimum shared claims (extends+known) to create an edge
MAX_COMPONENT_SIZE = 15      # Split components larger than this
MIN_CLUSTER_SIZE = 2         # Minimum articles per cluster
NEAR_DUPE_THRESHOLD = 0.80   # >80% claims KNOWN → near-duplicate

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


def load_data() -> tuple[list[dict], dict]:
    """Load articles.json and knowledge_index.json."""
    if not ARTICLES_PATH.exists():
        log(f"ERROR: {ARTICLES_PATH} not found")
        sys.exit(1)
    if not KNOWLEDGE_INDEX_PATH.exists():
        log(f"ERROR: {KNOWLEDGE_INDEX_PATH} not found")
        sys.exit(1)

    with open(ARTICLES_PATH) as f:
        articles = json.load(f)
    with open(KNOWLEDGE_INDEX_PATH) as f:
        ki = json.load(f)

    return articles, ki


def build_article_graph(ki: dict) -> dict[tuple[str, str], int]:
    """Build undirected article similarity graph from novelty matrix.

    Edge weight = max(extends+known) across both directions for each pair.
    Only includes edges where weight >= MIN_EDGE_WEIGHT.
    """
    nm = ki.get("article_novelty_matrix", {})
    edges: dict[tuple[str, str], int] = {}

    for target_id, entries in nm.items():
        for read_id, counts in entries.items():
            weight = counts.get("extends", 0) + counts.get("known", 0)
            pair = tuple(sorted([target_id, read_id]))
            edges[pair] = max(edges.get(pair, 0), weight)

    # Filter by minimum weight
    return {pair: w for pair, w in edges.items() if w >= MIN_EDGE_WEIGHT}


def find_connected_components(edges: dict[tuple[str, str], int]) -> list[set[str]]:
    """Find connected components using BFS (no external graph libraries)."""
    # Build adjacency list
    adj: dict[str, set[str]] = defaultdict(set)
    for (a, b), _ in edges.items():
        adj[a].add(b)
        adj[b].add(a)

    visited: set[str] = set()
    components: list[set[str]] = []

    for node in adj:
        if node in visited:
            continue
        # BFS
        component: set[str] = set()
        queue = [node]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    return components


def split_large_component(component: set[str],
                           edges: dict[tuple[str, str], int],
                           articles: list[dict],
                           depth: int = 0) -> list[set[str]]:
    """Split a large component using topic-guided spectral bisection.

    Strategy:
    1. Build a topic signature for each article (TF vector over topics).
    2. Compute a normalized Laplacian from edge weights.
    3. Use the Fiedler vector (2nd smallest eigenvector of Laplacian) to bisect.
    4. Recurse on any sub-cluster still larger than MAX_COMPONENT_SIZE.

    Falls back to topic-based grouping if spectral method fails.
    """
    nodes = list(component)
    if len(nodes) <= MAX_COMPONENT_SIZE:
        return [component]

    n = len(nodes)
    node_idx = {nid: i for i, nid in enumerate(nodes)}

    # Build weighted adjacency matrix (local to this component)
    W = np.zeros((n, n), dtype=np.float64)
    for (a, b), w in edges.items():
        if a in component and b in component:
            i, j = node_idx[a], node_idx[b]
            W[i, j] = w
            W[j, i] = w

    # Compute normalized Laplacian: L = D - W, L_norm = D^{-1/2} L D^{-1/2}
    D = np.diag(W.sum(axis=1))
    L = D - W

    # D^{-1/2} — handle zero-degree nodes
    d_sqrt_inv = np.zeros(n)
    diag_vals = np.diag(D)
    nonzero = diag_vals > 0
    d_sqrt_inv[nonzero] = 1.0 / np.sqrt(diag_vals[nonzero])
    D_sqrt_inv = np.diag(d_sqrt_inv)

    L_norm = D_sqrt_inv @ L @ D_sqrt_inv

    # Compute eigenvalues and eigenvectors
    try:
        eigenvalues, eigenvectors = np.linalg.eigh(L_norm)
        # Fiedler vector is the 2nd smallest eigenvector
        fiedler = eigenvectors[:, 1]
    except np.linalg.LinAlgError:
        log(f"  {'  ' * depth}Spectral decomposition failed, falling back to topic grouping")
        return _topic_based_split(component, edges, articles, depth)

    # Bisect using the Fiedler vector's sign
    group_a = set()
    group_b = set()
    median_val = float(np.median(fiedler))

    for i, nid in enumerate(nodes):
        if fiedler[i] <= median_val:
            group_a.add(nid)
        else:
            group_b.add(nid)

    # Ensure both groups have at least MIN_CLUSTER_SIZE
    if len(group_a) < MIN_CLUSTER_SIZE or len(group_b) < MIN_CLUSTER_SIZE:
        return _topic_based_split(component, edges, articles, depth)

    # Recurse on groups that are still too large
    result = []
    for group in [group_a, group_b]:
        if len(group) > MAX_COMPONENT_SIZE:
            result.extend(split_large_component(group, edges, articles, depth + 1))
        elif len(group) >= MIN_CLUSTER_SIZE:
            result.append(group)

    if not result:
        return _topic_based_split(component, edges, articles, depth)

    return result


def _topic_based_split(component: set[str],
                        edges: dict[tuple[str, str], int],
                        articles: list[dict],
                        depth: int = 0) -> list[set[str]]:
    """Split a component by grouping articles by their primary topic.

    Each article's primary topic is its most specific (least common globally) topic.
    Articles sharing a primary topic are grouped together. Groups that are too large
    are recursively split.
    """
    article_map = {a["id"]: a for a in articles}

    # Count global topic frequency to find specific topics
    global_topic_freq: dict[str, int] = defaultdict(int)
    for a in articles:
        for t in a.get("topics", []):
            global_topic_freq[t] += 1

    # Assign each article to its most specific topic
    topic_groups: dict[str, set[str]] = defaultdict(set)
    for nid in component:
        art = article_map.get(nid, {})
        topics = art.get("topics", [])
        if not topics:
            topic_groups["_uncategorized"].add(nid)
            continue
        # Pick the most specific topic (lowest global frequency)
        primary = min(topics, key=lambda t: global_topic_freq.get(t, 999))
        topic_groups[primary].add(nid)

    # Merge tiny topic groups (< MIN_CLUSTER_SIZE) into their best-connected neighbor
    small_groups = {t: g for t, g in topic_groups.items() if len(g) < MIN_CLUSTER_SIZE}
    large_groups = {t: g for t, g in topic_groups.items() if len(g) >= MIN_CLUSTER_SIZE}

    for topic, small_group in small_groups.items():
        best_target = None
        best_weight = -1
        for node in small_group:
            for (a, b), w in edges.items():
                other = b if a == node else (a if b == node else None)
                if other is None:
                    continue
                for lt, lg in large_groups.items():
                    if other in lg and w > best_weight:
                        best_weight = w
                        best_target = lt
        if best_target and best_target in large_groups:
            large_groups[best_target].update(small_group)
        # Otherwise these articles are dropped (isolated with no cluster)

    # Recursively split groups still too large
    result = []
    for topic, group in large_groups.items():
        if len(group) > MAX_COMPONENT_SIZE:
            # Try spectral split with higher edge threshold
            sub_edges = {p: w for p, w in edges.items()
                         if p[0] in group and p[1] in group}
            # Increase threshold for this sub-component
            if depth < 3:
                higher_threshold = MIN_EDGE_WEIGHT + (depth + 1) * 3
                filtered_edges = {p: w for p, w in sub_edges.items() if w >= higher_threshold}
                sub_components = find_connected_components(filtered_edges)
                valid = [c for c in sub_components if len(c) >= MIN_CLUSTER_SIZE]
                if len(valid) >= 2:
                    for c in valid:
                        if len(c) > MAX_COMPONENT_SIZE:
                            result.extend(split_large_component(c, edges, articles, depth + 1))
                        else:
                            result.append(c)
                    continue
            # If still can't split, just keep the large group
            result.append(group)
        elif len(group) >= MIN_CLUSTER_SIZE:
            result.append(group)

    return result if result else [component]


def detect_near_duplicates(ki: dict, articles: list[dict]) -> list[dict]:
    """Find article pairs where one has >80% claims KNOWN relative to another."""
    nm = ki.get("article_novelty_matrix", {})
    ac = ki.get("article_claims", {})
    title_map = {a["id"]: a.get("title", "") for a in articles}

    near_dupes = []
    seen_pairs: set[tuple[str, str]] = set()

    for target_id, entries in nm.items():
        total_claims = len(ac.get(target_id, []))
        if total_claims == 0:
            continue
        for read_id, counts in entries.items():
            known = counts.get("known", 0)
            ratio = known / total_claims
            if ratio >= NEAR_DUPE_THRESHOLD:
                pair = tuple(sorted([target_id, read_id]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                near_dupes.append({
                    "article_a": target_id,
                    "article_b": read_id,
                    "title_a": title_map.get(target_id, ""),
                    "title_b": title_map.get(read_id, ""),
                    "known_claims": known,
                    "total_claims_a": total_claims,
                    "overlap_ratio": round(ratio, 3),
                })

    near_dupes.sort(key=lambda x: -x["overlap_ratio"])
    return near_dupes


def compute_cluster_details(cluster: set[str],
                             edges: dict[tuple[str, str], int],
                             articles: list[dict],
                             ki: dict) -> dict:
    """Compute detailed info for a cluster."""
    article_map = {a["id"]: a for a in articles}
    ac = ki.get("article_claims", {})
    claims_dict = ki.get("claims", {})

    # Compute connectivity (degree within cluster) for each article
    node_degree: dict[str, int] = defaultdict(int)
    node_weight: dict[str, int] = defaultdict(int)
    for (a, b), w in edges.items():
        if a in cluster and b in cluster:
            node_degree[a] += 1
            node_degree[b] += 1
            node_weight[a] += w
            node_weight[b] += w

    # Sort by weighted degree (most connected first)
    sorted_nodes = sorted(cluster, key=lambda n: node_weight.get(n, 0), reverse=True)

    # Core articles: top third by connectivity (min 1)
    core_count = max(1, len(sorted_nodes) // 3)
    core_ids = sorted_nodes[:core_count]
    peripheral_ids = sorted_nodes[core_count:]

    # Collect all claims in this cluster
    cluster_claim_ids: set[str] = set()
    for aid in cluster:
        cluster_claim_ids.update(ac.get(aid, []))

    # Find shared claims: claims that appear in similarity pairs across articles in this cluster
    shared_claim_ids: set[str] = set()
    sims = ki.get("similarities", [])
    # Build a set of article IDs in cluster for fast lookup
    cluster_set = cluster
    for pair in sims:
        cid_a = pair["a"]
        cid_b = pair["b"]
        art_a = claims_dict.get(cid_a, {}).get("article_id", "")
        art_b = claims_dict.get(cid_b, {}).get("article_id", "")
        if art_a in cluster_set and art_b in cluster_set and art_a != art_b:
            shared_claim_ids.add(cid_a)
            shared_claim_ids.add(cid_b)

    # Collect topics across cluster articles
    topic_counts: dict[str, int] = defaultdict(int)
    for aid in cluster:
        art = article_map.get(aid, {})
        for t in art.get("topics", []):
            topic_counts[t] += 1

    # Most common topic as fallback label
    top_topics = sorted(topic_counts.items(), key=lambda x: -x[1])
    fallback_label = top_topics[0][0] if top_topics else "Unlabeled"

    # Key shared claim texts (top by frequency in similarity pairs)
    shared_claim_freq: dict[str, int] = defaultdict(int)
    for pair in sims:
        cid_a = pair["a"]
        cid_b = pair["b"]
        art_a = claims_dict.get(cid_a, {}).get("article_id", "")
        art_b = claims_dict.get(cid_b, {}).get("article_id", "")
        if art_a in cluster_set and art_b in cluster_set and art_a != art_b:
            shared_claim_freq[cid_a] += 1
            shared_claim_freq[cid_b] += 1

    top_shared = sorted(shared_claim_freq.items(), key=lambda x: -x[1])[:10]
    key_claims = []
    for cid, freq in top_shared:
        claim_info = claims_dict.get(cid, {})
        key_claims.append({
            "claim_id": cid,
            "text": claim_info.get("text", ""),
            "article_id": claim_info.get("article_id", ""),
            "cross_article_links": freq,
        })

    # Internal edge stats
    internal_edges = [(pair, w) for pair, w in edges.items()
                      if pair[0] in cluster and pair[1] in cluster]
    avg_weight = np.mean([w for _, w in internal_edges]) if internal_edges else 0

    # Build article list with metadata
    article_entries = []
    for aid in sorted_nodes:
        art = article_map.get(aid, {})
        article_entries.append({
            "id": aid,
            "title": art.get("title", ""),
            "topics": art.get("topics", []),
            "claim_count": len(ac.get(aid, [])),
            "internal_degree": node_degree.get(aid, 0),
            "internal_weight": node_weight.get(aid, 0),
            "is_core": aid in core_ids,
        })

    return {
        "label": fallback_label,  # Will be replaced by LLM label
        "size": len(cluster),
        "articles": article_entries,
        "core_article_ids": core_ids,
        "peripheral_article_ids": peripheral_ids,
        "top_topics": [{"topic": t, "count": c} for t, c in top_topics[:10]],
        "total_unique_claims": len(cluster_claim_ids),
        "total_shared_claims": len(shared_claim_ids),
        "key_shared_claims": key_claims,
        "internal_edges": len(internal_edges),
        "avg_edge_weight": round(float(avg_weight), 1),
    }


def _update_params(min_weight: int, max_component: int):
    """Update module-level clustering parameters from CLI args."""
    global MIN_EDGE_WEIGHT, MAX_COMPONENT_SIZE
    MIN_EDGE_WEIGHT = min_weight
    MAX_COMPONENT_SIZE = max_component


def _build_cluster_context(cluster: dict, article_map: dict) -> str:
    """Build a text summary of a cluster's articles + shared claims for labeling."""
    titles = []
    for entry in cluster["articles"][:10]:
        art = article_map.get(entry["id"], {})
        title = art.get("title", "")
        summary = art.get("one_line_summary", "")
        titles.append(f"- {title}" + (f" ({summary})" if summary else ""))

    claims_text = ""
    if cluster.get("key_shared_claims"):
        claims_text = "\nKey shared concepts:\n" + "\n".join(
            f"- {c['text']}" for c in cluster["key_shared_claims"][:5]
        )

    return "\n".join(titles) + claims_text


def generate_cluster_labels(clusters: list[dict], articles: list[dict]) -> list[dict]:
    """Use LLM to generate descriptive labels for each cluster.

    Two-pass approach:
    1. Generate initial labels independently for each cluster
    2. Detect collisions and re-prompt with contrastive context
    """
    from gemini_llm import call_llm

    article_map = {a["id"]: a for a in articles}

    # --- Pass 1: Initial labels ---
    log("  Pass 1: generating initial labels...")
    for i, cluster in enumerate(clusters):
        context = _build_cluster_context(cluster, article_map)
        prompt = (
            f"These {cluster['size']} articles form a concept cluster. "
            f"Generate a short, descriptive label (3-7 words) that captures "
            f"the specific common theme. Be specific — avoid generic labels like "
            f"the broad topic name. Return ONLY the label, nothing else.\n\n"
            f"Articles:\n{context}"
        )

        label = call_llm(prompt, max_tokens=30)
        if label:
            label = label.strip().strip('"').strip("'").strip(".")
            cluster["label"] = label
            log(f"    {i+1}/{len(clusters)}: {label} ({cluster['size']} articles)")
        else:
            log(f"    {i+1}/{len(clusters)}: [LLM failed, using topic] {cluster['label']} ({cluster['size']} articles)")

    # --- Pass 2: Fix collisions ---
    from collections import Counter
    label_counts = Counter(c["label"].lower() for c in clusters)
    dupes = {l for l, count in label_counts.items() if count > 1}

    if dupes:
        log(f"  Pass 2: fixing {len(dupes)} duplicate label groups...")
        for dupe_label in sorted(dupes):
            collision_group = [c for c in clusters if c["label"].lower() == dupe_label]
            log(f"    Resolving {len(collision_group)}x '{dupe_label}'...")

            # Build contrastive prompt with all clusters sharing this label
            cluster_descriptions = []
            for j, c in enumerate(collision_group):
                context = _build_cluster_context(c, article_map)
                cluster_descriptions.append(
                    f"CLUSTER {j+1} ({c['size']} articles):\n{context}"
                )

            contrastive_prompt = (
                f"These {len(collision_group)} clusters all got the same label '{dupe_label}' "
                f"but they cover DIFFERENT aspects. Generate a UNIQUE, specific label "
                f"(3-7 words) for each one that distinguishes it from the others.\n\n"
                + "\n\n".join(cluster_descriptions) +
                f"\n\nReturn exactly {len(collision_group)} labels, one per line, "
                f"in the same order as the clusters above. Each label must be different. "
                f"Return ONLY the labels, nothing else."
            )

            result = call_llm(contrastive_prompt, max_tokens=200)
            if result:
                new_labels = [l.strip().strip('"').strip("'").strip(".").lstrip("0123456789. )")
                              for l in result.strip().split("\n") if l.strip()]
                if len(new_labels) >= len(collision_group):
                    for j, c in enumerate(collision_group):
                        old = c["label"]
                        c["label"] = new_labels[j]
                        log(f"      '{old}' → '{new_labels[j]}'")
                else:
                    log(f"      LLM returned {len(new_labels)} labels for {len(collision_group)} clusters, skipping")
            else:
                log(f"      LLM failed for contrastive refinement of '{dupe_label}'")

    # --- Filter junk clusters (all articles have empty titles) ---
    for cluster in clusters:
        real_titles = sum(1 for e in cluster["articles"] if article_map.get(e["id"], {}).get("title", "").strip())
        if real_titles == 0:
            cluster["label"] = "Uncategorized"

    return clusters


def main():
    parser = argparse.ArgumentParser(description="Build concept clusters from Petrarca knowledge index")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed cluster information")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analyze clusters without writing output")
    parser.add_argument("--skip-llm", action="store_true",
                        help="Skip LLM cluster label generation")
    parser.add_argument("--min-weight", type=int, default=3,
                        help="Minimum edge weight (default: 3)")
    parser.add_argument("--max-component", type=int, default=15,
                        help="Max component size before splitting (default: 15)")
    args = parser.parse_args()

    # Apply CLI overrides to module-level parameters
    _update_params(args.min_weight, args.max_component)

    log("=== Building Petrarca Concept Clusters ===")
    log("")

    # 1. Load data
    log("Loading data...")
    articles, ki = load_data()
    article_map = {a["id"]: a for a in articles}
    ac = ki.get("article_claims", {})
    log(f"  {len(articles)} articles, {ki['stats']['total_claims']} claims")

    # 2. Build article graph
    log("Building article similarity graph...")
    edges = build_article_graph(ki)
    # Count unique articles in graph
    nodes_in_graph: set[str] = set()
    for (a, b) in edges:
        nodes_in_graph.add(a)
        nodes_in_graph.add(b)
    log(f"  {len(nodes_in_graph)} articles in graph, {len(edges)} edges (weight >= {MIN_EDGE_WEIGHT})")

    # 3. Find connected components
    log("Finding connected components...")
    components = find_connected_components(edges)
    components.sort(key=len, reverse=True)
    log(f"  {len(components)} components")
    for i, comp in enumerate(components[:10]):
        log(f"    Component {i+1}: {len(comp)} articles")

    # 4. Split large components
    log("Splitting large components...")
    clusters: list[set[str]] = []
    for comp in components:
        if len(comp) > MAX_COMPONENT_SIZE:
            sub = split_large_component(comp, edges, articles)
            log(f"  Split component ({len(comp)} articles) into {len(sub)} clusters")
            clusters.extend(sub)
        elif len(comp) >= MIN_CLUSTER_SIZE:
            clusters.append(comp)

    # Prune articles with no internal edges from their cluster
    pruned_clusters: list[set[str]] = []
    for cluster in clusters:
        # Build internal adjacency for this cluster
        connected = set()
        for (a, b), w in edges.items():
            if a in cluster and b in cluster:
                connected.add(a)
                connected.add(b)
        pruned = cluster & connected if connected else cluster
        if len(pruned) >= MIN_CLUSTER_SIZE:
            pruned_clusters.append(pruned)
    clusters = pruned_clusters

    # Sort clusters by size (largest first)
    clusters.sort(key=len, reverse=True)
    log(f"  {len(clusters)} clusters (>= {MIN_CLUSTER_SIZE} articles)")

    # 5. Detect near-duplicates
    log("Detecting near-duplicate articles...")
    near_dupes = detect_near_duplicates(ki, articles)
    log(f"  {len(near_dupes)} near-duplicate pairs found")

    # 6. Compute cluster details
    log("Computing cluster details...")
    cluster_details = []
    for i, cluster in enumerate(clusters):
        details = compute_cluster_details(cluster, edges, articles, ki)
        details["cluster_id"] = i + 1
        cluster_details.append(details)

    # 7. Generate LLM labels
    if not args.skip_llm and not args.dry_run:
        log("Generating LLM cluster labels...")
        cluster_details = generate_cluster_labels(cluster_details, articles)
    else:
        if args.skip_llm:
            log("Skipping LLM labels (--skip-llm)")
        for d in cluster_details:
            log(f"  Cluster {d['cluster_id']}: {d['label']} ({d['size']} articles)")

    # 8. Build output
    output = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parameters": {
            "min_edge_weight": MIN_EDGE_WEIGHT,
            "max_component_size": MAX_COMPONENT_SIZE,
            "min_cluster_size": MIN_CLUSTER_SIZE,
            "near_dupe_threshold": NEAR_DUPE_THRESHOLD,
        },
        "stats": {
            "total_articles": len(articles),
            "articles_in_graph": len(nodes_in_graph),
            "articles_in_clusters": sum(d["size"] for d in cluster_details),
            "total_edges": len(edges),
            "total_components": len(components),
            "total_clusters": len(cluster_details),
            "near_duplicate_pairs": len(near_dupes),
        },
        "clusters": cluster_details,
        "near_duplicates": near_dupes[:50],  # Cap at 50 most overlapping
    }

    # 9. Print summary
    print(f"\n{'='*60}")
    print(f"  Petrarca Concept Clusters")
    print(f"{'='*60}")
    print(f"  Generated: {output['generated_at']}")
    print(f"  Articles:  {len(articles)} total, {len(nodes_in_graph)} in graph, "
          f"{output['stats']['articles_in_clusters']} in clusters")
    print(f"  Edges:     {len(edges)} (weight >= {MIN_EDGE_WEIGHT})")
    print(f"  Components:{len(components)}")
    print(f"  Clusters:  {len(cluster_details)} (>= {MIN_CLUSTER_SIZE} articles)")
    print(f"  Near-dupes:{len(near_dupes)} pairs")
    print()

    # Cluster summary
    print("  Clusters:")
    for d in cluster_details[:30]:
        core_titles = []
        for entry in d["articles"]:
            if entry["is_core"]:
                core_titles.append(entry["title"][:50])
        core_str = "; ".join(core_titles[:3])
        topics_str = ", ".join(t["topic"] for t in d["top_topics"][:3])
        print(f"    #{d['cluster_id']} [{d['size']} articles] {d['label']}")
        print(f"       Topics: {topics_str}")
        print(f"       Core: {core_str}")
        print(f"       Claims: {d['total_unique_claims']} unique, {d['total_shared_claims']} shared, "
              f"avg edge weight: {d['avg_edge_weight']}")
        if args.verbose:
            for entry in d["articles"]:
                role = "CORE" if entry["is_core"] else "    "
                print(f"         {role} {entry['title'][:60]} "
                      f"(deg={entry['internal_degree']}, w={entry['internal_weight']})")
            if d.get("key_shared_claims"):
                print(f"       Key shared claims:")
                for c in d["key_shared_claims"][:5]:
                    print(f"         - {c['text'][:80]} (links={c['cross_article_links']})")
        print()

    # Near-duplicate summary
    if near_dupes and args.verbose:
        print("  Near-duplicates (top 20):")
        for nd in near_dupes[:20]:
            print(f"    {nd['title_a'][:40]} <-> {nd['title_b'][:40]}: "
                  f"{nd['known_claims']}/{nd['total_claims_a']} ({nd['overlap_ratio']:.0%})")
        print()

    # 10. Write output
    if not args.dry_run:
        log(f"Writing {OUTPUT_PATH}...")
        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        file_size = OUTPUT_PATH.stat().st_size
        log(f"  {file_size:,} bytes ({file_size / 1024:.1f} KB)")
    else:
        log("Dry run — not writing output")

    log("Done.")


if __name__ == "__main__":
    main()
