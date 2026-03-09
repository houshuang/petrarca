#!/usr/bin/env python3
"""Experiment: FSRS-inspired knowledge decay for reading.

Tests how knowledge decay affects novelty scoring over time. Implements a
simplified FSRS (Free Spaced Repetition Scheduler) model adapted for reading:

- Claims start with stability S based on reading engagement
- Stability decays over time if not reinforced
- Retrievability R = e^(-t/S) where t is days since encounter
- Claims with low R are treated as "partially forgotten" and may be novel again

This addresses Issue #5 from the overnight report: "High EXTENDS rate" and
Issue #10: "Confidence decay" — old knowledge should fade.

Usage:
    python3 scripts/experiment_knowledge_decay.py
    python3 scripts/experiment_knowledge_decay.py --decay-days 30  # simulate 30 days
"""

import json
import sys
import argparse
import math
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"


@dataclass
class FSRSClaimState:
    """FSRS-inspired state for a single claim."""
    claim_id: str
    status: str = "unknown"  # unknown | encountered | absorbed | decayed
    stability: float = 0.0  # S: how stable is this memory (in days)
    difficulty: float = 0.5  # D: how hard is this claim to remember (0-1)
    last_seen_day: int = 0
    encounter_count: int = 0
    source_article: str = ""

    def retrievability(self, current_day: int) -> float:
        """R = e^(-t/S) where t is days since last seen."""
        if self.stability <= 0:
            return 0.0
        t = current_day - self.last_seen_day
        return math.exp(-t / self.stability)


@dataclass
class FSRSKnowledgeLedger:
    """Knowledge ledger with FSRS decay."""
    states: dict = field(default_factory=dict)
    current_day: int = 0

    # FSRS parameters — calibrated for reading comprehension
    # Key insight: reading is not flash-card memorization. Ebbinghaus forgetting
    # curves apply to rote memorization; reading comprehension decays much slower.
    # A reader who understood an article retains the gist for weeks/months.
    BASE_STABILITY = 30.0  # Initial S for a casually read claim (days)
    ABSORBED_STABILITY = 120.0  # S for absorbed claims (user said "I know this")
    REINFORCEMENT_FACTOR = 2.5  # S multiplier when claim is re-encountered
    RETRIEVAL_THRESHOLD = 0.3  # Below this R, claim is "forgotten enough" to be novel again
    PARTIAL_THRESHOLD = 0.5  # Below this R, claim counts as "partially known"

    def encounter(self, claim_id: str, article_id: str, engagement: str = "read"):
        """Record encountering a claim while reading."""
        if claim_id not in self.states:
            # First encounter — set initial stability based on engagement
            s = {
                "skim": self.BASE_STABILITY * 0.3,   # ~9 days
                "read": self.BASE_STABILITY,           # 30 days
                "highlight": self.BASE_STABILITY * 2.0,  # 60 days
                "annotate": self.BASE_STABILITY * 4.0,   # 120 days
            }.get(engagement, self.BASE_STABILITY)

            self.states[claim_id] = FSRSClaimState(
                claim_id=claim_id,
                status="encountered",
                stability=s,
                last_seen_day=self.current_day,
                encounter_count=1,
                source_article=article_id,
            )
        else:
            state = self.states[claim_id]
            # Reinforcement — increase stability
            state.stability *= self.REINFORCEMENT_FACTOR
            state.last_seen_day = self.current_day
            state.encounter_count += 1
            if state.status == "decayed":
                state.status = "encountered"

    def absorb(self, claim_id: str):
        """User explicitly marks 'I know this'."""
        if claim_id in self.states:
            self.states[claim_id].status = "absorbed"
            self.states[claim_id].stability = max(
                self.states[claim_id].stability, self.ABSORBED_STABILITY
            )

    def effective_knowledge(self, claim_id: str) -> str:
        """Get effective knowledge state considering decay.

        Returns: "known" | "partial" | "forgotten" | "unknown"
        """
        if claim_id not in self.states:
            return "unknown"

        state = self.states[claim_id]
        r = state.retrievability(self.current_day)

        if r >= self.PARTIAL_THRESHOLD:
            return "known"
        elif r >= self.RETRIEVAL_THRESHOLD:
            return "partial"
        else:
            return "forgotten"

    def known_count(self) -> int:
        return sum(1 for s in self.states.values()
                   if self.effective_knowledge(s.claim_id) in ("known", "partial"))

    def summary(self) -> dict:
        """Summary of current knowledge state."""
        counts = {"known": 0, "partial": 0, "forgotten": 0, "unknown": 0}
        for state in self.states.values():
            ek = self.effective_knowledge(state.claim_id)
            counts[ek] += 1
        counts["total_encountered"] = len(self.states)
        return counts


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


def classify_with_decay(claim_idx: int, ledger: FSRSKnowledgeLedger,
                        claims: list[dict], claim_to_idx: dict,
                        similarity: np.ndarray,
                        known_threshold: float = 0.78,
                        extends_threshold: float = 0.68) -> str:
    """Classify a claim considering knowledge decay."""
    claim_id = claims[claim_idx]["id"]

    # Direct hit — check if this exact claim is still known
    ek = ledger.effective_knowledge(claim_id)
    if ek == "known":
        return "KNOWN"
    elif ek == "partial":
        return "PARTIALLY_KNOWN"

    # Check similarity to known claims (but weight by retrievability)
    max_weighted_sim = 0.0
    for known_id, state in ledger.states.items():
        known_idx = claim_to_idx.get(known_id)
        if known_idx is None:
            continue
        sim = float(similarity[claim_idx, known_idx])
        r = state.retrievability(ledger.current_day)
        weighted = sim * r  # Decay-weighted similarity
        if weighted > max_weighted_sim:
            max_weighted_sim = weighted

    if max_weighted_sim >= known_threshold:
        return "KNOWN"
    elif max_weighted_sim >= extends_threshold:
        return "EXTENDS"
    elif max_weighted_sim >= extends_threshold * 0.8:  # Just below extends threshold
        return "PARTIALLY_KNOWN"
    else:
        return "NEW"


def simulate_with_decay(articles, claims, claim_to_idx, similarity,
                        reading_schedule, model="nomic"):
    """Simulate reading over time with decay.

    reading_schedule: list of (day, article_indices, engagement)
    """
    known_threshold = 0.78 if model == "nomic" else 0.72
    extends_threshold = 0.68 if model == "nomic" else 0.62

    ledger = FSRSKnowledgeLedger()
    timeline = []

    for day, article_idx, engagement in reading_schedule:
        ledger.current_day = day
        article = articles[article_idx]
        article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]

        classifications = {"NEW": 0, "KNOWN": 0, "EXTENDS": 0, "PARTIALLY_KNOWN": 0}

        for claim in article_claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is None:
                continue
            c = classify_with_decay(idx, ledger, claims, claim_to_idx, similarity,
                                    known_threshold, extends_threshold)
            classifications[c] += 1

        # Read the article (encounter all claims)
        for claim in article_claims:
            ledger.encounter(claim["id"], article.get("id", ""), engagement)

        total = sum(classifications.values())
        novelty = ((classifications["NEW"] + classifications["EXTENDS"]) / total * 100) if total > 0 else 0

        step = {
            "day": day,
            "article": article.get("title", "")[:50],
            "engagement": engagement,
            "classifications": dict(classifications),
            "total_claims": total,
            "novelty_pct": round(novelty, 1),
            "knowledge_summary": ledger.summary(),
        }
        timeline.append(step)

    return timeline, ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nomic", choices=["gemini", "nomic"])
    parser.add_argument("--decay-days", type=int, default=60, help="Simulation length in days")
    args = parser.parse_args()

    print(f"Loading data (embeddings: {args.model})...", file=sys.stderr)
    articles, claims, claim_to_idx, similarity = load_data(args.model)
    print(f"  {len(articles)} articles, {len(claims)} claims", file=sys.stderr)

    # Build reading schedule: read articles spread over time
    # Scenario 1: Intensive burst (10 articles in 3 days, then wait)
    n_articles = min(15, len(articles))
    schedule_burst = []
    for i in range(n_articles):
        day = i // 3  # 3 articles per day for first 5 days
        schedule_burst.append((day, i, "read"))

    # Check knowledge at various points after the burst
    check_days = [0, 7, 14, 30, 45, 60]

    print(f"\n{'='*60}")
    print(f"  SCENARIO 1: Burst reading (15 articles in 5 days)")
    print(f"{'='*60}")

    timeline_burst, ledger_burst = simulate_with_decay(
        articles, claims, claim_to_idx, similarity, schedule_burst, args.model
    )

    for step in timeline_burst:
        c = step["classifications"]
        print(f"  Day {step['day']:3d}: {step['article'][:40]}")
        print(f"           {step['novelty_pct']}% novel (N:{c['NEW']} E:{c['EXTENDS']} "
              f"K:{c['KNOWN']} P:{c.get('PARTIALLY_KNOWN', 0)})")

    # Now check how knowledge decays over time
    print(f"\n  Knowledge decay after burst reading:")
    for check_day in check_days:
        ledger_burst.current_day = check_day
        summary = ledger_burst.summary()
        total = summary["total_encountered"]
        print(f"    Day {check_day:3d}: "
              f"known={summary['known']} ({summary['known']/total*100:.0f}%) | "
              f"partial={summary['partial']} ({summary['partial']/total*100:.0f}%) | "
              f"forgotten={summary['forgotten']} ({summary['forgotten']/total*100:.0f}%)")

    # Scenario 2: Re-reading after 30 days
    # Read same articles again after a 30-day gap
    print(f"\n{'='*60}")
    print(f"  SCENARIO 2: Re-reading after 30-day gap")
    print(f"{'='*60}")

    schedule_reread = list(schedule_burst)  # Same initial burst
    for i in range(min(5, n_articles)):
        schedule_reread.append((35, i, "read"))  # Re-read first 5 articles on day 35

    timeline_reread, ledger_reread = simulate_with_decay(
        articles, claims, claim_to_idx, similarity, schedule_reread, args.model
    )

    # Show the re-reading entries
    for step in timeline_reread[n_articles:]:
        c = step["classifications"]
        print(f"  Day {step['day']:3d}: RE-READ {step['article'][:40]}")
        print(f"           {step['novelty_pct']}% novel (N:{c['NEW']} E:{c['EXTENDS']} "
              f"K:{c['KNOWN']} P:{c.get('PARTIALLY_KNOWN', 0)})")

    # Scenario 3: Spaced reading (1-2 articles every few days)
    print(f"\n{'='*60}")
    print(f"  SCENARIO 3: Spaced reading (1-2 articles every few days)")
    print(f"{'='*60}")

    schedule_spaced = []
    day = 0
    for i in range(n_articles):
        schedule_spaced.append((day, i, "read"))
        day += 3 + (i % 2) * 2  # every 3-5 days

    timeline_spaced, ledger_spaced = simulate_with_decay(
        articles, claims, claim_to_idx, similarity, schedule_spaced, args.model
    )

    for step in timeline_spaced:
        c = step["classifications"]
        ks = step["knowledge_summary"]
        print(f"  Day {step['day']:3d}: {step['article'][:40]}")
        print(f"           {step['novelty_pct']}% novel | total known: {ks['known']+ks['partial']}")

    # Scenario 4: Compare decay vs no-decay for the same articles
    print(f"\n{'='*60}")
    print(f"  COMPARISON: Decay vs No-Decay (re-reading on day 30)")
    print(f"{'='*60}")

    # Manual comparison: read first 10 articles, then re-read articles 1-5 on day 30
    no_decay_schedule = list(schedule_burst[:10])  # Read 10 articles
    no_decay_schedule.extend([(30, i, "read") for i in range(5)])  # Re-read 5 on day 30

    timeline_nodecay_reread, _ = simulate_with_decay(
        articles, claims, claim_to_idx, similarity, no_decay_schedule, args.model
    )

    # With no decay (hack: set base stability very high)
    ledger_no_decay = FSRSKnowledgeLedger()
    ledger_no_decay.BASE_STABILITY = 99999  # effectively no decay
    ledger_no_decay.ABSORBED_STABILITY = 99999

    timeline_persistent = []
    for day, article_idx, engagement in no_decay_schedule:
        ledger_no_decay.current_day = day
        article = articles[article_idx]
        article_claims = [c for c in claims if c["article_id"] == article.get("id", "")]

        classifications = {"NEW": 0, "KNOWN": 0, "EXTENDS": 0, "PARTIALLY_KNOWN": 0}
        for claim in article_claims:
            idx = claim_to_idx.get(claim["id"])
            if idx is None:
                continue
            c = classify_with_decay(idx, ledger_no_decay, claims, claim_to_idx, similarity,
                                    0.78 if args.model == "nomic" else 0.72,
                                    0.68 if args.model == "nomic" else 0.62)
            classifications[c] += 1

        for claim in article_claims:
            ledger_no_decay.encounter(claim["id"], article.get("id", ""), engagement)

        total = sum(classifications.values())
        novelty = ((classifications["NEW"] + classifications["EXTENDS"]) / total * 100) if total > 0 else 0
        timeline_persistent.append({
            "day": day, "article": article.get("title", "")[:50],
            "novelty_pct": round(novelty, 1), "classifications": dict(classifications),
        })

    print(f"\n  {'Article':<45} {'Decay':>8} {'No-Decay':>10}")
    print(f"  {'─'*45} {'─'*8} {'─'*10}")
    for i in range(10, len(no_decay_schedule)):
        decay_step = timeline_nodecay_reread[i]
        persistent_step = timeline_persistent[i]
        print(f"  {decay_step['article'][:45]:<45} "
              f"{decay_step['novelty_pct']:>6.1f}% {persistent_step['novelty_pct']:>8.1f}%")

    # Save results
    output = {
        "model": args.model,
        "fsrs_params": {
            "base_stability": FSRSKnowledgeLedger.BASE_STABILITY,
            "absorbed_stability": FSRSKnowledgeLedger.ABSORBED_STABILITY,
            "reinforcement_factor": FSRSKnowledgeLedger.REINFORCEMENT_FACTOR,
            "retrieval_threshold": FSRSKnowledgeLedger.RETRIEVAL_THRESHOLD,
            "partial_threshold": FSRSKnowledgeLedger.PARTIAL_THRESHOLD,
        },
        "burst_timeline": timeline_burst,
        "reread_timeline": timeline_reread,
        "spaced_timeline": timeline_spaced,
        "decay_vs_nodecay": {
            "decay": [{"day": s["day"], "article": s["article"],
                       "novelty_pct": s["novelty_pct"]} for s in timeline_nodecay_reread[10:]],
            "no_decay": [{"day": s["day"], "article": s["article"],
                         "novelty_pct": s["novelty_pct"]} for s in timeline_persistent[10:]],
        },
    }
    output_path = DATA_DIR / "experiment_knowledge_decay.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
