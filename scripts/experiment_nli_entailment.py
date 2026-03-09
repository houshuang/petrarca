#!/usr/bin/env python3
"""Experiment: NLI-based entailment for claim comparison.

Tests whether an LLM judge can better classify claim relationships than
pure cosine similarity, especially in the ambiguous middle range (0.60-0.80).

Approach:
1. Select claim pairs from different similarity ranges
2. Have Gemini Flash classify each pair as: ENTAILS / EXTENDS / CONTRADICTS / UNRELATED
3. Compare with cosine-only classification
4. Measure agreement and find where LLM adds value

Usage:
    python3 scripts/experiment_nli_entailment.py
    python3 scripts/experiment_nli_entailment.py --model nomic  # use nomic embeddings
"""

import json
import os
import sys
import random
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"

# Load API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY", "")

NLI_PROMPT = """You are a knowledge relationship classifier. Given two claims, classify their relationship.

Claim A: {claim_a}
Claim B: {claim_b}

Classify their relationship as EXACTLY ONE of:
- ENTAILS: Claim B is essentially restating what Claim A says (same core knowledge)
- EXTENDS: Claim B adds new information to the same topic as Claim A (elaboration, detail, example)
- CONTRADICTS: Claim B directly contradicts or disagrees with Claim A
- UNRELATED: Claims are about different topics or have no meaningful relationship

Also rate your confidence (0.0-1.0) and give a one-sentence reason.

Respond in JSON format:
{{"relationship": "ENTAILS|EXTENDS|CONTRADICTS|UNRELATED", "confidence": 0.85, "reason": "..."}}"""


def load_data(model: str = "gemini"):
    """Load articles, claims, and embeddings."""
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

    # Cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    similarity = normalized @ normalized.T

    return claims, claim_to_idx, similarity


def sample_pairs(claims, similarity, n_per_bucket=10):
    """Sample claim pairs from different similarity buckets."""
    random.seed(42)
    n = len(claims)

    # Define buckets
    buckets = {
        "high (0.75-1.0)": (0.75, 1.0),
        "medium-high (0.65-0.75)": (0.65, 0.75),
        "medium (0.55-0.65)": (0.55, 0.65),
        "low (0.40-0.55)": (0.40, 0.55),
    }

    sampled = {}
    for bucket_name, (lo, hi) in buckets.items():
        candidates = []
        for i in range(n):
            for j in range(i + 1, n):
                # Skip same-article pairs
                if claims[i]["article_id"] == claims[j]["article_id"]:
                    continue
                sim = float(similarity[i, j])
                if lo <= sim < hi:
                    candidates.append((i, j, sim))

        # Sample from candidates
        if len(candidates) > n_per_bucket:
            candidates = random.sample(candidates, n_per_bucket)
        sampled[bucket_name] = candidates

    return sampled


def judge_pair(claim_a_text: str, claim_b_text: str) -> dict:
    """Use Gemini Flash to judge the relationship between two claims."""
    import litellm

    prompt = NLI_PROMPT.format(claim_a=claim_a_text, claim_b=claim_b_text)

    try:
        resp = litellm.completion(
            model="gemini/gemini-2.0-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
            api_key=GEMINI_API_KEY,
        )
        text = resp.choices[0].message.content.strip()
        # Parse JSON from response
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except Exception as e:
        return {"relationship": "ERROR", "confidence": 0.0, "reason": str(e)}


def cosine_classify(sim: float, model: str = "gemini") -> str:
    """Classify based on pure cosine similarity."""
    if model == "nomic":
        if sim >= 0.78:
            return "ENTAILS"
        elif sim >= 0.68:
            return "EXTENDS"
        else:
            return "UNRELATED"
    else:  # gemini
        if sim >= 0.72:
            return "ENTAILS"
        elif sim >= 0.62:
            return "EXTENDS"
        else:
            return "UNRELATED"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nomic", choices=["gemini", "nomic"])
    parser.add_argument("--pairs-per-bucket", type=int, default=8)
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        print("Error: GEMINI_KEY or GEMINI_API_KEY required", file=sys.stderr)
        sys.exit(1)

    print(f"Loading data (embeddings: {args.model})...", file=sys.stderr)
    claims, claim_to_idx, similarity = load_data(args.model)
    print(f"  {len(claims)} claims loaded", file=sys.stderr)

    print(f"\nSampling {args.pairs_per_bucket} pairs per similarity bucket...", file=sys.stderr)
    buckets = sample_pairs(claims, similarity, args.pairs_per_bucket)

    results = {}
    total_pairs = 0
    agreements = 0
    disagreements = []

    for bucket_name, pairs in buckets.items():
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Bucket: {bucket_name} ({len(pairs)} pairs)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        bucket_results = []

        for i, j, sim in pairs:
            claim_a = claims[i]["normalized_text"]
            claim_b = claims[j]["normalized_text"]

            # LLM judge
            judgment = judge_pair(claim_a, claim_b)
            time.sleep(0.3)  # rate limit

            # Cosine-only classification
            cosine_class = cosine_classify(sim, args.model)

            llm_class = judgment.get("relationship", "ERROR")
            agree = (
                (cosine_class == "ENTAILS" and llm_class == "ENTAILS") or
                (cosine_class == "EXTENDS" and llm_class == "EXTENDS") or
                (cosine_class == "UNRELATED" and llm_class == "UNRELATED")
            )

            if agree:
                agreements += 1
            else:
                disagreements.append({
                    "claim_a": claim_a[:80],
                    "claim_b": claim_b[:80],
                    "cosine_sim": round(sim, 4),
                    "cosine_class": cosine_class,
                    "llm_class": llm_class,
                    "llm_confidence": judgment.get("confidence", 0),
                    "llm_reason": judgment.get("reason", ""),
                })

            total_pairs += 1

            entry = {
                "claim_a": claim_a[:100],
                "claim_b": claim_b[:100],
                "article_a": claims[i]["article_title"][:40],
                "article_b": claims[j]["article_title"][:40],
                "cosine_sim": round(sim, 4),
                "cosine_class": cosine_class,
                "llm_class": llm_class,
                "llm_confidence": judgment.get("confidence", 0),
                "llm_reason": judgment.get("reason", ""),
                "agree": agree,
            }
            bucket_results.append(entry)

            status = "✓" if agree else "✗"
            print(f"  {status} sim={sim:.3f} cosine={cosine_class:10s} llm={llm_class:12s} "
                  f"conf={judgment.get('confidence', 0):.2f}", file=sys.stderr)
            if not agree:
                print(f"      A: {claim_a[:70]}", file=sys.stderr)
                print(f"      B: {claim_b[:70]}", file=sys.stderr)
                print(f"      Reason: {judgment.get('reason', '')[:80]}", file=sys.stderr)

        results[bucket_name] = bucket_results

    # Summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  SUMMARY", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Total pairs judged: {total_pairs}")
    print(f"  Agreement (cosine vs LLM): {agreements}/{total_pairs} "
          f"({agreements/total_pairs*100:.1f}%)")
    print(f"  Disagreements: {len(disagreements)}")

    # Analyze disagreement patterns
    if disagreements:
        print(f"\n  Disagreement patterns:")
        cosine_says = {}
        for d in disagreements:
            key = f"{d['cosine_class']} → {d['llm_class']}"
            cosine_says[key] = cosine_says.get(key, 0) + 1
        for k, v in sorted(cosine_says.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}")

    # LLM classification distribution
    llm_dist = {}
    for bucket_results in results.values():
        for r in bucket_results:
            llm_dist[r["llm_class"]] = llm_dist.get(r["llm_class"], 0) + 1
    print(f"\n  LLM classification distribution:")
    for k, v in sorted(llm_dist.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")

    # CONTRADICTS findings (most interesting for validation)
    contradicts = [r for results_list in results.values()
                   for r in results_list if r["llm_class"] == "CONTRADICTS"]
    if contradicts:
        print(f"\n  CONTRADICTS found ({len(contradicts)}):")
        for c in contradicts:
            print(f"    [{c['cosine_sim']:.3f}] {c['claim_a'][:60]}")
            print(f"              ↔ {c['claim_b'][:60]}")
            print(f"              Reason: {c['llm_reason'][:80]}")

    # Save results
    output = {
        "model": args.model,
        "total_pairs": total_pairs,
        "agreement_rate": round(agreements / max(total_pairs, 1) * 100, 1),
        "disagreements": disagreements,
        "contradicts_found": contradicts,
        "llm_distribution": llm_dist,
        "buckets": results,
    }
    output_path = DATA_DIR / "experiment_nli_entailment.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
