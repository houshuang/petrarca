#!/usr/bin/env python3
"""Experiment: Contradiction detection between claims.

Tests whether LLM judge can find genuinely contradictory claims across articles.
Uses a two-stage approach:
1. Embedding-based candidate generation (moderate similarity + different topics/conclusions)
2. LLM judge for contradiction classification

Also tests "soft contradictions" (disagreements in emphasis, evaluation, or recommendation)
vs "hard contradictions" (factual disagreements).

Usage:
    python3 scripts/experiment_contradiction_detection.py
"""

import json
import os
import sys
import random
from pathlib import Path
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
EMBEDDINGS_PATH = DATA_DIR / "claim_embeddings_nomic.npz"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY", "")


def load_data():
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    for article in articles:
        for claim in article.get("atomic_claims", []):
            claims.append({**claim, "article_id": article.get("id", ""),
                           "article_title": article.get("title", "")})

    data = np.load(EMBEDDINGS_PATH)
    embeddings = data["embeddings"]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = embeddings / norms
    similarity = normed @ normed.T

    return articles, claims, similarity


def find_contradiction_candidates(claims, similarity):
    """Find pairs that are topically similar but potentially contradictory.

    Strategy: Look for pairs with moderate-high similarity (0.60-0.85) that:
    1. Come from different articles
    2. Have at least one shared topic
    3. Include evaluative or causal claims (more likely to disagree)
    """
    candidates = []
    n = len(claims)

    # Build topic index
    topic_to_claims = defaultdict(set)
    for i, c in enumerate(claims):
        for t in c.get("topics", []):
            topic_to_claims[t].add(i)

    # Prioritize evaluative/causal claims (more likely to contain opinions)
    opinion_types = {"eval", "caus", "pred"}

    for i in range(n):
        ci = claims[i]
        ci_type = ci.get("claim_type", "")

        for j in range(i + 1, n):
            cj = claims[j]

            # Must be from different articles
            if ci["article_id"] == cj["article_id"]:
                continue

            sim = float(similarity[i, j])
            # Sweet spot: similar enough to be about the same thing, but not identical
            if sim < 0.55 or sim > 0.85:
                continue

            # Must share at least one topic
            topics_i = set(ci.get("topics", []))
            topics_j = set(cj.get("topics", []))
            shared_topics = topics_i & topics_j
            if not shared_topics:
                continue

            # Prefer evaluative/causal claims
            cj_type = cj.get("claim_type", "")
            opinion_bonus = 0
            if ci_type in opinion_types:
                opinion_bonus += 1
            if cj_type in opinion_types:
                opinion_bonus += 1

            candidates.append({
                "idx_a": i,
                "idx_b": j,
                "similarity": sim,
                "shared_topics": list(shared_topics),
                "types": [ci_type, cj_type],
                "opinion_bonus": opinion_bonus,
                "text_a": ci["normalized_text"],
                "text_b": cj["normalized_text"],
                "article_a": ci["article_title"][:50],
                "article_b": cj["article_title"][:50],
            })

    # Sort by opinion_bonus (desc), then similarity (prefer mid-range)
    candidates.sort(key=lambda x: (-x["opinion_bonus"],
                                    -abs(x["similarity"] - 0.70)))

    return candidates


def judge_contradiction(claim_a, claim_b):
    """Use Gemini to judge if two claims contradict each other."""
    import litellm

    prompt = f"""Analyze whether these two claims contradict each other.

CLAIM A: {claim_a}
CLAIM B: {claim_b}

Classify the relationship as one of:
1. HARD_CONTRADICTION — Direct factual disagreement. Both cannot be true simultaneously.
2. SOFT_CONTRADICTION — Disagreement in evaluation, emphasis, or recommendation. Both could be technically true but express opposing views.
3. TENSION — Not outright contradiction but notable tension or different perspective on the same topic.
4. COMPATIBLE — No contradiction. Claims are consistent even if they cover different aspects.

Respond in this exact JSON format:
{{"relationship": "HARD_CONTRADICTION|SOFT_CONTRADICTION|TENSION|COMPATIBLE", "explanation": "brief explanation of why", "confidence": 0.0-1.0}}"""

    try:
        resp = litellm.completion(
            model="gemini/gemini-2.0-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
            api_key=GEMINI_API_KEY,
        )
        text = resp.choices[0].message.content.strip()
        # Extract JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception as e:
        return {"relationship": "ERROR", "explanation": str(e), "confidence": 0.0}


def main():
    if not GEMINI_API_KEY:
        print("Error: GEMINI_KEY or GEMINI_API_KEY required", file=sys.stderr)
        sys.exit(1)

    print("Loading data...", file=sys.stderr)
    articles, claims, similarity = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    print("Finding contradiction candidates...", file=sys.stderr)
    candidates = find_contradiction_candidates(claims, similarity)
    print(f"  {len(candidates)} candidates found", file=sys.stderr)

    # Sample: take top candidates (opinion-heavy pairs)
    sample_size = min(50, len(candidates))
    sample = candidates[:sample_size]

    print(f"\nJudging {sample_size} candidate pairs...", file=sys.stderr)
    results = []
    relationship_counts = defaultdict(int)

    for i, cand in enumerate(sample):
        print(f"  [{i+1}/{sample_size}] sim={cand['similarity']:.3f} "
              f"types={cand['types']}", file=sys.stderr)

        judgment = judge_contradiction(cand["text_a"], cand["text_b"])
        result = {**cand, "judgment": judgment}
        results.append(result)

        rel = judgment.get("relationship", "ERROR")
        relationship_counts[rel] += 1

    # Print report
    print(f"\n{'='*70}")
    print(f"  CONTRADICTION DETECTION REPORT")
    print(f"{'='*70}")

    print(f"\n  CANDIDATES ANALYZED: {sample_size}")
    print(f"\n  RESULTS:")
    for rel in ["HARD_CONTRADICTION", "SOFT_CONTRADICTION", "TENSION", "COMPATIBLE", "ERROR"]:
        count = relationship_counts.get(rel, 0)
        pct = count / sample_size * 100 if sample_size > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {rel:<25} {count:>3} ({pct:>5.1f}%) {bar}")

    # Show interesting findings
    for rel_type in ["HARD_CONTRADICTION", "SOFT_CONTRADICTION", "TENSION"]:
        findings = [r for r in results if r["judgment"].get("relationship") == rel_type]
        if not findings:
            continue

        print(f"\n{'─'*70}")
        print(f"  ✦ {rel_type} ({len(findings)} found)")
        print(f"{'─'*70}")

        for r in findings[:5]:
            j = r["judgment"]
            print(f"\n  [{r['similarity']:.3f}] confidence={j.get('confidence', '?')}")
            print(f"    A: {r['text_a'][:90]}")
            print(f"       — {r['article_a']}")
            print(f"    B: {r['text_b'][:90]}")
            print(f"       — {r['article_b']}")
            print(f"    Explanation: {j.get('explanation', '')}")

    # Save results
    output = {
        "config": {
            "sample_size": sample_size,
            "total_candidates": len(candidates),
            "similarity_range": [0.55, 0.85],
        },
        "summary": dict(relationship_counts),
        "results": results,
    }
    output_path = DATA_DIR / "experiment_contradiction_detection.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
