#!/usr/bin/env python3
"""
Simulate Petrarca knowledge model behavior over time.

Replicates the app's content-word matching algorithm and models:
1. Concept updates per article read (at claims depth)
2. Novelty score evolution over time
3. Review queue growth over 1/2/4 weeks
4. Orphan concepts/topics that never get matched
5. Coverage gaps (articles without concepts)

Usage: python3 scripts/simulate_knowledge_model.py
"""

import json
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

BASE = Path(__file__).resolve().parent.parent / "app" / "data"

with open(BASE / "articles.json") as f:
    articles = json.load(f)

with open(BASE / "concepts.json") as f:
    concepts = json.load(f)

# Build article -> concept index (same as store.ts)
article_concept_index: dict[str, list[str]] = {}
for c in concepts:
    for aid in c["source_article_ids"]:
        article_concept_index.setdefault(aid, []).append(c["id"])

concept_by_id = {c["id"]: c for c in concepts}
article_by_id = {a["id"]: a for a in articles}

# ---------------------------------------------------------------------------
# Matching algorithm (replicated from store.ts)
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "that", "which", "who", "whom", "this", "these", "those",
    "it", "its", "they", "them", "their", "we", "our", "you", "your",
    "than", "more", "most", "very", "also", "just", "about",
}


def content_words(text: str) -> set[str]:
    """Extract content words (stop words removed, len > 2), matching store.ts."""
    import re
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


def match_claim_to_concepts(
    article_id: str, claim_text: str, threshold: float = 0.3
) -> list[str]:
    """Return concept IDs that match this claim above threshold."""
    article_concepts = article_concept_index.get(article_id, [])
    claim_content = content_words(claim_text)
    matched = []

    for cid in article_concepts:
        concept = concept_by_id.get(cid)
        if not concept:
            continue
        concept_content = content_words(concept["text"])
        if not concept_content:
            continue
        overlap = len(concept_content & claim_content)
        ratio = overlap / len(concept_content)
        if ratio > threshold:
            matched.append(cid)
    return matched


# ---------------------------------------------------------------------------
# Section 1: Matching analysis per article
# ---------------------------------------------------------------------------

def analyze_matching():
    print("=" * 72)
    print("SECTION 1: CLAIM-TO-CONCEPT MATCHING ANALYSIS")
    print("=" * 72)

    articles_with_concepts = [a for a in articles if a["id"] in article_concept_index]
    articles_without_concepts = [a for a in articles if a["id"] not in article_concept_index]

    print(f"\nArticles with concepts: {len(articles_with_concepts)} / {len(articles)}")
    print(f"Articles WITHOUT concepts: {len(articles_without_concepts)} / {len(articles)} ({100*len(articles_without_concepts)/len(articles):.0f}%)")
    print()

    if articles_without_concepts:
        print("Articles with no concepts (reading these updates ZERO knowledge):")
        for a in articles_without_concepts:
            print(f"  - {a['title'][:70]}")
        print()

    # For each article with concepts, simulate reading at claims depth
    total_claims = 0
    total_matched_claims = 0
    concepts_updated_per_article = []
    detailed_matches = []

    for a in articles_with_concepts:
        claims = a.get("key_claims", [])
        total_claims += len(claims)
        updated_concepts = set()

        for claim in claims:
            matched = match_claim_to_concepts(a["id"], claim)
            if matched:
                total_matched_claims += 1
                updated_concepts.update(matched)

        concepts_updated_per_article.append(
            (a["id"], a["title"][:50], len(claims), len(updated_concepts))
        )
        detailed_matches.append((a, updated_concepts))

    print("Per-article matching at claims depth (threshold=0.3):")
    for aid, title, n_claims, n_concepts in sorted(
        concepts_updated_per_article, key=lambda x: -x[3]
    ):
        available = len(article_concept_index.get(aid, []))
        print(f"  {title:<50} {n_claims} claims -> {n_concepts}/{available} concepts matched")

    print(f"\nTotal claims across articles with concepts: {total_claims}")
    print(f"Claims that match at least one concept: {total_matched_claims}/{total_claims} ({100*total_matched_claims/total_claims:.0f}%)")
    print(f"Avg concepts updated per article: {sum(x[3] for x in concepts_updated_per_article)/len(concepts_updated_per_article):.1f}")

    # Show match details for thresholds
    print("\n--- Threshold sensitivity analysis ---")
    for thresh in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]:
        matched_concepts_total = set()
        matched_claims = 0
        for a in articles_with_concepts:
            for claim in a.get("key_claims", []):
                m = match_claim_to_concepts(a["id"], claim, threshold=thresh)
                if m:
                    matched_claims += 1
                    matched_concepts_total.update(m)
        print(f"  threshold={thresh:.1f}: {matched_claims}/{total_claims} claims match, {len(matched_concepts_total)}/{len(concepts)} concepts reachable")


# ---------------------------------------------------------------------------
# Section 2: Novelty score evolution
# ---------------------------------------------------------------------------

def simulate_novelty_evolution():
    print("\n" + "=" * 72)
    print("SECTION 2: NOVELTY SCORE EVOLUTION")
    print("=" * 72)

    # Simulate reading articles in date order (newest first, as the app sorts)
    sorted_articles = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)
    # Only consider articles with concepts for novelty scoring
    all_with_concepts = [a for a in sorted_articles if a["id"] in article_concept_index]

    known_concepts: set[str] = set()

    print(f"\nSimulating user reading articles in date order (newest first).")
    print(f"After each article read (claims depth), concepts matching 'knew_it' signals become known.\n")
    print(f"{'Articles read':<15} {'Concepts known':<16} {'Avg novelty (has concepts)':<30} {'Min novelty':<12} {'Max novelty':<12}")
    print("-" * 85)

    for i, a in enumerate(all_with_concepts):
        # User reads this article, signals "interesting" on all claims -> concepts become encountered
        # For simulation, assume 50% knew_it, 50% interesting
        for claim in a.get("key_claims", []):
            matched = match_claim_to_concepts(a["id"], claim)
            known_concepts.update(matched)

        # Compute novelty for all remaining unread articles
        if (i + 1) % 3 == 0 or i == 0 or i == len(all_with_concepts) - 1:
            novelties = []
            for other in all_with_concepts[i + 1:]:
                cids = article_concept_index.get(other["id"], [])
                if not cids:
                    continue
                unknown_count = sum(1 for cid in cids if cid not in known_concepts)
                novelties.append(unknown_count / len(cids))

            if novelties:
                avg_nov = sum(novelties) / len(novelties)
                min_nov = min(novelties)
                max_nov = max(novelties)
            else:
                avg_nov = min_nov = max_nov = 0.0

            print(f"  {i+1:<13} {len(known_concepts):<16} {avg_nov:<30.3f} {min_nov:<12.3f} {max_nov:<12.3f}")

    # Also show what happens to articles WITHOUT concepts
    no_concept_articles = [a for a in sorted_articles if a["id"] not in article_concept_index]
    print(f"\nArticles without concepts always return null novelty score (no differentiation possible).")
    print(f"This affects {len(no_concept_articles)}/{len(articles)} articles ({100*len(no_concept_articles)/len(articles):.0f}%).")


# ---------------------------------------------------------------------------
# Section 3: Review queue projection
# ---------------------------------------------------------------------------

def simulate_review_queue():
    print("\n" + "=" * 72)
    print("SECTION 3: REVIEW QUEUE PROJECTION (1/2/4 WEEKS)")
    print("=" * 72)

    DAY_MS = 24 * 60 * 60 * 1000

    # Multipliers from store.ts
    multipliers = {1: 0.5, 2: 1.2, 3: 2.5, 4: 3.5}

    # Simulate 28 days, user reads 4 articles/day, does daily reviews
    sorted_articles = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)
    reading_queue = list(sorted_articles)  # articles to read

    # Review state: concept_id -> {stability_days, due_at, engagement_count}
    reviews: dict[str, dict] = {}
    known_concepts: set[str] = set()
    encountered_concepts: set[str] = set()

    ARTICLES_PER_DAY = 4
    REVIEWS_PER_DAY = 15  # max reviews user does per day

    print(f"\nAssumptions: {ARTICLES_PER_DAY} articles/day, up to {REVIEWS_PER_DAY} reviews/day")
    print(f"All articles read in date order. 'knew_it' on 30% of claims, 'interesting' on 50%, skip 20%.\n")

    print(f"{'Day':<6} {'Articles read':<15} {'New concepts':<14} {'Total known':<13} {'Queue size':<12} {'Due today':<12} {'Reviewed':<10} {'Backlog':<10}")
    print("-" * 92)

    articles_read_total = 0
    day_start_ms = 0  # simulate from day 0

    for day in range(1, 29):
        current_time = day * DAY_MS
        new_concepts_today = 0

        # Read articles
        for _ in range(ARTICLES_PER_DAY):
            if not reading_queue:
                break
            article = reading_queue.pop(0)
            articles_read_total += 1

            for claim in article.get("key_claims", []):
                matched = match_claim_to_concepts(article["id"], claim)
                # Simulate user signals
                r = random.random()
                if r < 0.3:
                    signal = "knew_it"
                elif r < 0.8:
                    signal = "interesting"
                else:
                    signal = "skip"

                for cid in matched:
                    was_new = cid not in known_concepts and cid not in encountered_concepts

                    if signal == "knew_it":
                        known_concepts.add(cid)
                        if cid not in reviews:
                            reviews[cid] = {
                                "stability_days": 7,  # known -> longer initial interval
                                "due_at": current_time + 7 * DAY_MS,
                                "engagement_count": 0,
                            }
                            if was_new:
                                new_concepts_today += 1
                    elif signal == "interesting":
                        if cid not in known_concepts:
                            encountered_concepts.add(cid)
                        if cid not in reviews:
                            reviews[cid] = {
                                "stability_days": 1,  # encountered -> short interval
                                "due_at": current_time + 1 * DAY_MS,
                                "engagement_count": 0,
                            }
                            if was_new:
                                new_concepts_today += 1

        # Count due reviews
        due_today = [
            cid for cid, r in reviews.items() if r["due_at"] <= current_time
        ]
        queue_size = len(reviews)

        # Do reviews (up to REVIEWS_PER_DAY)
        reviewed_count = 0
        for cid in due_today[:REVIEWS_PER_DAY]:
            r = reviews[cid]
            # Simulate review rating: mostly "good" (3)
            rating = random.choices([1, 2, 3, 4], weights=[5, 15, 60, 20])[0]
            if rating == 1:
                r["stability_days"] = 1
            else:
                r["stability_days"] = max(1, min(365, r["stability_days"] * multipliers[rating]))
            r["due_at"] = current_time + r["stability_days"] * DAY_MS
            r["engagement_count"] += 1
            reviewed_count += 1

        backlog = max(0, len(due_today) - REVIEWS_PER_DAY)

        if day in [1, 2, 3, 5, 7, 10, 14, 21, 28]:
            print(
                f"  {day:<4} {articles_read_total:<15} {new_concepts_today:<14} "
                f"{len(known_concepts) + len(encountered_concepts):<13} {queue_size:<12} "
                f"{len(due_today):<12} {reviewed_count:<10} {backlog:<10}"
            )

    print(f"\nAfter 28 days:")
    print(f"  Articles read: {articles_read_total}")
    print(f"  Total concepts in review system: {len(reviews)}")
    print(f"  Known concepts: {len(known_concepts)}")
    print(f"  Encountered concepts: {len(encountered_concepts)}")
    print(f"  Unreached concepts: {len(concepts) - len(known_concepts) - len(encountered_concepts)}")

    # Interval distribution at day 28
    intervals = [r["stability_days"] for r in reviews.values()]
    if intervals:
        print(f"\n  Interval distribution at day 28:")
        buckets = {"< 1 day": 0, "1-3 days": 0, "4-7 days": 0, "1-2 weeks": 0, "2-4 weeks": 0, "1+ month": 0}
        for iv in intervals:
            if iv < 1:
                buckets["< 1 day"] += 1
            elif iv <= 3:
                buckets["1-3 days"] += 1
            elif iv <= 7:
                buckets["4-7 days"] += 1
            elif iv <= 14:
                buckets["1-2 weeks"] += 1
            elif iv <= 28:
                buckets["2-4 weeks"] += 1
            else:
                buckets["1+ month"] += 1
        for label, count in buckets.items():
            print(f"    {label}: {count} concepts")


# ---------------------------------------------------------------------------
# Section 4: Orphan and unreachable concepts
# ---------------------------------------------------------------------------

def analyze_orphans():
    print("\n" + "=" * 72)
    print("SECTION 4: ORPHAN CONCEPTS & MATCHING GAPS")
    print("=" * 72)

    # Find concepts that no claim can reach at 0.3 threshold
    reachable = set()
    unreachable = []

    for a in articles:
        article_cids = article_concept_index.get(a["id"], [])
        if not article_cids:
            continue
        for claim in a.get("key_claims", []):
            matched = match_claim_to_concepts(a["id"], claim, threshold=0.3)
            reachable.update(matched)

    for c in concepts:
        if c["id"] not in reachable:
            unreachable.append(c)

    print(f"\nReachable concepts (via any claim at threshold=0.3): {len(reachable)}/{len(concepts)}")
    print(f"Unreachable concepts: {len(unreachable)}/{len(concepts)}")

    if unreachable:
        print("\nUnreachable concepts (no claim matches above 0.3 threshold):")
        for c in unreachable:
            # Show what the best match would be
            best_ratio = 0
            best_claim = ""
            for aid in c["source_article_ids"]:
                a = article_by_id.get(aid)
                if not a:
                    continue
                concept_content = content_words(c["text"])
                for claim in a.get("key_claims", []):
                    claim_content = content_words(claim)
                    if concept_content:
                        overlap = len(concept_content & claim_content)
                        ratio = overlap / len(concept_content)
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_claim = claim[:60]

            print(f"  [{c['id']}] {c['text'][:70]}...")
            print(f"    topic: {c['topic']}, best match ratio: {best_ratio:.2f}")
            if best_claim:
                print(f"    best claim: \"{best_claim}\"")
            print()

    # Show detailed matching for a few examples
    print("\n--- Detailed word overlap examples ---")
    examples = [a for a in articles if a["id"] in article_concept_index][:3]
    for a in examples:
        print(f"\nArticle: {a['title'][:60]}")
        for claim in a.get("key_claims", [])[:2]:
            claim_words = content_words(claim)
            print(f"  Claim: \"{claim[:70]}\"")
            print(f"    Content words: {sorted(claim_words)[:10]}...")
            for cid in article_concept_index.get(a["id"], []):
                concept = concept_by_id[cid]
                concept_words = content_words(concept["text"])
                overlap = claim_words & concept_words
                ratio = len(overlap) / len(concept_words) if concept_words else 0
                marker = "MATCH" if ratio > 0.3 else "miss"
                print(f"    vs [{cid}] ratio={ratio:.2f} [{marker}] overlap={sorted(overlap)[:5]}")


# ---------------------------------------------------------------------------
# Section 5: Topic coverage analysis
# ---------------------------------------------------------------------------

def analyze_topic_coverage():
    print("\n" + "=" * 72)
    print("SECTION 5: TOPIC COVERAGE ANALYSIS")
    print("=" * 72)

    # Article topics vs concept topics
    article_topics = set()
    for a in articles:
        article_topics.update(a.get("topics", []))

    concept_topics = set(c["topic"] for c in concepts)

    print(f"\nUnique article topics: {len(article_topics)}")
    print(f"Unique concept topics: {len(concept_topics)}")
    print(f"Overlap: {len(article_topics & concept_topics)}")
    print(f"Article topics not in any concept: {len(article_topics - concept_topics)}")
    print(f"Concept topics not in any article topic: {len(concept_topics - article_topics)}")

    # Topics with articles but no concepts
    uncovered_topics = article_topics - concept_topics
    topic_article_count = Counter()
    for a in articles:
        for t in a.get("topics", []):
            topic_article_count[t] += 1

    if uncovered_topics:
        print("\nArticle topics with NO concepts (sorted by article count):")
        for t in sorted(uncovered_topics, key=lambda x: -topic_article_count[x]):
            print(f"  {t}: {topic_article_count[t]} articles")

    # Concept density per topic
    concept_topic_count = Counter(c["topic"] for c in concepts)
    print("\nConcept density by topic (concepts / articles):")
    for topic in sorted(concept_topics, key=lambda t: -concept_topic_count[t]):
        n_concepts = concept_topic_count[topic]
        n_articles = topic_article_count.get(topic, 0)
        ratio = n_concepts / n_articles if n_articles > 0 else float("inf")
        print(f"  {topic}: {n_concepts} concepts / {n_articles} articles = {ratio:.1f} concepts/article")


# ---------------------------------------------------------------------------
# Section 6: Recommendations
# ---------------------------------------------------------------------------

def recommendations():
    print("\n" + "=" * 72)
    print("SECTION 6: RECOMMENDATIONS")
    print("=" * 72)

    articles_without = [a for a in articles if a["id"] not in article_concept_index]
    pct_without = 100 * len(articles_without) / len(articles)

    # Count unreachable concepts
    reachable = set()
    for a in articles:
        for claim in a.get("key_claims", []):
            matched = match_claim_to_concepts(a["id"], claim, threshold=0.3)
            reachable.update(matched)
    unreachable_count = len(concepts) - len(reachable)

    print(f"""
1. CRITICAL: CONCEPT COVERAGE GAP
   {len(articles_without)}/{len(articles)} articles ({pct_without:.0f}%) have ZERO concepts.
   Reading these articles updates nothing in the knowledge model.
   These include diverse topics (history, literature, product analytics,
   NLP, fine-tuning) that are completely invisible to the system.

   FIX: Run concept extraction on all articles. The build_articles.py
   pipeline should generate concepts for every article, not just the
   first batch.

2. MATCHING QUALITY
   {unreachable_count}/{len(concepts)} concepts ({100*unreachable_count/len(concepts):.0f}%) cannot be reached by any claim
   at the 0.3 threshold. The content-word matching is too coarse for
   concepts whose text diverges significantly from claim wording.

   FIX: Consider semantic matching (embeddings) or lowering threshold
   to 0.2 for claim matching. Also consider matching against section
   content, not just key_claims.

3. CONCEPT DENSITY
   Currently {len(concepts)} concepts across {len(articles)} articles = {len(concepts)/len(articles):.1f} concepts/article.
   For the 21 articles WITH concepts: {len(concepts)/21:.1f} concepts/article.
   This is thin — each article typically has 5-8 key claims but only
   ~3 concepts. Many claims never connect to a concept.

   FIX: Aim for 1:1 claim-to-concept mapping (or close to it).
   This would mean ~280+ concepts instead of 69.

4. TOPIC FRAGMENTATION
   Article topics and concept topics use different vocabularies.
   Many article topics have no corresponding concepts at all.
   The topic field on concepts is decorative, not functional for matching.

   FIX: Either unify the topic taxonomy, or rely less on topics and
   more on content matching for cross-article concept connections.

5. REVIEW QUEUE SUSTAINABILITY
   With 4 articles/day and current concept density, the review queue
   grows slowly (~2-3 new concepts/day). This is manageable but
   means the system provides very little value in the first week.
   With better coverage (~6 concepts/article, all articles), expect
   ~24 new concepts/day — review queue of ~150+ after 4 weeks.
   This would require either: capping daily reviews, or increasing
   intervals for well-known concepts.

6. NOVELTY DIFFERENTIATION
   Novelty scores start differentiating after reading ~5-6 articles
   (when enough concepts become known). But 55% of articles return
   null novelty (no concepts), making the Feed's novelty ranking
   useless for over half the content.

   FIX: Concept coverage (#1 above) is prerequisite for useful novelty.
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    random.seed(42)  # reproducibility
    print("PETRARCA KNOWLEDGE MODEL SIMULATION")
    print(f"Data: {len(articles)} articles, {len(concepts)} concepts")
    print(f"Articles with concepts: {sum(1 for a in articles if a['id'] in article_concept_index)}")
    print(f"Total key_claims: {sum(len(a.get('key_claims', [])) for a in articles)}")

    analyze_matching()
    simulate_novelty_evolution()
    simulate_review_queue()
    analyze_orphans()
    analyze_topic_coverage()
    recommendations()
