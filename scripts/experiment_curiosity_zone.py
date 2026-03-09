#!/usr/bin/env python3
"""Experiment: Curiosity zone scoring for article selection.

Tests the "zone of proximal development" idea from the research:
articles that are neither fully familiar nor completely unknown are
most interesting. The sweet spot is adjacent to current knowledge.

Approach:
1. After reading N articles, score remaining unread articles
2. Score = f(novelty_ratio, topic_overlap, extends_ratio)
3. Articles with ~60-80% novelty should score highest (some context, lots new)
4. Compare with naive "most novel" ranking

Usage:
    python3 scripts/experiment_curiosity_zone.py
    python3 scripts/experiment_curiosity_zone.py --top 10
"""

import json
import sys
import argparse
import math
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"


def load_data(model: str = "nomic"):
    """Load articles, claims, and similarity matrix."""
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    for article in articles:
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claims.append({
                **claim,
                "article_id": article.get("id", ""),
                "article_title": article.get("title", ""),
            })

    emb_path = DATA_DIR / f"claim_embeddings{'_nomic' if model == 'nomic' else ''}.npz"
    data = np.load(emb_path)
    embeddings = data["embeddings"]

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    similarity = normalized @ normalized.T

    return articles, claims, claim_to_idx, similarity


def classify_article_claims(article, claims, claim_to_idx, known_ids, similarity,
                            known_threshold=0.78, extends_threshold=0.68):
    """Classify all claims in an article relative to known claims."""
    article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]
    classifications = {"NEW": 0, "KNOWN": 0, "EXTENDS": 0}

    for claim in article_claims:
        idx = claim_to_idx.get(claim["id"])
        if idx is None:
            continue

        if claim["id"] in known_ids:
            classifications["KNOWN"] += 1
            continue

        max_sim = 0.0
        for kid in known_ids:
            kidx = claim_to_idx.get(kid)
            if kidx is not None:
                sim = float(similarity[idx, kidx])
                if sim > max_sim:
                    max_sim = sim

        if max_sim >= known_threshold:
            classifications["KNOWN"] += 1
        elif max_sim >= extends_threshold:
            classifications["EXTENDS"] += 1
        else:
            classifications["NEW"] += 1

    return classifications, len(article_claims)


def curiosity_score(classifications: dict, total: int) -> float:
    """Compute curiosity zone score.

    The ideal article has:
    - Some familiar context (KNOWN + EXTENDS > 0) — you can relate to it
    - Majority new content (NEW is high) — it teaches you something
    - Some EXTENDS (bridges known → new) — smooth learning curve

    The scoring function peaks at ~60-80% novelty with some familiar context.
    Pure 100% novel articles score lower (no context to anchor learning).
    Pure 100% known articles score near zero (nothing to learn).
    """
    if total == 0:
        return 0.0

    new_ratio = classifications["NEW"] / total
    extends_ratio = classifications["EXTENDS"] / total
    known_ratio = classifications["KNOWN"] / total

    # Novelty component: peaks at 0.7 (70% novel)
    # Uses a Gaussian centered at 0.7 with sigma=0.2
    novelty = new_ratio + extends_ratio * 0.5
    novelty_score = math.exp(-((novelty - 0.7) ** 2) / (2 * 0.2 ** 2))

    # Context bonus: having SOME known content helps anchor learning
    # Peaks at ~20-30% known
    context_bonus = min(known_ratio * 3, 1.0)  # 0 at 0%, peaks at 33%

    # Bridge bonus: EXTENDS claims are the most valuable — they connect
    bridge_bonus = extends_ratio * 2  # Linearly rewards EXTENDS

    # Combine: novelty is primary, context and bridge are bonuses
    score = novelty_score * 0.5 + context_bonus * 0.25 + bridge_bonus * 0.25

    return round(score, 4)


def curiosity_score_v2(classifications: dict, total: int,
                       topic_overlap: float = 0.0) -> float:
    """V2: Also considers topic-level interest overlap.

    topic_overlap: fraction of article's topics that user has shown interest in
    """
    base = curiosity_score(classifications, total)

    # Topic relevance: prefer articles in topics user is exploring
    # But not fully explored topics (that would be KNOWN heavy)
    topic_factor = 0.5 + 0.5 * topic_overlap  # 0.5 baseline, up to 1.0

    return round(base * topic_factor, 4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nomic", choices=["gemini", "nomic"])
    parser.add_argument("--read-first", type=int, default=10, help="Read this many articles first")
    parser.add_argument("--top", type=int, default=15, help="Show top N recommendations")
    args = parser.parse_args()

    print(f"Loading data (embeddings: {args.model})...", file=sys.stderr)
    articles, claims, claim_to_idx, similarity = load_data(args.model)
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    # Simulate: read first N articles
    known_ids = set()
    known_topics = defaultdict(int)

    for article in articles[:args.read_first]:
        for claim in article.get("atomic_claims", []):
            known_ids.add(claim["id"])
        for topic in article.get("interest_topics", []):
            if isinstance(topic, dict):
                known_topics[topic.get("topic", "")] += 1
            else:
                known_topics[topic] += 1

    print(f"\n  Read {args.read_first} articles, know {len(known_ids)} claims", file=sys.stderr)
    print(f"  Known topics: {', '.join(sorted(known_topics.keys())[:10])}", file=sys.stderr)

    # Score remaining unread articles
    unread = articles[args.read_first:]
    scored = []

    for article in unread:
        classifications, total = classify_article_claims(
            article, claims, claim_to_idx, known_ids, similarity,
            known_threshold=0.78 if args.model == "nomic" else 0.72,
            extends_threshold=0.68 if args.model == "nomic" else 0.62,
        )

        if total == 0:
            continue

        # Compute topic overlap
        article_topics = set()
        for t in article.get("interest_topics", []):
            if isinstance(t, dict):
                article_topics.add(t.get("topic", ""))
            else:
                article_topics.add(t)
        topic_overlap = (len(article_topics & set(known_topics.keys())) / len(article_topics)
                        if article_topics else 0)

        score = curiosity_score(classifications, total)
        score_v2 = curiosity_score_v2(classifications, total, topic_overlap)
        novelty_pct = round((classifications["NEW"] + classifications["EXTENDS"]) / total * 100, 1)

        scored.append({
            "title": article.get("title", "")[:60],
            "total_claims": total,
            "classifications": classifications,
            "novelty_pct": novelty_pct,
            "curiosity_score": score,
            "curiosity_score_v2": score_v2,
            "topic_overlap": round(topic_overlap, 2),
        })

    # Sort by curiosity score
    scored.sort(key=lambda x: x["curiosity_score_v2"], reverse=True)

    # Display results
    print(f"\n{'='*60}")
    print(f"  CURIOSITY ZONE RANKING (after reading {args.read_first} articles)")
    print(f"{'='*60}")

    print(f"\n  {'Rank':<5} {'Score':>6} {'Nov%':>5} {'N':>3} {'E':>3} {'K':>3} "
          f"{'TopOvl':>6} {'Title'}")
    print(f"  {'─'*5} {'─'*6} {'─'*5} {'─'*3} {'─'*3} {'─'*3} {'─'*6} {'─'*40}")

    for i, s in enumerate(scored[:args.top]):
        c = s["classifications"]
        print(f"  {i+1:<5} {s['curiosity_score_v2']:>6.3f} {s['novelty_pct']:>4.0f}% "
              f"{c['NEW']:>3} {c['EXTENDS']:>3} {c['KNOWN']:>3} "
              f"{s['topic_overlap']:>5.1f} {s['title']}")

    # Compare with naive "most novel" ranking
    naive_sorted = sorted(scored, key=lambda x: x["novelty_pct"], reverse=True)

    print(f"\n{'='*60}")
    print(f"  COMPARISON: Curiosity Zone vs Naive Most-Novel")
    print(f"{'='*60}")

    # Find articles that curiosity ranking promotes or demotes
    curiosity_top = set(s["title"] for s in scored[:10])
    naive_top = set(s["title"] for s in naive_sorted[:10])

    promoted = curiosity_top - naive_top
    demoted = naive_top - curiosity_top

    if promoted:
        print(f"\n  Promoted by curiosity zone (in top 10 for curiosity, not for naive novelty):")
        for title in promoted:
            s = next(x for x in scored if x["title"] == title)
            rank_curiosity = next(i+1 for i, x in enumerate(scored) if x["title"] == title)
            rank_naive = next(i+1 for i, x in enumerate(naive_sorted) if x["title"] == title)
            print(f"    #{rank_curiosity} (was #{rank_naive}): {title}")
            print(f"      Score={s['curiosity_score_v2']:.3f} Nov={s['novelty_pct']}% "
                  f"N={s['classifications']['NEW']} E={s['classifications']['EXTENDS']} "
                  f"K={s['classifications']['KNOWN']}")

    if demoted:
        print(f"\n  Demoted by curiosity zone (in top 10 for naive, not for curiosity):")
        for title in demoted:
            s = next(x for x in scored if x["title"] == title)
            rank_curiosity = next(i+1 for i, x in enumerate(scored) if x["title"] == title)
            rank_naive = next(i+1 for i, x in enumerate(naive_sorted) if x["title"] == title)
            print(f"    #{rank_curiosity} (was #{rank_naive}): {title}")
            print(f"      Score={s['curiosity_score_v2']:.3f} Nov={s['novelty_pct']}% "
                  f"N={s['classifications']['NEW']} E={s['classifications']['EXTENDS']} "
                  f"K={s['classifications']['KNOWN']}")

    # Score distribution analysis
    print(f"\n{'='*60}")
    print(f"  SCORE DISTRIBUTION ANALYSIS")
    print(f"{'='*60}")

    scores = [s["curiosity_score_v2"] for s in scored]
    novelties = [s["novelty_pct"] for s in scored]

    print(f"  Curiosity scores: mean={np.mean(scores):.3f}, "
          f"std={np.std(scores):.3f}, "
          f"min={min(scores):.3f}, max={max(scores):.3f}")
    print(f"  Novelty %: mean={np.mean(novelties):.1f}%, "
          f"min={min(novelties):.1f}%, max={max(novelties):.1f}%")

    # Correlation between curiosity score and raw novelty
    correlation = np.corrcoef(scores, novelties)[0, 1]
    print(f"  Correlation (curiosity vs novelty): {correlation:.3f}")
    print(f"    {'→ High correlation = curiosity adds little value' if abs(correlation) > 0.8 else '→ Good: curiosity differs meaningfully from naive novelty'}")

    # Save results
    output = {
        "model": args.model,
        "articles_read": args.read_first,
        "known_claims": len(known_ids),
        "curiosity_ranking": scored[:20],
        "naive_ranking": [{"title": s["title"], "novelty_pct": s["novelty_pct"],
                           "curiosity_score": s["curiosity_score_v2"]}
                          for s in naive_sorted[:20]],
        "promoted": list(promoted),
        "demoted": list(demoted),
        "correlation": round(float(correlation), 3),
        "score_stats": {
            "mean": round(float(np.mean(scores)), 3),
            "std": round(float(np.std(scores)), 3),
        },
    }
    output_path = DATA_DIR / "experiment_curiosity_zone.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
