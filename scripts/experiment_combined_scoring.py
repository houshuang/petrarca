#!/usr/bin/env python3
"""Experiment: Combined novelty scoring with all validated approaches.

Integrates:
1. Nomic embeddings (cosine similarity)
2. LLM judge for ambiguous zone (0.68-0.78)
3. FSRS knowledge decay (30-day base stability)
4. Curiosity zone scoring (article selection)

Simulates a realistic 2-week reading scenario with daily engagement.

Usage:
    python3 scripts/experiment_combined_scoring.py
    python3 scripts/experiment_combined_scoring.py --skip-nli  # skip LLM judge (faster)
"""

import json
import os
import sys
import math
import time
import argparse
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY", "")


# ─── FSRS Knowledge State ────────────────────────────────────────────────

@dataclass
class ClaimKnowledge:
    claim_id: str
    stability: float = 30.0
    last_seen_day: int = 0
    encounter_count: int = 0
    engagement: str = "read"

    def retrievability(self, day: int) -> float:
        if self.stability <= 0:
            return 0.0
        return math.exp(-(day - self.last_seen_day) / self.stability)


class CombinedKnowledgeLedger:
    """Knowledge ledger combining embeddings + decay + NLI."""

    ENGAGEMENT_STABILITY = {
        "skim": 9.0,
        "read": 30.0,
        "highlight": 60.0,
        "annotate": 120.0,
    }
    REINFORCE_FACTOR = 2.5

    def __init__(self):
        self.claims: dict[str, ClaimKnowledge] = {}
        self.day = 0
        self.nli_cache: dict[str, str] = {}  # "i,j" -> relationship

    def encounter(self, claim_id: str, engagement: str = "read"):
        if claim_id not in self.claims:
            self.claims[claim_id] = ClaimKnowledge(
                claim_id=claim_id,
                stability=self.ENGAGEMENT_STABILITY.get(engagement, 30.0),
                last_seen_day=self.day,
                encounter_count=1,
                engagement=engagement,
            )
        else:
            c = self.claims[claim_id]
            c.stability *= self.REINFORCE_FACTOR
            c.last_seen_day = self.day
            c.encounter_count += 1

    def get_knowledge_state(self, claim_id: str) -> str:
        """Returns: known | partial | forgotten | unknown"""
        if claim_id not in self.claims:
            return "unknown"
        r = self.claims[claim_id].retrievability(self.day)
        if r >= 0.5:
            return "known"
        elif r >= 0.3:
            return "partial"
        else:
            return "forgotten"

    def known_ids(self) -> set[str]:
        return {cid for cid, c in self.claims.items()
                if c.retrievability(self.day) >= 0.3}


# ─── NLI Judge ────────────────────────────────────────────────────────────

def nli_judge(claim_a: str, claim_b: str) -> str:
    """Use Gemini Flash to classify relationship between two claims."""
    import litellm
    prompt = f"""Classify the relationship between these two claims as EXACTLY ONE of:
- ENTAILS: Same core knowledge
- EXTENDS: Adds new info to same topic
- UNRELATED: Different topics

Claim A: {claim_a}
Claim B: {claim_b}

Respond with just the word: ENTAILS, EXTENDS, or UNRELATED"""

    try:
        resp = litellm.completion(
            model="gemini/gemini-2.0-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0,
            api_key=GEMINI_API_KEY,
        )
        text = resp.choices[0].message.content.strip().upper()
        for label in ["ENTAILS", "EXTENDS", "UNRELATED"]:
            if label in text:
                return label
        return "UNRELATED"
    except Exception:
        return "UNRELATED"


# ─── Combined Classification ─────────────────────────────────────────────

def classify_claim_combined(claim_idx: int, claims: list[dict],
                            claim_to_idx: dict, similarity: np.ndarray,
                            ledger: CombinedKnowledgeLedger,
                            use_nli: bool = True) -> dict:
    """Classify a claim using the full combined pipeline.

    Returns dict with classification + metadata.
    """
    claim = claims[claim_idx]
    claim_id = claim["id"]

    # 1. Direct hit with decay check
    state = ledger.get_knowledge_state(claim_id)
    if state == "known":
        return {"classification": "KNOWN", "method": "direct_hit", "confidence": 1.0}
    if state == "partial":
        return {"classification": "PARTIALLY_KNOWN", "method": "direct_hit_decay", "confidence": 0.5}

    # 2. Embedding similarity with decay weighting
    max_sim = 0.0
    max_weighted = 0.0
    best_known_idx = None
    best_known_id = None

    for known_id in ledger.known_ids():
        known_idx = claim_to_idx.get(known_id)
        if known_idx is None:
            continue
        sim = float(similarity[claim_idx, known_idx])
        r = ledger.claims[known_id].retrievability(ledger.day)
        weighted = sim * r

        if weighted > max_weighted:
            max_weighted = weighted
            max_sim = sim
            best_known_idx = known_idx
            best_known_id = known_id

    # 3. Classification with tiered thresholds
    if max_weighted >= 0.78:
        return {"classification": "KNOWN", "method": "embedding_weighted",
                "similarity": round(max_sim, 3), "confidence": round(max_weighted, 3)}

    if max_weighted >= 0.68:
        # Ambiguous zone — use NLI judge if enabled
        if use_nli and GEMINI_API_KEY and best_known_idx is not None:
            cache_key = f"{claim_idx},{best_known_idx}"
            if cache_key not in ledger.nli_cache:
                nli_result = nli_judge(claim["normalized_text"],
                                       claims[best_known_idx]["normalized_text"])
                ledger.nli_cache[cache_key] = nli_result
                time.sleep(0.2)
            else:
                nli_result = ledger.nli_cache[cache_key]

            if nli_result == "ENTAILS":
                return {"classification": "KNOWN", "method": "nli_judge",
                        "similarity": round(max_sim, 3), "nli": "ENTAILS"}
            elif nli_result == "EXTENDS":
                return {"classification": "EXTENDS", "method": "nli_judge",
                        "similarity": round(max_sim, 3), "nli": "EXTENDS"}
            else:
                return {"classification": "NEW", "method": "nli_judge",
                        "similarity": round(max_sim, 3), "nli": "UNRELATED"}

        return {"classification": "EXTENDS", "method": "embedding_only",
                "similarity": round(max_sim, 3)}

    if max_weighted >= 0.55:
        return {"classification": "NEW", "method": "below_threshold",
                "similarity": round(max_sim, 3)}

    return {"classification": "NEW", "method": "no_match", "similarity": 0.0}


# ─── Curiosity Zone ──────────────────────────────────────────────────────

def curiosity_score(new: int, extends: int, known: int, partial: int) -> float:
    total = new + extends + known + partial
    if total == 0:
        return 0.0

    novelty = (new + extends * 0.5) / total
    novelty_score = math.exp(-((novelty - 0.7) ** 2) / (2 * 0.2 ** 2))

    context = (known + partial) / total
    context_bonus = min(context * 3, 1.0)

    bridge = extends / total
    bridge_bonus = bridge * 2

    return round(novelty_score * 0.5 + context_bonus * 0.25 + bridge_bonus * 0.25, 4)


# ─── Simulation ──────────────────────────────────────────────────────────

def load_data():
    with open(ARTICLES_PATH) as f:
        articles = json.load(f)

    claims = []
    claim_to_idx = {}
    for article in articles:
        for claim in article.get("atomic_claims", []):
            idx = len(claims)
            claim_to_idx[claim["id"]] = idx
            claims.append({**claim, "article_id": article.get("id", ""),
                           "article_title": article.get("title", "")})

    emb_path = DATA_DIR / "claim_embeddings_nomic.npz"
    data = np.load(emb_path)
    embeddings = data["embeddings"]
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    similarity = (embeddings / norms) @ (embeddings / norms).T

    return articles, claims, claim_to_idx, similarity


def simulate_week(articles, claims, claim_to_idx, similarity, use_nli=True):
    """Simulate a realistic 2-week reading scenario."""
    ledger = CombinedKnowledgeLedger()

    # Reading schedule: variable engagement, realistic pattern
    # Week 1: intensive reading (3-4 articles/day, mostly "read")
    # Week 2: selective (1-2 articles/day, some highlights)
    schedule = [
        # (day, article_index, engagement)
        (0, 0, "read"), (0, 1, "read"), (0, 2, "skim"),
        (1, 3, "read"), (1, 4, "highlight"),
        (2, 5, "read"), (2, 6, "read"), (2, 7, "skim"),
        (3, 8, "read"), (3, 9, "highlight"),
        (4, 10, "read"), (4, 11, "read"),
        (5, 12, "highlight"), (5, 13, "read"),
        # Week 2 — more selective, some re-reads
        (8, 14, "read"),
        (9, 0, "read"),  # Re-read first article
        (10, 15, "highlight"),
        (12, 16, "read"),
    ]

    # Ensure we don't exceed article count
    schedule = [(d, i, e) for d, i, e in schedule if i < len(articles)]

    timeline = []
    nli_calls = 0

    for day, article_idx, engagement in schedule:
        ledger.day = day
        article = articles[article_idx]
        article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]

        counts = {"NEW": 0, "KNOWN": 0, "EXTENDS": 0, "PARTIALLY_KNOWN": 0}
        methods = defaultdict(int)
        nli_used = 0

        for claim in article_claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is None:
                continue
            result = classify_claim_combined(
                idx, claims, claim_to_idx, similarity, ledger, use_nli=use_nli
            )
            counts[result["classification"]] = counts.get(result["classification"], 0) + 1
            methods[result["method"]] += 1
            if result["method"] == "nli_judge":
                nli_used += 1

        # Encounter all claims
        for claim in article_claims:
            ledger.encounter(claim["id"], engagement)

        total = sum(counts.values())
        novelty = (counts["NEW"] + counts["EXTENDS"]) / total * 100 if total > 0 else 0
        c_score = curiosity_score(counts["NEW"], counts["EXTENDS"],
                                   counts["KNOWN"], counts.get("PARTIALLY_KNOWN", 0))

        nli_calls += nli_used
        step = {
            "day": day,
            "article": article.get("title", "")[:50],
            "engagement": engagement,
            "total_claims": total,
            "counts": dict(counts),
            "novelty_pct": round(novelty, 1),
            "curiosity_score": c_score,
            "methods": dict(methods),
            "nli_calls": nli_used,
        }
        timeline.append(step)

    # Score remaining unread articles
    read_indices = set(i for _, i, _ in schedule)
    unread_articles = [(i, a) for i, a in enumerate(articles) if i not in read_indices]

    recommendations = []
    for i, article in unread_articles:
        article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]
        counts = {"NEW": 0, "KNOWN": 0, "EXTENDS": 0, "PARTIALLY_KNOWN": 0}

        for claim in article_claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is None:
                continue
            # Use cosine-only for ranking (no NLI for unread articles — too many calls)
            result = classify_claim_combined(
                idx, claims, claim_to_idx, similarity, ledger, use_nli=False
            )
            counts[result["classification"]] = counts.get(result["classification"], 0) + 1

        total = sum(counts.values())
        if total == 0:
            continue

        novelty = (counts["NEW"] + counts["EXTENDS"]) / total * 100
        c_score = curiosity_score(counts["NEW"], counts["EXTENDS"],
                                   counts["KNOWN"], counts.get("PARTIALLY_KNOWN", 0))

        recommendations.append({
            "title": article.get("title", "")[:60],
            "total_claims": total,
            "counts": dict(counts),
            "novelty_pct": round(novelty, 1),
            "curiosity_score": c_score,
        })

    recommendations.sort(key=lambda x: x["curiosity_score"], reverse=True)

    return timeline, recommendations, nli_calls, ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-nli", action="store_true", help="Skip NLI judge calls")
    args = parser.parse_args()

    print("Loading data...", file=sys.stderr)
    articles, claims, claim_to_idx, similarity = load_data()
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    use_nli = not args.skip_nli and bool(GEMINI_API_KEY)
    if not use_nli:
        print("  NLI judge disabled (--skip-nli or no API key)", file=sys.stderr)

    print(f"\nRunning 2-week combined simulation...", file=sys.stderr)
    timeline, recs, nli_calls, ledger = simulate_week(
        articles, claims, claim_to_idx, similarity, use_nli=use_nli
    )

    print(f"\n{'='*70}")
    print(f"  COMBINED SCORING — 2-Week Reading Simulation")
    print(f"{'='*70}")

    print(f"\n  {'Day':>3} {'Eng':>4} {'Nov%':>5} {'Cur':>5} "
          f"{'N':>3} {'E':>3} {'K':>3} {'P':>3} {'NLI':>3} {'Title'}")
    print(f"  {'─'*3} {'─'*4} {'─'*5} {'─'*5} "
          f"{'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*40}")

    for step in timeline:
        c = step["counts"]
        eng = step["engagement"][:4]
        print(f"  {step['day']:>3} {eng:>4} {step['novelty_pct']:>4.0f}% "
              f"{step['curiosity_score']:>5.3f} "
              f"{c.get('NEW',0):>3} {c.get('EXTENDS',0):>3} "
              f"{c.get('KNOWN',0):>3} {c.get('PARTIALLY_KNOWN',0):>3} "
              f"{step['nli_calls']:>3} {step['article'][:40]}")

    # Method distribution
    method_totals = defaultdict(int)
    for step in timeline:
        for method, count in step["methods"].items():
            method_totals[method] += count

    print(f"\n  Classification methods used:")
    for method, count in sorted(method_totals.items(), key=lambda x: -x[1]):
        print(f"    {method}: {count}")
    print(f"  Total NLI calls: {nli_calls}")

    # Recommendations
    print(f"\n{'='*70}")
    print(f"  RECOMMENDED NEXT READS (curiosity zone)")
    print(f"{'='*70}")
    print(f"\n  {'Rank':>4} {'Score':>6} {'Nov%':>5} {'N':>3} {'E':>3} "
          f"{'K':>3} {'P':>3} {'Title'}")
    print(f"  {'─'*4} {'─'*6} {'─'*5} {'─'*3} {'─'*3} {'─'*3} {'─'*3} {'─'*40}")

    for i, rec in enumerate(recs[:15]):
        c = rec["counts"]
        print(f"  {i+1:>4} {rec['curiosity_score']:>6.3f} {rec['novelty_pct']:>4.0f}% "
              f"{c.get('NEW',0):>3} {c.get('EXTENDS',0):>3} "
              f"{c.get('KNOWN',0):>3} {c.get('PARTIALLY_KNOWN',0):>3} "
              f"{rec['title'][:40]}")

    # Knowledge state summary
    ledger.day = 14  # End of simulation
    total_claims = len(ledger.claims)
    states = {"known": 0, "partial": 0, "forgotten": 0}
    for cid in ledger.claims:
        states[ledger.get_knowledge_state(cid)] += 1

    print(f"\n  Knowledge state at day 14:")
    print(f"    Total encountered: {total_claims}")
    print(f"    Known: {states['known']} ({states['known']/total_claims*100:.0f}%)")
    print(f"    Partial: {states['partial']} ({states['partial']/total_claims*100:.0f}%)")
    print(f"    Forgotten: {states['forgotten']} ({states['forgotten']/total_claims*100:.0f}%)")

    # Save results
    output = {
        "use_nli": use_nli,
        "total_nli_calls": nli_calls,
        "timeline": timeline,
        "recommendations": recs[:20],
        "method_totals": dict(method_totals),
        "knowledge_state": {
            "day": 14,
            "total": total_claims,
            **states,
        },
    }
    output_path = DATA_DIR / "experiment_combined_scoring.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
