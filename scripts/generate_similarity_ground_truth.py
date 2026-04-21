#!/usr/bin/env python3
"""Generate ground truth dataset for article-level thematic similarity.

Computes summary embeddings via amygdala, stratifies pairs by cosine bands,
then uses Gemini Flash to rate thematic overlap for ~300 pairs.

Runs in stages with checkpointing to handle timeouts gracefully:
  Stage 1: Compute embeddings and sample pairs → saves pairs_to_rate.json
  Stage 2: Rate pairs via LLM (resumes from checkpoint) → saves final output

Usage: python generate_similarity_ground_truth.py
"""

import json
import os
import sys
import time
import random
from datetime import datetime, timezone
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

# Setup paths
os.chdir("/Users/stian/src/petrarca/scripts")
sys.path.insert(0, ".")

# Load env
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/.env"))
load_dotenv("/Users/stian/src/petrarca/.env")

GT_DIR = Path("/Users/stian/src/petrarca/scripts/ground-truth")
PAIRS_FILE = GT_DIR / "pairs_to_rate.json"
PROGRESS_FILE = GT_DIR / "rating_progress.json"
OUTPUT_FILE = GT_DIR / "article_similarity_ratings.json"


def load_articles():
    with open("/Users/stian/src/petrarca/app/data/articles.json") as f:
        return json.load(f)


def compute_embeddings(articles):
    from limbic.amygdala import EmbeddingModel
    model = EmbeddingModel()
    texts = [f"{a['title']}. {a.get('full_summary', a.get('one_line_summary', ''))}" for a in articles]
    print(f"Computing embeddings for {len(texts)} articles...")
    embeddings = model.embed_batch(texts)
    print(f"Embeddings shape: {embeddings.shape}")
    return embeddings


def compute_pairwise_cosine(embeddings):
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = embeddings / norms
    return normed @ normed.T


def get_broad_topics(article):
    return set(t.get("broad", "") for t in article.get("interest_topics", []) if t.get("broad"))


def sample_pairs(articles, sim_matrix):
    n = len(articles)
    all_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            all_pairs.append((i, j, float(sim_matrix[i, j])))

    print(f"Total possible pairs: {len(all_pairs)}")
    all_pairs.sort(key=lambda x: x[2], reverse=True)

    broad_topics = {i: get_broad_topics(a) for i, a in enumerate(articles)}
    content_types = {i: a.get("content_type", "unknown") for i, a in enumerate(articles)}

    selected = set()

    def pick(candidates, n_want, label):
        chosen = []
        for i, j, c in candidates:
            if (i, j) not in selected and len(chosen) < n_want:
                chosen.append((i, j, c))
                selected.add((i, j))
        print(f"  {label}: {len(candidates)} available, sampled {len(chosen)}")
        return chosen

    # Band 1: >= 0.70
    band1 = pick([(i,j,c) for i,j,c in all_pairs if c >= 0.70], 50, ">=0.70")

    # Band 2: ambiguous 0.45-0.55
    b2 = [(i,j,c) for i,j,c in all_pairs if 0.45 <= c <= 0.55]
    random.shuffle(b2)
    band2 = pick(b2, 50, "0.45-0.55")

    # Band 3: near miss 0.35-0.45
    b3 = [(i,j,c) for i,j,c in all_pairs if 0.35 <= c < 0.45]
    random.shuffle(b3)
    band3 = pick(b3, 50, "0.35-0.45")

    # Band 4: < 0.30 negative controls
    b4 = [(i,j,c) for i,j,c in all_pairs if c < 0.30]
    random.shuffle(b4)
    band4 = pick(b4, 50, "<0.30")

    # Band 5: shared broad topic, evenly across similarity range
    shared_pool = [(i,j,c) for i,j,c in all_pairs if (i,j) not in selected and len(broad_topics[i] & broad_topics[j]) > 0]
    shared_pool.sort(key=lambda x: x[2])
    if len(shared_pool) >= 50:
        step = len(shared_pool) / 50
        band5_candidates = [shared_pool[int(k * step)] for k in range(50)]
    else:
        band5_candidates = shared_pool
    band5 = pick(band5_candidates, 50, "shared_topic")

    # Band 6: diff type + shared topic
    b6 = [(i,j,c) for i,j,c in all_pairs if (i,j) not in selected and content_types[i] != content_types[j] and len(broad_topics[i] & broad_topics[j]) > 0]
    random.shuffle(b6)
    band6 = pick(b6, 50, "diff_type_shared_topic")

    result = []
    for i, j, c in band1 + band2 + band3 + band4 + band5 + band6:
        shared = sorted(broad_topics[i] & broad_topics[j])
        result.append({
            "i": i, "j": j,
            "a_id": articles[i]["id"],
            "b_id": articles[j]["id"],
            "a_title": articles[i]["title"],
            "b_title": articles[j]["title"],
            "cosine_similarity": round(c, 4),
            "shared_broad_topics": shared,
            "content_types": [content_types[i], content_types[j]],
        })

    print(f"Total sampled: {len(result)}")
    return result


def stage1_embed_and_sample():
    """Compute embeddings, sample pairs, save to disk."""
    random.seed(42)
    np.random.seed(42)

    articles = load_articles()
    print(f"Loaded {len(articles)} articles")

    embeddings = compute_embeddings(articles)
    sim_matrix = compute_pairwise_cosine(embeddings)

    upper = sim_matrix[np.triu_indices(len(articles), k=1)]
    stats = {
        "min": float(upper.min()), "max": float(upper.max()),
        "mean": float(upper.mean()), "std": float(upper.std()),
    }
    print(f"\nCosine stats: mean={stats['mean']:.4f}, std={stats['std']:.4f}")
    for lo, hi, label in [(0.70, 1.01, ">=0.70"), (0.55, 0.70, "0.55-0.70"),
                           (0.45, 0.55, "0.45-0.55"), (0.35, 0.45, "0.35-0.45"),
                           (0.30, 0.35, "0.30-0.35"), (-1, 0.30, "<0.30")]:
        count = int(np.sum((upper >= lo) & (upper < hi)))
        print(f"  {label}: {count} pairs")

    pairs = sample_pairs(articles, sim_matrix)

    with open(PAIRS_FILE, "w") as f:
        json.dump({"cosine_stats": stats, "pairs": pairs}, f, indent=2)
    print(f"Saved {len(pairs)} pairs to {PAIRS_FILE}")
    return pairs, stats


def build_prompt(a, b):
    def fmt_claims(article):
        claims = article.get("key_claims", [])[:5]
        return "\n".join(f"- {c}" for c in claims) if claims else "(none)"

    return f"""Rate the thematic overlap between these two articles. Consider: would reading Article A significantly reduce the novelty of reading Article B?

Article A: {a['title']}
Summary: {a.get('full_summary', a.get('one_line_summary', ''))}
Key claims:
{fmt_claims(a)}

Article B: {b['title']}
Summary: {b.get('full_summary', b.get('one_line_summary', ''))}
Key claims:
{fmt_claims(b)}

Rate on this scale:
0 = Completely unrelated topics
1 = Same broad field but different specific topics
2 = Shared themes — reading both adds value but there's thematic overlap
3 = Significant overlap — reading both would feel partly redundant
4 = Near-duplicate — covers essentially the same ground

Return ONLY a JSON object: {{"score": N, "reason": "brief explanation"}}"""


def rate_pair(pair, articles, retry_count=3):
    # TODO(session-88): migrate to claude_llm when this script gets revived
    from gemini_llm import call_llm
    a = articles[pair["i"]]
    b = articles[pair["j"]]
    prompt = build_prompt(a, b)

    for attempt in range(retry_count):
        try:
            response = call_llm(prompt, response_mime_type="application/json", max_tokens=256)
            if response:
                result = json.loads(response)
                return {"llm_rating": result["score"], "llm_reason": result.get("reason", "")}
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            pass
        except Exception as e:
            pass
        if attempt < retry_count - 1:
            time.sleep(2 ** attempt)

    return {"llm_rating": None, "llm_reason": "FAILED"}


def stage2_rate_pairs(pairs=None, stats=None):
    """Rate pairs via LLM with checkpointing."""
    articles = load_articles()

    if pairs is None:
        with open(PAIRS_FILE) as f:
            data = json.load(f)
        pairs = data["pairs"]
        stats = data["cosine_stats"]

    # Load existing progress
    progress = {}
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            progress = json.load(f)
        print(f"Resuming from checkpoint: {len(progress)} pairs already rated")

    # Filter to unrated pairs
    to_rate = [p for p in pairs if f"{p['a_id']}_{p['b_id']}" not in progress]
    print(f"Pairs to rate: {len(to_rate)} (of {len(pairs)} total)")

    if not to_rate:
        print("All pairs already rated!")
    else:
        completed = 0
        start = time.time()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            for p in to_rate:
                key = f"{p['a_id']}_{p['b_id']}"
                futures[executor.submit(rate_pair, p, articles)] = (key, p)

            for future in as_completed(futures):
                key, pair = futures[future]
                result = future.result()
                progress[key] = result
                completed += 1

                if completed % 25 == 0 or completed == len(to_rate):
                    elapsed = time.time() - start
                    rate = completed / elapsed if elapsed > 0 else 0
                    failed = sum(1 for v in progress.values() if v["llm_rating"] is None)
                    print(f"  {completed}/{len(to_rate)} done ({rate:.1f}/sec, {failed} failures)")

                    # Checkpoint
                    with open(PROGRESS_FILE, "w") as f:
                        json.dump(progress, f)

        # Final checkpoint
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f)

    # Merge ratings into pairs
    rated_pairs = []
    for p in pairs:
        key = f"{p['a_id']}_{p['b_id']}"
        rating = progress.get(key, {"llm_rating": None, "llm_reason": "MISSING"})
        entry = {
            "a_id": p["a_id"], "b_id": p["b_id"],
            "a_title": p["a_title"], "b_title": p["b_title"],
            "cosine_similarity": p["cosine_similarity"],
            "llm_rating": rating["llm_rating"],
            "llm_reason": rating["llm_reason"],
            "shared_broad_topics": p["shared_broad_topics"],
            "content_types": p["content_types"],
        }
        rated_pairs.append(entry)

    rated_pairs.sort(key=lambda x: x["cosine_similarity"], reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "gemini-3.1-flash-lite-preview",
        "sample_strategy": "stratified by cosine similarity bands",
        "human_calibration_accuracy": "83% at 0.47 threshold",
        "total_pairs": len(rated_pairs),
        "valid_ratings": sum(1 for p in rated_pairs if p.get("llm_rating") is not None),
        "cosine_stats": stats,
        "pairs": rated_pairs,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved {len(rated_pairs)} rated pairs to {OUTPUT_FILE}")

    analyze_results(rated_pairs)


def analyze_results(pairs):
    valid = [p for p in pairs if p.get("llm_rating") is not None]
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Total pairs: {len(pairs)}, Valid: {len(valid)}, Failed: {len(pairs) - len(valid)}")

    if not valid:
        return

    rating_counts = Counter(p["llm_rating"] for p in valid)
    print(f"\nRating distribution:")
    for r in range(5):
        c = rating_counts.get(r, 0)
        pct = c / len(valid) * 100
        print(f"  {r}: {c:4d} ({pct:5.1f}%) {'#' * int(pct)}")

    def band_label(cos):
        if cos >= 0.70: return ">=0.70"
        if cos >= 0.55: return "0.55-0.70"
        if cos >= 0.45: return "0.45-0.55"
        if cos >= 0.35: return "0.35-0.45"
        if cos >= 0.30: return "0.30-0.35"
        return "<0.30"

    band_ratings = defaultdict(list)
    for p in valid:
        band_ratings[band_label(p["cosine_similarity"])].append(p["llm_rating"])

    print(f"\nBy cosine band:")
    print(f"  {'Band':<12} {'N':>4}  {'Mean':>5}  {'Med':>4}  0/1/2/3/4")
    for band in [">=0.70", "0.55-0.70", "0.45-0.55", "0.35-0.45", "0.30-0.35", "<0.30"]:
        if band in band_ratings:
            rs = band_ratings[band]
            d = Counter(rs)
            print(f"  {band:<12} {len(rs):>4}  {np.mean(rs):>5.2f}  {np.median(rs):>4.1f}  {'/'.join(str(d.get(r,0)) for r in range(5))}")

    cosines = np.array([p["cosine_similarity"] for p in valid])
    ratings = np.array([p["llm_rating"] for p in valid])

    pearson = float(np.corrcoef(cosines, ratings)[0, 1])
    from scipy.stats import spearmanr
    spearman_rho, spearman_p = spearmanr(cosines, ratings)

    print(f"\nCorrelation:")
    print(f"  Pearson r:  {pearson:.4f}")
    print(f"  Spearman ρ: {spearman_rho:.4f} (p={spearman_p:.2e})")

    print(f"\nSurprises (high cos >= 0.60, low rating <= 1):")
    for p in sorted([p for p in valid if p["cosine_similarity"] >= 0.60 and p["llm_rating"] <= 1],
                    key=lambda x: -x["cosine_similarity"])[:8]:
        print(f"  cos={p['cosine_similarity']:.3f} r={p['llm_rating']}: \"{p['a_title'][:35]}\" vs \"{p['b_title'][:35]}\"")

    print(f"\nSurprises (low cos < 0.35, high rating >= 3):")
    for p in sorted([p for p in valid if p["cosine_similarity"] < 0.35 and p["llm_rating"] >= 3],
                    key=lambda x: x["cosine_similarity"])[:8]:
        print(f"  cos={p['cosine_similarity']:.3f} r={p['llm_rating']}: \"{p['a_title'][:35]}\" vs \"{p['b_title'][:35]}\"")

    print(f"\nThreshold analysis (similar = LLM >= 2):")
    print(f"  {'Thresh':<8} {'Prec':>6} {'Rec':>6} {'F1':>6} {'Acc':>6}")
    for t in [0.35, 0.40, 0.45, 0.47, 0.50, 0.55, 0.60]:
        pred = cosines >= t
        actual = ratings >= 2
        tp = int(np.sum(pred & actual))
        fp = int(np.sum(pred & ~actual))
        fn = int(np.sum(~pred & actual))
        tn = int(np.sum(~pred & ~actual))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        acc = (tp + tn) / len(valid)
        print(f"  {t:<8.2f} {prec:>6.3f} {rec:>6.3f} {f1:>6.3f} {acc:>6.3f}")


def main():
    # Stage 1: Embed & sample (fast, ~10 sec)
    if not PAIRS_FILE.exists():
        pairs, stats = stage1_embed_and_sample()
    else:
        print(f"Pairs file exists, loading from {PAIRS_FILE}")
        with open(PAIRS_FILE) as f:
            data = json.load(f)
        pairs, stats = data["pairs"], data["cosine_stats"]
        print(f"  {len(pairs)} pairs loaded")

    # Stage 2: Rate via LLM (slower, ~5 min with 10 workers)
    stage2_rate_pairs(pairs, stats)


if __name__ == "__main__":
    main()
