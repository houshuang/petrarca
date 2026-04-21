#!/usr/bin/env python3
"""Two-stage article similarity pipeline experiment.

Tests whether combining embedding cosine (fast, free) with LLM judgment (accurate, targeted)
can exceed either alone on 18 human-rated article pairs.

Experiments:
1. Two-stage accuracy: embed filter -> LLM judge at various thresholds
2. Cost analysis: how many pairs pass each filter for 257 articles
3. Ensemble methods: cosine + topic Jaccard, content_type match, shared entities

Results saved to: scripts/ground-truth/two_stage_pipeline_results.json
"""

import json
import os
import sys
import time
import re
import numpy as np
from pathlib import Path
from itertools import combinations
from scipy.stats import spearmanr
from scipy.spatial.distance import cosine as cosine_dist

# Setup paths
os.chdir('/Users/stian/src/petrarca/scripts')
sys.path.insert(0, '.')

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.env'))

# TODO(session-88): migrate to claude_llm when this script gets revived
from gemini_llm import call_llm
from limbic.amygdala import EmbeddingModel

# ---------- Constants ----------
ARTICLES_PATH = Path('/Users/stian/src/petrarca/app/data/articles.json')
OUTPUT_PATH = Path('/Users/stian/src/petrarca/scripts/ground-truth/two_stage_pipeline_results.json')

GROUND_TRUTH = [
    ("285b8ae54c07", "b9d2abdd810b", 0),
    ("4e3e14e51653", "b5f346e0da19", 2),
    ("285b8ae54c07", "43d791697511", 0),
    ("265493334801", "51004180677e", 0),
    ("84d020b998c3", "a3f9376d02cb", 0),
    ("84d020b998c3", "d0f2b608730b", 1),
    ("55fb8f174d74", "b5ec6d0add6d", 1),
    ("e0d8e9f5e16b", "ed72c07c5d8a", 0),
    ("55fb8f174d74", "a3f9376d02cb", 1),
    ("e0d8e9f5e16b", "ffea1cbfe4f7", 0),
    ("55fb8f174d74", "ffea1cbfe4f7", 1),
    ("55fb8f174d74", "75972a5d6aa1", 0),
    ("38c43325a50c", "b5ec6d0add6d", 1),
    ("d0f2b608730b", "885101003525", 1),
    ("e0d8e9f5e16b", "0708161ff37b", 0),
    ("38c43325a50c", "d0f2b608730b", 0),
    ("b5ec6d0add6d", "885101003525", 0),
    ("38c43325a50c", "e0d8e9f5e16b", 0),
]


def cosine_sim(a, b):
    return 1.0 - cosine_dist(a, b)


def best_threshold_accuracy(sims, labels):
    """Find best binary threshold. labels: list of 0/1."""
    thresholds = np.arange(0.0, 1.001, 0.005)
    best_acc = 0.0
    best_t = 0.0
    for t in thresholds:
        preds = [1 if s >= t else 0 for s in sims]
        acc = sum(1 for p, l in zip(preds, labels) if p == l) / len(labels)
        if acc > best_acc or (acc == best_acc and t > best_t):
            best_acc = acc
            best_t = t
    return best_acc, best_t


def evaluate(sims, ratings):
    """Evaluate similarity scores against ground truth ratings."""
    labels = [1 if r >= 1 else 0 for r in ratings]
    acc, thresh = best_threshold_accuracy(sims, labels)
    rho, p_val = spearmanr(sims, ratings)
    return {
        "accuracy": round(acc, 4),
        "threshold": round(thresh, 4),
        "spearman_rho": round(rho, 4),
        "spearman_p": round(p_val, 4),
    }


# ---------- Load articles ----------
def load_articles():
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)
    return {a["id"]: a for a in articles}


# ---------- LLM Judge ----------
LLM_CACHE = {}  # (id_a, id_b) -> score


def llm_judge(article_a, article_b):
    """Rate thematic overlap 0-4 using Gemini Flash Lite."""
    pair_key = tuple(sorted([article_a["id"], article_b["id"]]))
    if pair_key in LLM_CACHE:
        return LLM_CACHE[pair_key]

    claims_a = article_a.get("key_claims", [])[:4]
    claims_b = article_b.get("key_claims", [])[:4]

    prompt = f"""Rate thematic overlap 0-4:
0=unrelated, 1=same field different topics, 2=shared themes, 3=significant overlap, 4=near-duplicate

Article A: {article_a['title']} — {article_a.get('one_line_summary', '')}
Claims: {json.dumps(claims_a)}

Article B: {article_b['title']} — {article_b.get('one_line_summary', '')}
Claims: {json.dumps(claims_b)}

Return ONLY a number 0-4."""

    result = call_llm(prompt, max_tokens=10)
    if result is None:
        print(f"  WARNING: LLM returned None for {pair_key}", file=sys.stderr)
        LLM_CACHE[pair_key] = 0
        return 0

    # Parse numeric score
    match = re.search(r'[0-4]', result.strip())
    score = int(match.group()) if match else 0
    LLM_CACHE[pair_key] = score
    time.sleep(0.15)  # Rate limit
    return score


# ===================================================================
#  EXPERIMENT 1: Two-stage accuracy
# ===================================================================

def run_experiment_1(articles_by_id, embed_sims, ratings):
    """Test two-stage pipeline configurations."""
    print("\n" + "=" * 70)
    print("  EXPERIMENT 1: Two-Stage Accuracy")
    print("=" * 70)

    labels = [1 if r >= 1 else 0 for r in ratings]
    results = {}

    # --- Baseline: embedding only ---
    embed_result = evaluate(embed_sims, ratings)
    results["baseline_embedding"] = embed_result
    print(f"\n  Baseline (embedding only): {embed_result['accuracy']:.1%} "
          f"(threshold={embed_result['threshold']:.3f}, rho={embed_result['spearman_rho']:.4f})")

    # --- Baseline: LLM only ---
    print("\n  Running LLM judge on all 18 pairs...")
    llm_scores = []
    for a_id, b_id, rating in GROUND_TRUTH:
        score = llm_judge(articles_by_id[a_id], articles_by_id[b_id])
        llm_scores.append(score)
        print(f"    {a_id[:6]}..{b_id[:6]} -> LLM={score} (human={rating})", file=sys.stderr)

    llm_sims_normalized = [s / 4.0 for s in llm_scores]  # Normalize to 0-1
    llm_result = evaluate(llm_sims_normalized, ratings)
    results["baseline_llm"] = {
        **llm_result,
        "raw_scores": llm_scores,
    }
    print(f"  Baseline (LLM only): {llm_result['accuracy']:.1%} "
          f"(threshold={llm_result['threshold']:.3f}, rho={llm_result['spearman_rho']:.4f})")

    # --- Config 1-3: Embed filter -> LLM judge all candidates ---
    for filter_thresh in [0.35, 0.40, 0.45]:
        config_name = f"embed_filter_{filter_thresh:.2f}_then_llm"
        print(f"\n  Config: filter >= {filter_thresh} -> LLM judge")

        final_scores = []
        llm_calls = 0
        pair_details = []

        for i, (a_id, b_id, rating) in enumerate(GROUND_TRUTH):
            sim = embed_sims[i]
            if sim >= filter_thresh:
                # Pass to LLM
                llm_score = llm_judge(articles_by_id[a_id], articles_by_id[b_id])
                llm_calls += 1
                final_sim = llm_score / 4.0
                method = "llm"
            else:
                # Below threshold -> unrelated
                final_sim = 0.0
                llm_score = None
                method = "filtered_out"

            final_scores.append(final_sim)
            pair_details.append({
                "a": a_id, "b": b_id, "rating": rating,
                "embed_sim": round(sim, 4),
                "llm_score": llm_score,
                "final_sim": round(final_sim, 4),
                "method": method,
            })

        passed = sum(1 for s in embed_sims if s >= filter_thresh)
        result = evaluate(final_scores, ratings)
        result["llm_calls"] = llm_calls
        result["passed_filter"] = passed
        result["pairs"] = pair_details
        results[config_name] = result
        print(f"    Passed filter: {passed}/18, LLM calls: {llm_calls}")
        print(f"    Accuracy: {result['accuracy']:.1%} (rho={result['spearman_rho']:.4f})")

    # --- Config 4: Weighted average of embed + LLM ---
    print("\n  Config 4: Weighted average (embed + LLM)")
    best_weighted = None
    best_weighted_acc = 0

    for w_embed in np.arange(0.1, 0.91, 0.1):
        w_llm = 1.0 - w_embed
        combined = [
            w_embed * embed_sims[i] + w_llm * llm_sims_normalized[i]
            for i in range(len(GROUND_TRUTH))
        ]
        result = evaluate(combined, ratings)
        if result["accuracy"] > best_weighted_acc or (
            result["accuracy"] == best_weighted_acc
            and result["spearman_rho"] > (best_weighted or {}).get("spearman_rho", -1)
        ):
            best_weighted_acc = result["accuracy"]
            best_weighted = {
                "w_embed": round(w_embed, 2),
                "w_llm": round(w_llm, 2),
                **result,
                "combined_scores": [round(c, 4) for c in combined],
            }

    results["config4_weighted_avg"] = best_weighted
    print(f"    Best weights: embed={best_weighted['w_embed']}, llm={best_weighted['w_llm']}")
    print(f"    Accuracy: {best_weighted['accuracy']:.1%} (rho={best_weighted['spearman_rho']:.4f})")

    # --- Config 5: Take max of embed and LLM ---
    print("\n  Config 5: Max(embed, LLM)")
    max_scores = [
        max(embed_sims[i], llm_sims_normalized[i])
        for i in range(len(GROUND_TRUTH))
    ]
    result_max = evaluate(max_scores, ratings)
    result_max["scores"] = [round(s, 4) for s in max_scores]
    results["config5_max"] = result_max
    print(f"    Accuracy: {result_max['accuracy']:.1%} (rho={result_max['spearman_rho']:.4f})")

    # --- Config 6: Ambiguous zone only ---
    print("\n  Config 6: LLM for ambiguous zone (0.35-0.60), pass through high/low")
    final_scores_6 = []
    llm_calls_6 = 0
    pair_details_6 = []

    for i, (a_id, b_id, rating) in enumerate(GROUND_TRUTH):
        sim = embed_sims[i]
        if sim >= 0.60:
            # High confidence: related
            final_sim = sim
            method = "high_pass"
            llm_score = None
        elif sim < 0.35:
            # Low confidence: unrelated
            final_sim = sim
            method = "low_pass"
            llm_score = None
        else:
            # Ambiguous zone: use LLM
            llm_score = llm_judge(articles_by_id[a_id], articles_by_id[b_id])
            llm_calls_6 += 1
            final_sim = llm_score / 4.0
            method = "llm_ambiguous"

        final_scores_6.append(final_sim)
        pair_details_6.append({
            "a": a_id, "b": b_id, "rating": rating,
            "embed_sim": round(sim, 4),
            "llm_score": llm_score,
            "final_sim": round(final_sim, 4),
            "method": method,
        })

    result_6 = evaluate(final_scores_6, ratings)
    result_6["llm_calls"] = llm_calls_6
    result_6["pairs"] = pair_details_6
    results["config6_ambiguous_zone"] = result_6
    print(f"    LLM calls: {llm_calls_6}/18 (ambiguous zone only)")
    print(f"    Accuracy: {result_6['accuracy']:.1%} (rho={result_6['spearman_rho']:.4f})")

    return results


# ===================================================================
#  EXPERIMENT 2: Cost analysis
# ===================================================================

def run_experiment_2(articles_by_id, model):
    """Cost analysis for 257 articles at various thresholds."""
    print("\n" + "=" * 70)
    print("  EXPERIMENT 2: Cost Analysis (257 articles)")
    print("=" * 70)

    all_articles = list(articles_by_id.values())
    n = len(all_articles)
    total_pairs = n * (n - 1) // 2
    print(f"\n  Total articles: {n}, Total pairs: {total_pairs:,}")

    # Embed all article summaries
    print("  Embedding all article summaries...", file=sys.stderr)
    aid_list = [a["id"] for a in all_articles]
    texts = [a.get("full_summary", "") for a in all_articles]
    embeddings = model.embed_batch(texts)
    emb_map = {aid: embeddings[i] for i, aid in enumerate(aid_list)}

    # Compute all pairwise cosine similarities
    print("  Computing pairwise similarities...", file=sys.stderr)
    all_sims = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine_sim(embeddings[i], embeddings[j])
            all_sims.append(sim)

    all_sims = np.array(all_sims)

    # Gemini Flash Lite pricing (per 1M tokens)
    # Input: $0.075/1M tokens, Output: $0.30/1M tokens
    # Estimate ~300 input tokens + ~5 output tokens per pair
    INPUT_COST_PER_M = 0.075
    OUTPUT_COST_PER_M = 0.30
    TOKENS_INPUT_PER_PAIR = 300
    TOKENS_OUTPUT_PER_PAIR = 5

    cost_per_pair = (
        TOKENS_INPUT_PER_PAIR / 1_000_000 * INPUT_COST_PER_M +
        TOKENS_OUTPUT_PER_PAIR / 1_000_000 * OUTPUT_COST_PER_M
    )

    results = {
        "total_articles": n,
        "total_pairs": total_pairs,
        "cost_per_pair_usd": round(cost_per_pair, 8),
        "sim_distribution": {
            "min": round(float(all_sims.min()), 4),
            "max": round(float(all_sims.max()), 4),
            "mean": round(float(all_sims.mean()), 4),
            "median": round(float(np.median(all_sims)), 4),
            "std": round(float(all_sims.std()), 4),
            "p90": round(float(np.percentile(all_sims, 90)), 4),
            "p95": round(float(np.percentile(all_sims, 95)), 4),
            "p99": round(float(np.percentile(all_sims, 99)), 4),
        },
        "thresholds": {},
    }

    print(f"\n  Similarity distribution:")
    print(f"    min={all_sims.min():.4f}  mean={all_sims.mean():.4f}  "
          f"median={np.median(all_sims):.4f}  max={all_sims.max():.4f}")
    print(f"    p90={np.percentile(all_sims, 90):.4f}  p95={np.percentile(all_sims, 95):.4f}  "
          f"p99={np.percentile(all_sims, 99):.4f}")

    print(f"\n  {'Threshold':>10} {'Pairs':>8} {'% of total':>11} {'LLM cost':>10} {'Time (est)':>12}")
    print(f"  {'─'*10} {'─'*8} {'─'*11} {'─'*10} {'─'*12}")

    for thresh in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        pairs_passing = int(np.sum(all_sims >= thresh))
        pct = pairs_passing / total_pairs * 100
        cost = pairs_passing * cost_per_pair
        # ~0.3s per LLM call with batching
        time_est_s = pairs_passing * 0.3
        time_est_min = time_est_s / 60

        results["thresholds"][str(thresh)] = {
            "pairs_passing": pairs_passing,
            "pct_of_total": round(pct, 2),
            "estimated_cost_usd": round(cost, 4),
            "estimated_time_minutes": round(time_est_min, 1),
        }

        print(f"  {thresh:>10.2f} {pairs_passing:>8,} {pct:>10.1f}% "
              f"${cost:>9.4f} {time_est_min:>9.1f} min")

    # Also add the ambiguous zone analysis
    ambiguous_low = 0.35
    ambiguous_high = 0.60
    pairs_ambiguous = int(np.sum((all_sims >= ambiguous_low) & (all_sims < ambiguous_high)))
    pairs_high = int(np.sum(all_sims >= ambiguous_high))
    cost_ambiguous = pairs_ambiguous * cost_per_pair
    time_ambiguous = pairs_ambiguous * 0.3 / 60

    results["ambiguous_zone"] = {
        "low": ambiguous_low,
        "high": ambiguous_high,
        "pairs_in_zone": pairs_ambiguous,
        "pairs_above_high": pairs_high,
        "pairs_below_low": total_pairs - pairs_ambiguous - pairs_high,
        "estimated_cost_usd": round(cost_ambiguous, 4),
        "estimated_time_minutes": round(time_ambiguous, 1),
    }

    print(f"\n  Ambiguous zone ({ambiguous_low}-{ambiguous_high}):")
    print(f"    Pairs in zone: {pairs_ambiguous:,}")
    print(f"    Pairs above {ambiguous_high}: {pairs_high:,}")
    print(f"    LLM cost for zone only: ${cost_ambiguous:.4f}")
    print(f"    Time for zone only: {time_ambiguous:.1f} min")

    # Full corpus LLM cost (no filtering)
    full_cost = total_pairs * cost_per_pair
    full_time = total_pairs * 0.3 / 60
    results["no_filter"] = {
        "pairs": total_pairs,
        "estimated_cost_usd": round(full_cost, 4),
        "estimated_time_minutes": round(full_time, 1),
    }
    print(f"\n  No filtering (all pairs): ${full_cost:.4f}, {full_time:.0f} min")

    return results


# ===================================================================
#  EXPERIMENT 3: Ensemble methods
# ===================================================================

def topic_jaccard(article_a, article_b):
    """Jaccard similarity of topic sets."""
    topics_a = set(article_a.get("topics", []))
    topics_b = set(article_b.get("topics", []))
    if not topics_a or not topics_b:
        return 0.0
    return len(topics_a & topics_b) / len(topics_a | topics_b)


def content_type_match(article_a, article_b):
    """1.0 if same content_type, 0.0 otherwise."""
    ct_a = article_a.get("content_type", "")
    ct_b = article_b.get("content_type", "")
    if not ct_a or not ct_b:
        return 0.0
    return 1.0 if ct_a == ct_b else 0.0


def shared_entity_count(article_a, article_b):
    """Count of shared entity names (normalized lowercase)."""
    ents_a = set(e["name"].lower() for e in article_a.get("entities", []))
    ents_b = set(e["name"].lower() for e in article_b.get("entities", []))
    return len(ents_a & ents_b)


def run_experiment_3(articles_by_id, embed_sims, ratings):
    """Ensemble methods: combine embedding similarity with cheap signals."""
    print("\n" + "=" * 70)
    print("  EXPERIMENT 3: Ensemble Methods")
    print("=" * 70)

    labels = [1 if r >= 1 else 0 for r in ratings]
    results = {}

    # Compute additional signals for each pair
    topic_jaccards = []
    content_matches = []
    entity_counts = []

    for a_id, b_id, rating in GROUND_TRUTH:
        a = articles_by_id[a_id]
        b = articles_by_id[b_id]
        topic_jaccards.append(topic_jaccard(a, b))
        content_matches.append(content_type_match(a, b))
        entity_counts.append(shared_entity_count(a, b))

    # Normalize entity counts to 0-1 range
    max_ent = max(entity_counts) if max(entity_counts) > 0 else 1
    entity_normalized = [e / max_ent for e in entity_counts]

    print(f"\n  Signal distributions:")
    print(f"    Topic Jaccard:  min={min(topic_jaccards):.3f}  max={max(topic_jaccards):.3f}  "
          f"mean={np.mean(topic_jaccards):.3f}")
    print(f"    Content match:  {sum(content_matches)}/{len(content_matches)} pairs match")
    print(f"    Entity overlap: min={min(entity_counts)}  max={max(entity_counts)}  "
          f"mean={np.mean(entity_counts):.1f}")

    # Individual signal accuracies
    for name, signal in [
        ("topic_jaccard_only", topic_jaccards),
        ("content_type_only", [float(x) for x in content_matches]),
        ("entity_count_only", entity_normalized),
    ]:
        result = evaluate(signal, ratings)
        results[name] = result
        print(f"\n  {name}: acc={result['accuracy']:.1%} "
              f"(thresh={result['threshold']:.3f}, rho={result['spearman_rho']:.4f})")

    # --- Ensemble: Cosine + Topic Jaccard ---
    print("\n  Searching best weights for Cosine + Topic Jaccard...")
    best_ens = None
    best_ens_acc = 0

    for w_cos in np.arange(0.1, 0.91, 0.05):
        w_topic = 1.0 - w_cos
        combined = [
            w_cos * embed_sims[i] + w_topic * topic_jaccards[i]
            for i in range(len(GROUND_TRUTH))
        ]
        result = evaluate(combined, ratings)
        if result["accuracy"] > best_ens_acc or (
            result["accuracy"] == best_ens_acc
            and result["spearman_rho"] > (best_ens or {}).get("spearman_rho", -1)
        ):
            best_ens_acc = result["accuracy"]
            best_ens = {
                "w_cosine": round(w_cos, 3),
                "w_topic_jaccard": round(w_topic, 3),
                **result,
            }

    results["cosine_plus_topic_jaccard"] = best_ens
    print(f"    Best: w_cos={best_ens['w_cosine']}, w_topic={best_ens['w_topic_jaccard']}")
    print(f"    Accuracy: {best_ens['accuracy']:.1%} (rho={best_ens['spearman_rho']:.4f})")

    # --- Ensemble: Cosine + Content Type bonus ---
    print("\n  Searching best weights for Cosine + Content Type bonus...")
    best_ct = None
    best_ct_acc = 0

    for bonus in np.arange(0.0, 0.31, 0.02):
        combined = [
            embed_sims[i] + bonus * content_matches[i]
            for i in range(len(GROUND_TRUTH))
        ]
        result = evaluate(combined, ratings)
        if result["accuracy"] > best_ct_acc or (
            result["accuracy"] == best_ct_acc
            and result["spearman_rho"] > (best_ct or {}).get("spearman_rho", -1)
        ):
            best_ct_acc = result["accuracy"]
            best_ct = {
                "content_type_bonus": round(float(bonus), 3),
                **result,
            }

    results["cosine_plus_content_type"] = best_ct
    print(f"    Best bonus: {best_ct['content_type_bonus']}")
    print(f"    Accuracy: {best_ct['accuracy']:.1%} (rho={best_ct['spearman_rho']:.4f})")

    # --- Ensemble: Cosine + Entity count ---
    print("\n  Searching best weights for Cosine + Entity overlap...")
    best_ent = None
    best_ent_acc = 0

    for w_cos in np.arange(0.1, 0.91, 0.05):
        w_ent = 1.0 - w_cos
        combined = [
            w_cos * embed_sims[i] + w_ent * entity_normalized[i]
            for i in range(len(GROUND_TRUTH))
        ]
        result = evaluate(combined, ratings)
        if result["accuracy"] > best_ent_acc or (
            result["accuracy"] == best_ent_acc
            and result["spearman_rho"] > (best_ent or {}).get("spearman_rho", -1)
        ):
            best_ent_acc = result["accuracy"]
            best_ent = {
                "w_cosine": round(w_cos, 3),
                "w_entity": round(w_ent, 3),
                **result,
            }

    results["cosine_plus_entity_overlap"] = best_ent
    print(f"    Best: w_cos={best_ent['w_cosine']}, w_entity={best_ent['w_entity']}")
    print(f"    Accuracy: {best_ent['accuracy']:.1%} (rho={best_ent['spearman_rho']:.4f})")

    # --- Ensemble: All three cheap signals ---
    print("\n  Searching best weights for Cosine + Topic + Entity (3-way)...")
    best_3way = None
    best_3way_acc = 0

    for w_cos in np.arange(0.3, 0.91, 0.05):
        remaining = 1.0 - w_cos
        for w_topic_frac in np.arange(0.0, 1.01, 0.1):
            w_topic = remaining * w_topic_frac
            w_ent = remaining * (1.0 - w_topic_frac)

            combined = [
                w_cos * embed_sims[i] + w_topic * topic_jaccards[i] + w_ent * entity_normalized[i]
                for i in range(len(GROUND_TRUTH))
            ]
            result = evaluate(combined, ratings)
            if result["accuracy"] > best_3way_acc or (
                result["accuracy"] == best_3way_acc
                and result["spearman_rho"] > (best_3way or {}).get("spearman_rho", -1)
            ):
                best_3way_acc = result["accuracy"]
                best_3way = {
                    "w_cosine": round(w_cos, 3),
                    "w_topic_jaccard": round(w_topic, 3),
                    "w_entity": round(w_ent, 3),
                    **result,
                }

    results["cosine_plus_topic_plus_entity"] = best_3way
    print(f"    Best: w_cos={best_3way['w_cosine']}, w_topic={best_3way['w_topic_jaccard']}, "
          f"w_entity={best_3way['w_entity']}")
    print(f"    Accuracy: {best_3way['accuracy']:.1%} (rho={best_3way['spearman_rho']:.4f})")

    # --- Show per-pair signal values for analysis ---
    pair_signals = []
    for i, (a_id, b_id, rating) in enumerate(GROUND_TRUTH):
        pair_signals.append({
            "a": a_id, "b": b_id, "rating": rating,
            "embed_sim": round(embed_sims[i], 4),
            "topic_jaccard": round(topic_jaccards[i], 4),
            "content_match": int(content_matches[i]),
            "entity_count": entity_counts[i],
        })
    results["pair_signals"] = pair_signals

    return results


# ===================================================================
#  MAIN
# ===================================================================

def main():
    print("Loading articles...", file=sys.stderr)
    articles_by_id = load_articles()
    print(f"  {len(articles_by_id)} articles loaded", file=sys.stderr)

    # Verify all ground truth articles exist
    needed_ids = set()
    for a, b, _ in GROUND_TRUTH:
        needed_ids.add(a)
        needed_ids.add(b)
    missing = needed_ids - set(articles_by_id.keys())
    if missing:
        print(f"ERROR: Missing articles: {missing}", file=sys.stderr)
        sys.exit(1)
    print(f"  All {len(needed_ids)} ground truth articles found", file=sys.stderr)

    # Embed article summaries for ground truth pairs
    print("Embedding article summaries...", file=sys.stderr)
    model = EmbeddingModel()
    aid_list = sorted(needed_ids)
    texts = [articles_by_id[aid].get("full_summary", "") for aid in aid_list]
    embeddings = model.embed_batch(texts)
    emb_map = {aid: embeddings[i] for i, aid in enumerate(aid_list)}

    # Compute cosine similarities for ground truth pairs
    ratings = [r for _, _, r in GROUND_TRUTH]
    embed_sims = []
    for a_id, b_id, _ in GROUND_TRUTH:
        sim = cosine_sim(emb_map[a_id], emb_map[b_id])
        embed_sims.append(float(sim))

    # Show pair details
    print("\n  Ground truth pairs with embedding similarity:")
    for i, (a_id, b_id, rating) in enumerate(GROUND_TRUTH):
        title_a = articles_by_id[a_id]["title"][:35]
        title_b = articles_by_id[b_id]["title"][:35]
        print(f"    {embed_sims[i]:.3f} (human={rating}) {title_a} <-> {title_b}")

    all_results = {}

    # Run experiments
    all_results["experiment_1"] = run_experiment_1(articles_by_id, embed_sims, ratings)
    all_results["experiment_2"] = run_experiment_2(articles_by_id, model)
    all_results["experiment_3"] = run_experiment_3(articles_by_id, embed_sims, ratings)

    # --- Summary comparison table ---
    print("\n" + "=" * 90)
    print("  SUMMARY: All Methods Compared")
    print("=" * 90)
    print(f"\n  {'Method':<45} {'Accuracy':>10} {'Rho':>8} {'LLM calls':>10}")
    print(f"  {'─'*45} {'─'*10} {'─'*8} {'─'*10}")

    summary_rows = []

    # Experiment 1 results
    exp1 = all_results["experiment_1"]
    for name, res in exp1.items():
        llm_calls = res.get("llm_calls", 18 if "llm" in name else 0)
        summary_rows.append((
            f"E1: {name}",
            res["accuracy"],
            res["spearman_rho"],
            llm_calls,
        ))

    # Experiment 3 results (skip pair_signals)
    exp3 = all_results["experiment_3"]
    for name, res in exp3.items():
        if name == "pair_signals":
            continue
        summary_rows.append((
            f"E3: {name}",
            res["accuracy"],
            res["spearman_rho"],
            0,
        ))

    # Sort by accuracy desc, then rho desc
    summary_rows.sort(key=lambda x: (x[1], x[2]), reverse=True)

    for name, acc, rho, llm_calls in summary_rows:
        calls_str = str(llm_calls) if llm_calls > 0 else "0"
        print(f"  {name:<45} {acc:>9.1%} {rho:>8.4f} {calls_str:>10}")

    # Save results
    all_results["metadata"] = {
        "date": "2026-03-21",
        "model": "paraphrase-multilingual-MiniLM-L12-v2",
        "llm_model": "gemini-3.1-flash-lite-preview",
        "n_pairs": len(GROUND_TRUTH),
        "n_articles_total": len(articles_by_id),
        "llm_cache_size": len(LLM_CACHE),
        "llm_cache": {f"{a},{b}": v for (a, b), v in LLM_CACHE.items()},
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n  Results saved to {OUTPUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
