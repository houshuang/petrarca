#!/usr/bin/env python3
"""Multi-stage synthesis pipeline for Petrarca concept clusters.

Replaces the monolithic single-LLM-call synthesis generator with a pipeline
that produces better, more deterministic results by leveraging pre-computed
knowledge index data and separating concerns across stages.

Stages:
  0: Deterministic Brief Builder (no LLM) — builds synthesis brief from knowledge index
  1: Tension Narration (LLM, parallel) — describes what each tension is about
  2: Outline & Theme Organization (LLM) — generates structured outline
  3: Prose Generation (LLM, parallel by section) — writes 2-3 paragraphs per section
  4: Assembly & Verification (deterministic + LLM) — stitches, checks, computes coverage

Output: data/synthesis-stages/{cluster_id}/ with intermediate artifacts
        + final entry merged into data/syntheses.json

Usage:
    python3 scripts/synthesis_pipeline.py --cluster-id 22 --verbose
    python3 scripts/synthesis_pipeline.py --cluster-id 4 --stage 0  # run only stage 0
    python3 scripts/synthesis_pipeline.py --all --verbose
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
STAGES_DIR = DATA_DIR / "synthesis-stages"
CLUSTERS_PATH = DATA_DIR / "concept_clusters.json"
ARTICLES_PATH = DATA_DIR / "articles.json"
KNOWLEDGE_INDEX_PATH = DATA_DIR / "knowledge_index.json"
SYNTHESES_PATH = DATA_DIR / "syntheses.json"

# Model selection per stage
MODEL_EXTRACTION = "gemini-3.1-flash-lite-preview"  # Stages 1, 4-questions
MODEL_REASONING = "gemini-3-flash-preview"           # Stages 2, 3

# Similarity thresholds (match knowledge index)
THRESHOLD_KNOWN = 0.78
THRESHOLD_EXTENDS = 0.68

# Synthesis approaches — controls Stage 2 (outline) and Stage 3 (prose) prompts
APPROACHES = ["thematic", "dialectical", "progressive", "narrative", "hybrid"]

APPROACH_STAGE2 = {
    "thematic": {
        "system_instruction": (
            "You are a humanist scholar organizing a synthesis essay. "
            "Create an outline that captures genuine intellectual insights, "
            "tensions, and surprising connections between sources. "
            "Every heading should be specific enough that a reader knows "
            "what argument the section makes."
        ),
        "organization_rule": (
            "Organize by INSIGHT and ARGUMENT, not by article. Let structure emerge from the ideas. "
            "Each section should cover a distinct theme or argument that weaves multiple sources together."
        ),
    },
    "dialectical": {
        "system_instruction": (
            "You are a dialectical thinker organizing a synthesis around intellectual conflict. "
            "Lead with what's contested, what sources disagree about, and where perspectives diverge. "
            "Your outline should make the reader feel the productive friction between ideas."
        ),
        "organization_rule": (
            "Organize by TENSIONS and DEBATES between sources. Each section should center on a "
            "disagreement, different emphasis, or unresolved question. Headings should name the "
            "conflict or opposing positions. Distribute shared claims as common ground within "
            "each debate section, not as a separate section."
        ),
    },
    "progressive": {
        "system_instruction": (
            "You are a methodical scholar organizing a synthesis as progressive disclosure — "
            "from consensus to divergence. Start with what all sources agree on, then zoom into "
            "what each contributes uniquely, then end with what's contested or open."
        ),
        "organization_rule": (
            "Organize in THREE layers: "
            "(1) First 1-2 sections: SHARED GROUND — what's established and agreed across sources. "
            "(2) Middle sections: UNIQUE CONTRIBUTIONS — what specific articles add that others don't. "
            "(3) Final 1-2 sections: CONTESTED TERRITORY — tensions, open questions, unresolved debates. "
            "This gives the reader a landscape: settled → distinctive → disputed."
        ),
    },
    "narrative": {
        "system_instruction": (
            "You are a guide walking the reader through these sources in the order they should "
            "be encountered. Each section represents what the next article (or pair) adds to the "
            "reader's understanding. Think 'here's what you'd learn reading these in sequence.'"
        ),
        "organization_rule": (
            "Organize by READING ORDER — use the marginal reading order from the coverage data. "
            "Each section should represent what one or two articles add incrementally: "
            "'Having read X, article Y now adds Z.' Headings should capture the knowledge GAIN, "
            "not just the article topic. Tensions emerge naturally as later articles challenge earlier ones."
        ),
    },
    "hybrid": {
        "system_instruction": (
            "You are a humanist scholar writing a synthesis that replaces reading the individual articles. "
            "Use a PROGRESSIVE structure (shared ground → unique insights → contested territory) "
            "but with NARRATIVE transitions between sections and DIALECTICAL framing for contested material. "
            "Your outline must be deep enough that a reader learns concrete, specific things — "
            "not just the 10,000-foot view. Include specific methods, benchmarks, names, and approaches."
        ),
        "organization_rule": (
            "Use a LAYERED PROGRESSIVE structure with narrative flow:\n"
            "(1) First section: COMMON GROUND — the consensus across sources, with specific shared insights. "
            "Use narrative transitions, not bullet summaries.\n"
            "(2) Middle sections: UNIQUE CONTRIBUTIONS grouped by theme (not by article). "
            "Each section should surface concrete methods, tools, and approaches from specific sources. "
            "Use 'Having established X, we now see Y' narrative bridges between sections.\n"
            "(3) Final section(s): CONTESTED TERRITORY — frame as dialectical tensions. "
            "Name the disagreement, give each side its strongest case, don't resolve artificially.\n"
            "CRITICAL: Every section must include specific details (benchmarks, tool names, methods, "
            "dates) not just thematic summaries. The reader should LEARN something concrete from each section.\n"
            "For each section, include an 'evidence_details' field with 2-3 specific facts, methods, "
            "or approaches that should be surfaced as concrete evidence blocks in the prose."
        ),
    },
}

APPROACH_STAGE3 = {
    "thematic": {
        "system_instruction": (
            "You are a humanist scholar writing a synthesis essay. "
            "Write substantive, flowing prose with rich detail from the sources. "
            "Every claim must be attributed to a specific source via markdown link. "
            "Avoid vague generalities — be specific about what each source argues. "
            "CRITICAL: Always complete your final sentence and paragraph. Never stop mid-sentence."
        ),
        "voice_instruction": (
            "Write flowing scholarly prose that weaves sources together around the section's theme. "
            "Let insights from different sources build on each other."
        ),
    },
    "dialectical": {
        "system_instruction": (
            "You are a dialectical essayist surfacing productive friction between ideas. "
            "Every claim must be attributed to a specific source via markdown link. "
            "Name the disagreement clearly, then give each side its strongest case. "
            "CRITICAL: Always complete your final sentence and paragraph. Never stop mid-sentence."
        ),
        "voice_instruction": (
            "Lead with the conflict or tension. Name what's at stake. Present each side's "
            "strongest argument using specific evidence from the sources. Don't resolve "
            "artificially — let the reader sit with genuine disagreement. End each section "
            "with what the tension reveals about the field."
        ),
    },
    "progressive": {
        "system_instruction": (
            "You are a methodical scholar presenting a layered analysis. "
            "Every claim must be attributed to a specific source via markdown link. "
            "In shared-ground sections: emphasize consensus with cross-references. "
            "In unique sections: highlight what only this source contributes. "
            "In contested sections: present both sides fairly. "
            "CRITICAL: Always complete your final sentence and paragraph. Never stop mid-sentence."
        ),
        "voice_instruction": (
            "Match your voice to the layer: authoritative and synthesizing for shared ground, "
            "curious and highlighting for unique contributions, and exploratory for contested "
            "territory. Signal transitions between layers clearly."
        ),
    },
    "narrative": {
        "system_instruction": (
            "You are a guide narrating a journey through these readings. "
            "Every claim must be attributed to a specific source via markdown link. "
            "Frame each section as 'what the next reading adds to your understanding.' "
            "CRITICAL: Always complete your final sentence and paragraph. Never stop mid-sentence."
        ),
        "voice_instruction": (
            "Write as if walking the reader through a reading journey. Use phrases like "
            "'Having seen X, this article now reveals Y' or 'This challenges the earlier claim that Z.' "
            "Build cumulative understanding — each section should feel like it deepens or redirects "
            "what came before. Make the incremental knowledge gain visceral."
        ),
    },
    "hybrid": {
        "system_instruction": (
            "You are a humanist scholar writing a synthesis that replaces reading the source articles. "
            "Write at TWO LEVELS within each section:\n"
            "- MAIN NARRATIVE: Flowing prose making the argument (17px equivalent)\n"
            "- EVIDENCE BLOCKS: Specific methods, benchmarks, code patterns, tool details "
            "that a practitioner would want to know. Mark these with :::evidence and :::end markers.\n"
            "Every claim must be attributed via markdown link. "
            "CRITICAL: Always complete your final sentence and paragraph. Never stop mid-sentence."
        ),
        "voice_instruction": (
            "Write at two levels of depth WITHIN each section:\n"
            "1. MAIN NARRATIVE paragraphs that make the argument and surface insights. "
            "Flowing prose, scholarly but direct.\n"
            "2. EVIDENCE BLOCKS that contain the concrete specifics a practitioner needs. "
            "Wrap these in :::evidence / :::end markers. These should contain specific "
            "benchmarks (49% on SWE-bench), tool names (tmux lanes, setup.md), methods "
            "(git reset loops, SHA-256 commitments), and implementation details.\n"
            "The reader should be able to scan just the main narrative for the argument, "
            "OR read the evidence blocks for actionable specifics.\n"
            "Use narrative transitions between themes: 'Having established X, we now see Y.'"
        ),
    },
}

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
    print(msg, file=sys.stderr, flush=True)


def timed(stage_name: str):
    """Decorator to time a stage function."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            t0 = time.time()
            log(f"\n{'='*60}")
            log(f"  Stage: {stage_name}")
            log(f"{'='*60}")
            result = fn(*args, **kwargs)
            elapsed = time.time() - t0
            log(f"  [{stage_name}] completed in {elapsed:.1f}s")
            return result, elapsed
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_data():
    """Load articles, knowledge index, concept clusters, and existing syntheses."""
    log("Loading data files...")
    t0 = time.time()

    with open(ARTICLES_PATH) as f:
        articles = json.load(f)
    article_map = {a["id"]: a for a in articles}

    with open(KNOWLEDGE_INDEX_PATH) as f:
        ki = json.load(f)

    with open(CLUSTERS_PATH) as f:
        clusters_data = json.load(f)

    existing_syntheses = {}
    if SYNTHESES_PATH.exists():
        with open(SYNTHESES_PATH) as f:
            data = json.load(f)
        existing_syntheses = {
            s["cluster_id"]: s for s in data.get("syntheses", []) if "cluster_id" in s
        }

    log(f"  Loaded in {time.time() - t0:.1f}s: {len(articles)} articles, "
        f"{len(ki.get('claims', {}))} claims, "
        f"{len(clusters_data.get('clusters', []))} clusters")

    return article_map, ki, clusters_data, existing_syntheses


# ---------------------------------------------------------------------------
# Stage 0: Deterministic Brief Builder
# ---------------------------------------------------------------------------

def stage_0_build_brief(cluster: dict, article_map: dict, ki: dict,
                        verbose: bool = False) -> dict:
    """Build the synthesis brief from pre-computed knowledge index data."""
    cluster_id = f"cluster_{cluster['cluster_id']}"
    cluster_ids = set(a["id"] for a in cluster["articles"])
    claims_dict = ki.get("claims", {})
    article_claims_map = ki.get("article_claims", {})
    nm = ki.get("article_novelty_matrix", {})
    similarities = ki.get("similarities", [])
    llm_verdicts = ki.get("llm_verdicts", {})

    # 1. Extract novelty graph subset for this cluster
    novelty_graph = {}
    for target_id in cluster_ids:
        if target_id not in nm:
            continue
        target_entry = {}
        for read_id, counts in nm[target_id].items():
            if read_id in cluster_ids and read_id != target_id:
                target_entry[read_id] = counts
        if target_entry:
            novelty_graph[target_id] = target_entry

    # 2. Build claim ID sets per article (within this cluster)
    claims_by_article = {}
    all_cluster_claim_ids = set()
    for aid in cluster_ids:
        cids = article_claims_map.get(aid, [])
        claims_by_article[aid] = set(cids)
        all_cluster_claim_ids.update(cids)

    # 3. Build within-cluster similarity lookup: for each claim, track
    #    its max similarity to any claim in a DIFFERENT article within the cluster
    claim_to_article = {}
    for aid, cids in claims_by_article.items():
        for cid in cids:
            claim_to_article[cid] = aid

    # Build max-similarity-to-other-article for each claim
    claim_max_cross_sim = {}  # claim_id -> (max_score, nearest_claim_id)
    cross_article_pairs = []  # pairs within this cluster

    for pair in similarities:
        cid_a, cid_b, score = pair["a"], pair["b"], pair["score"]
        art_a = claim_to_article.get(cid_a)
        art_b = claim_to_article.get(cid_b)

        # Both claims must be in this cluster and from different articles
        if art_a is None or art_b is None:
            continue
        if art_a == art_b:
            continue

        cross_article_pairs.append(pair)

        # Track max cross-article similarity for each claim
        if cid_a not in claim_max_cross_sim or score > claim_max_cross_sim[cid_a][0]:
            claim_max_cross_sim[cid_a] = (score, cid_b)
        if cid_b not in claim_max_cross_sim or score > claim_max_cross_sim[cid_b][0]:
            claim_max_cross_sim[cid_b] = (score, cid_a)

    # 4. Identify shared claims: claims with cross-article similarity >= EXTENDS
    shared_claims = []
    shared_claim_freq = {}  # claim_id -> count of cross-article links

    for pair in cross_article_pairs:
        cid_a, cid_b = pair["a"], pair["b"]
        if pair["score"] >= THRESHOLD_EXTENDS:
            shared_claim_freq[cid_a] = shared_claim_freq.get(cid_a, 0) + 1
            shared_claim_freq[cid_b] = shared_claim_freq.get(cid_b, 0) + 1

    # Merge with key_shared_claims from cluster data
    existing_shared = {c["claim_id"]: c for c in cluster.get("key_shared_claims", [])}
    for cid in existing_shared:
        if cid not in shared_claim_freq:
            shared_claim_freq[cid] = existing_shared[cid].get("cross_article_links", 1)

    # Sort by frequency, take top
    for cid, freq in sorted(shared_claim_freq.items(), key=lambda x: -x[1])[:20]:
        claim_info = claims_dict.get(cid, {})
        if not claim_info:
            continue
        # Find which articles share this claim
        sharing_articles = set()
        sharing_articles.add(claim_info.get("article_id", ""))
        for pair in cross_article_pairs:
            if pair["score"] >= THRESHOLD_EXTENDS:
                if pair["a"] == cid:
                    other_art = claim_to_article.get(pair["b"])
                    if other_art:
                        sharing_articles.add(other_art)
                elif pair["b"] == cid:
                    other_art = claim_to_article.get(pair["a"])
                    if other_art:
                        sharing_articles.add(other_art)

        shared_claims.append({
            "claim_id": cid,
            "text": claim_info.get("text", ""),
            "article_ids": sorted(sharing_articles),
            "cross_links": freq,
        })

    # 5. Identify unique claims per article: claims with no cross-article sim >= EXTENDS
    unique_claims_per_article = {}
    for aid in cluster_ids:
        unique = []
        for cid in claims_by_article.get(aid, set()):
            max_sim_info = claim_max_cross_sim.get(cid)
            claim_info = claims_dict.get(cid, {})
            if not claim_info:
                continue
            if max_sim_info is None or max_sim_info[0] < THRESHOLD_EXTENDS:
                nearest_sim = max_sim_info[0] if max_sim_info else 0.0
                unique.append({
                    "claim_id": cid,
                    "text": claim_info.get("text", ""),
                    "similarity_to_nearest": round(nearest_sim, 3),
                })
        # Sort by most unique first
        unique.sort(key=lambda x: x["similarity_to_nearest"])
        unique_claims_per_article[aid] = unique

    # 6. Find high-tension pairs: claims with similarity 0.68-0.78 from different articles
    #    These are claims that seem related but different — potential tensions
    high_tension_pairs = []
    seen_tension_pairs = set()

    for pair in cross_article_pairs:
        score = pair["score"]
        if not (THRESHOLD_EXTENDS <= score < THRESHOLD_KNOWN):
            continue

        cid_a, cid_b = pair["a"], pair["b"]
        pair_key = tuple(sorted([cid_a, cid_b]))
        if pair_key in seen_tension_pairs:
            continue
        seen_tension_pairs.add(pair_key)

        claim_a_info = claims_dict.get(cid_a, {})
        claim_b_info = claims_dict.get(cid_b, {})
        if not claim_a_info or not claim_b_info:
            continue

        art_a = claim_to_article.get(cid_a, "")
        art_b = claim_to_article.get(cid_b, "")

        # Check LLM verdict if available
        verdict_key_1 = f"{cid_a}::{cid_b}"
        verdict_key_2 = f"{cid_b}::{cid_a}"
        llm_verdict = llm_verdicts.get(verdict_key_1) or llm_verdicts.get(verdict_key_2)

        # Prioritize pairs where LLM said EXTENDS (genuine difference, not just duplicate)
        # and especially ones near the boundary
        high_tension_pairs.append({
            "claim_a": {
                "id": cid_a,
                "text": claim_a_info.get("text", ""),
                "article_id": art_a,
            },
            "claim_b": {
                "id": cid_b,
                "text": claim_b_info.get("text", ""),
                "article_id": art_b,
            },
            "similarity": score,
            "llm_verdict": llm_verdict,
        })

    # Sort: prefer EXTENDS verdicts and mid-range similarity (most likely real tensions)
    def tension_sort_key(t):
        score = t["similarity"]
        verdict = t.get("llm_verdict")
        # Prefer EXTENDS over ENTAILS, and mid-range similarity
        verdict_bonus = 0.1 if verdict == "EXTENDS" else (0.0 if verdict is None else -0.1)
        # Peak interest at 0.73 similarity (equidistant between thresholds)
        distance_from_peak = abs(score - 0.73)
        return distance_from_peak - verdict_bonus

    high_tension_pairs.sort(key=tension_sort_key)
    # Cap: scale with cluster size but max out at 10 for quality
    max_tensions = min(10, max(4, len(cluster_ids)))
    high_tension_pairs = high_tension_pairs[:max_tensions]

    # 7. Compute reading order by marginal information gain
    coverage_order = _compute_reading_order(cluster_ids, novelty_graph, claims_by_article)

    brief = {
        "cluster_id": cluster_id,
        "label": cluster.get("label", "Unlabeled"),
        "article_count": len(cluster_ids),
        "total_claims": len(all_cluster_claim_ids),
        "novelty_graph": novelty_graph,
        "shared_claims": shared_claims,
        "unique_claims_per_article": {
            aid: claims[:8] for aid, claims in unique_claims_per_article.items()
        },
        "high_tension_pairs": high_tension_pairs,
        "coverage_if_read_in_order": coverage_order,
    }

    if verbose:
        log(f"  Brief: {len(shared_claims)} shared claims, "
            f"{sum(len(v) for v in unique_claims_per_article.values())} unique claims, "
            f"{len(high_tension_pairs)} tension pairs")

    return brief


def _compute_reading_order(cluster_ids: set, novelty_graph: dict,
                           claims_by_article: dict) -> list[dict]:
    """Greedy algorithm: at each step, pick the article adding the most new claims."""
    remaining = set(cluster_ids)
    read_so_far = set()
    order = []

    while remaining:
        best_article = None
        best_marginal = -1

        for candidate in remaining:
            candidate_claims = claims_by_article.get(candidate, set())
            if not candidate_claims:
                # Article with no claims: marginal = 0
                if best_marginal < 0:
                    best_article = candidate
                    best_marginal = 0
                continue

            # Count how many of this article's claims are NEW given what we've read
            known_claims = set()
            for read_aid in read_so_far:
                if candidate in novelty_graph and read_aid in novelty_graph[candidate]:
                    entry = novelty_graph[candidate][read_aid]
                    known_claims_count = entry.get("known", 0) + entry.get("extends", 0)
                    # Approximate: we can't get exact claim IDs from novelty matrix,
                    # so use the count as a proxy
                    pass

            # Simpler approach: count total overlap with all read articles
            total_overlap = 0
            for read_aid in read_so_far:
                if candidate in novelty_graph and read_aid in novelty_graph[candidate]:
                    entry = novelty_graph[candidate][read_aid]
                    total_overlap = max(total_overlap,
                                        entry.get("known", 0) + entry.get("extends", 0))

            marginal = len(candidate_claims) - total_overlap
            if marginal > best_marginal:
                best_marginal = marginal
                best_article = candidate

        if best_article is None:
            break

        remaining.remove(best_article)
        read_so_far.add(best_article)
        order.append({
            "article_id": best_article,
            "marginal_new_claims": max(0, best_marginal),
        })

    return order


# ---------------------------------------------------------------------------
# Stage 1: Tension Narration (LLM, parallel)
# ---------------------------------------------------------------------------

def stage_1_narrate_tensions(brief: dict, article_map: dict,
                             verbose: bool = False) -> list[dict]:
    """For each high-tension pair, ask the LLM to describe the tension."""
    from gemini_llm import call_llm

    tension_pairs = brief.get("high_tension_pairs", [])
    if not tension_pairs:
        log("  No tension pairs to narrate")
        return []

    log(f"  Narrating {len(tension_pairs)} tension pairs...")

    def _narrate_one(pair: dict, index: int) -> dict:
        claim_a = pair["claim_a"]
        claim_b = pair["claim_b"]

        art_a = article_map.get(claim_a["article_id"], {})
        art_b = article_map.get(claim_b["article_id"], {})
        title_a = art_a.get("title", "Article A")
        title_b = art_b.get("title", "Article B")

        prompt = f"""Two articles about related topics make claims that overlap but differ.

Article A: "{title_a}"
Claim A: {claim_a["text"]}

Article B: "{title_b}"
Claim B: {claim_b["text"]}

Cosine similarity: {pair["similarity"]:.3f} (range 0.68-0.78 = related but distinct)

Your task: determine if these claims represent a genuine TENSION worth discussing in a synthesis essay. A tension means the claims offer competing interpretations, different emphases on the same phenomenon, or outright disagreement. Claims that simply discuss different subtopics are NOT tensions.

Return JSON:
{{
  "is_tension": true/false,
  "label": "Short 3-7 word tension label (only if is_tension=true)",
  "description": "1-2 sentences: what specific point do these claims disagree on or emphasize differently? Name what Article A argues vs what Article B argues.",
  "type": "disagreement|emphasis|methodology|scope|framing"
}}"""

        response = call_llm(
            prompt,
            model=MODEL_EXTRACTION,
            max_tokens=300,
            response_mime_type="application/json",
        )

        if response:
            try:
                parsed = json.loads(response)
                # Filter out non-tensions
                if not parsed.get("is_tension", True):
                    return None
                return {
                    "label": parsed.get("label", "Unknown tension"),
                    "description": parsed.get("description", ""),
                    "type": parsed.get("type", "emphasis"),
                    "side_a": {
                        "article_id": claim_a["article_id"],
                        "claim_id": claim_a["id"],
                        "claim_text": claim_a["text"],
                    },
                    "side_b": {
                        "article_id": claim_b["article_id"],
                        "claim_id": claim_b["id"],
                        "claim_text": claim_b["text"],
                    },
                    "similarity": pair["similarity"],
                }
            except json.JSONDecodeError:
                pass

        # Fallback: include but mark as uncertain
        return {
            "label": "Related claims with different emphasis",
            "description": f'"{title_a}" claims: {claim_a["text"]}. '
                           f'Meanwhile, "{title_b}" claims: {claim_b["text"]}.',
            "type": "emphasis",
            "side_a": {
                "article_id": claim_a["article_id"],
                "claim_id": claim_a["id"],
                "claim_text": claim_a["text"],
            },
            "side_b": {
                "article_id": claim_b["article_id"],
                "claim_id": claim_b["id"],
                "claim_text": claim_b["text"],
            },
            "similarity": pair["similarity"],
        }

    narrated = []
    filtered_count = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_narrate_one, pair, i): i
            for i, pair in enumerate(tension_pairs)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                if result is None:
                    filtered_count += 1
                    if verbose:
                        log(f"    [{idx+1}/{len(tension_pairs)}] filtered (not a real tension)")
                else:
                    narrated.append(result)
                    if verbose:
                        log(f"    [{idx+1}/{len(tension_pairs)}] {result['label']}")
            except Exception as e:
                log(f"    [{idx+1}/{len(tension_pairs)}] ERROR: {e}")

    # Sort back to original order by similarity (most interesting first)
    narrated.sort(key=lambda t: -t.get("similarity", 0))

    log(f"  Narrated {len(narrated)} tensions ({filtered_count} filtered as non-tensions)")
    return narrated


# ---------------------------------------------------------------------------
# Stage 2: Outline & Theme Organization (LLM)
# ---------------------------------------------------------------------------

def stage_2_generate_outline(brief: dict, tensions: list[dict],
                             article_map: dict, verbose: bool = False,
                             approach: str = "thematic") -> dict:
    """Generate a structured outline with descriptive headings."""
    from gemini_llm import call_llm

    cluster_label = brief.get("label", "Unlabeled")
    article_count = brief.get("article_count", 0)

    # Build article summaries
    article_summaries = []
    cluster_article_ids = set()
    for entry in brief.get("coverage_if_read_in_order", []):
        aid = entry["article_id"]
        cluster_article_ids.add(aid)
        art = article_map.get(aid, {})
        title = art.get("title", "Untitled")
        summary = art.get("full_summary", art.get("one_line_summary", ""))
        key_claims = art.get("key_claims", [])
        article_summaries.append(
            f"- **{title}** (ID: {aid})\n"
            f"  Summary: {summary}\n"
            f"  Key claims: {'; '.join(key_claims[:5]) if key_claims else 'N/A'}"
        )

    articles_text = "\n".join(article_summaries)

    # Build shared claims text
    shared_text = ""
    if brief.get("shared_claims"):
        shared_lines = []
        for sc in brief["shared_claims"][:12]:
            arts = ", ".join(sc["article_ids"][:3])
            shared_lines.append(f"- {sc['text']} (shared across: {arts})")
        shared_text = "SHARED CLAIMS (appear across multiple articles):\n" + "\n".join(shared_lines)

    # Build tensions text
    tension_text = ""
    if tensions:
        tension_lines = []
        for i, t in enumerate(tensions[:8]):
            art_a_title = article_map.get(t["side_a"]["article_id"], {}).get("title", "?")[:50]
            art_b_title = article_map.get(t["side_b"]["article_id"], {}).get("title", "?")[:50]
            tension_lines.append(
                f"[Tension {i}] {t['label']} ({t['type']})\n"
                f"  {t['description']}\n"
                f"  Sources: \"{art_a_title}\" vs \"{art_b_title}\""
            )
        tension_text = "TENSIONS BETWEEN SOURCES:\n" + "\n".join(tension_lines)

    # Build unique claims highlights
    unique_text = ""
    unique_highlights = []
    for aid, claims in brief.get("unique_claims_per_article", {}).items():
        art = article_map.get(aid, {})
        title = art.get("title", "?")[:50]
        if claims:
            top_unique = [c["text"] for c in claims[:3]]
            unique_highlights.append(f"- \"{title}\": {'; '.join(top_unique)}")
    if unique_highlights:
        unique_text = "UNIQUE CONTRIBUTIONS PER ARTICLE:\n" + "\n".join(unique_highlights)

    # Build article reference key
    ref_lines = []
    for entry in brief.get("coverage_if_read_in_order", []):
        aid = entry["article_id"]
        art = article_map.get(aid, {})
        ref_lines.append(f"- {aid} = \"{art.get('title', 'Untitled')}\"")
    ref_key = "\n".join(ref_lines)

    # Reading order context for narrative approach
    reading_order_text = ""
    if approach == "narrative":
        order_entries = brief.get("coverage_if_read_in_order", [])
        if order_entries:
            order_lines = []
            for i, entry in enumerate(order_entries):
                art = article_map.get(entry["article_id"], {})
                title = art.get("title", "Untitled")[:60]
                marginal = entry.get("marginal_novel_claims", 0)
                order_lines.append(f"  {i+1}. \"{title}\" — adds {marginal} novel claims")
            reading_order_text = "\nOPTIMAL READING ORDER (most to least marginal value):\n" + "\n".join(order_lines)

    approach_config = APPROACH_STAGE2[approach]
    organization_rule = approach_config["organization_rule"]

    prompt = f"""You are organizing a synthesis of {article_count} articles about "{cluster_label}".

SYNTHESIS APPROACH: {approach.upper()}

ARTICLES:
{articles_text}

{shared_text}

{tension_text}

{unique_text}
{reading_order_text}

ARTICLE ID KEY:
{ref_key}

Generate a structured outline for a synthesis essay. Return JSON:
{{
  "title": "A compelling, descriptive title for the synthesis (not just the topic name)",
  "sections": [
    {{
      "heading": "Descriptive heading capturing the actual insight (NEVER use 'Overview', 'Shared Themes', 'Unique Contributions', 'Introduction', 'Conclusion', 'Summary')",
      "theme_summary": "1-2 sentences describing what this section argues or explores",
      "primary_articles": ["article_id_1", "article_id_2"],
      "supporting_articles": ["article_id_3"],
      "shared_claims_to_weave": ["claim text 1", "claim text 2"],
      "unique_claims_to_highlight": ["claim text"],
      "tension_indices": [0],
      "suggested_research_question": "An open question this section raises"
    }}
  ]
}}

RULES:
1. 3-6 sections depending on cluster size. Each section should cover a distinct theme or argument.
2. Every article must appear as primary in at least one section.
3. Headings must be specific and descriptive — capture the actual intellectual content.
4. Distribute tensions across sections (not all in one section).
5. Each section should have 2-4 primary articles and material for 2-3 rich paragraphs.
6. APPROACH-SPECIFIC: {organization_rule}
7. The first section should be the most compelling entry point, not a generic introduction."""

    system_instruction = approach_config["system_instruction"]

    response = call_llm(
        prompt,
        model=MODEL_REASONING,
        max_tokens=4096,
        system_instruction=system_instruction,
        response_mime_type="application/json",
    )

    if not response:
        log("  ERROR: No outline response from LLM")
        return _fallback_outline(brief, article_map)

    try:
        outline = json.loads(response)
    except json.JSONDecodeError:
        log(f"  ERROR: Could not parse outline JSON")
        return _fallback_outline(brief, article_map)

    # Validate and fix outline
    outline = _validate_outline(outline, brief, article_map, cluster_article_ids, tensions)

    if verbose:
        log(f"  Outline: \"{outline.get('title', '?')}\"")
        for i, sec in enumerate(outline.get("sections", [])):
            log(f"    Section {i}: {sec.get('heading', '?')} "
                f"({len(sec.get('primary_articles', []))} primary, "
                f"{len(sec.get('tension_indices', []))} tensions)")

    return outline


def _fallback_outline(brief: dict, article_map: dict) -> dict:
    """Generate a minimal outline without LLM."""
    articles = brief.get("coverage_if_read_in_order", [])
    return {
        "title": brief.get("label", "Synthesis"),
        "sections": [{
            "heading": f"Analysis of {brief.get('label', 'Topic')}",
            "theme_summary": "Combined analysis of all articles",
            "primary_articles": [a["article_id"] for a in articles],
            "supporting_articles": [],
            "shared_claims_to_weave": [],
            "unique_claims_to_highlight": [],
            "tension_indices": list(range(min(3, len(brief.get("high_tension_pairs", []))))),
            "suggested_research_question": "",
        }],
    }


BANNED_HEADINGS = {
    "overview", "introduction", "conclusion", "summary",
    "shared themes", "unique contributions", "common themes",
    "key findings", "main themes", "general overview",
    "discussion", "final thoughts", "closing remarks",
}


def _validate_outline(outline: dict, brief: dict, article_map: dict,
                       cluster_article_ids: set, tensions: list[dict]) -> dict:
    """Validate and fix the outline."""
    sections = outline.get("sections", [])

    # Check: all articles covered
    covered_articles = set()
    for sec in sections:
        for aid in sec.get("primary_articles", []):
            covered_articles.add(aid)
        for aid in sec.get("supporting_articles", []):
            covered_articles.add(aid)

    missing = cluster_article_ids - covered_articles
    if missing and sections:
        # Add missing articles to the last section
        sections[-1].setdefault("supporting_articles", []).extend(sorted(missing))
        log(f"  Warning: {len(missing)} articles were missing from outline, added to last section")

    # Check: no banned headings
    for sec in sections:
        heading = sec.get("heading", "").strip()
        if heading.lower() in BANNED_HEADINGS:
            # Replace with something based on the theme_summary
            theme = sec.get("theme_summary", "")
            if theme:
                sec["heading"] = theme[:80]
            else:
                sec["heading"] = f"Exploring {brief.get('label', 'the Topic')}"
            log(f"  Warning: Replaced banned heading \"{heading}\" with \"{sec['heading']}\"")

    # Check: tensions distributed but not overloaded
    used_tension_indices = set()
    for sec in sections:
        for idx in sec.get("tension_indices", []):
            used_tension_indices.add(idx)

    unused_tensions = set(range(len(tensions))) - used_tension_indices
    if unused_tensions and sections:
        # Distribute unused tensions, but cap at 2 per section
        for i, idx in enumerate(sorted(unused_tensions)):
            section_idx = i % len(sections)
            current = sections[section_idx].get("tension_indices", [])
            if len(current) < 3:  # max 3 tensions per section
                sections[section_idx].setdefault("tension_indices", []).append(idx)

    # Cap tensions per section at 2 (for prose quality)
    for sec in sections:
        if len(sec.get("tension_indices", [])) > 2:
            sec["tension_indices"] = sec["tension_indices"][:2]

    outline["sections"] = sections
    return outline


# ---------------------------------------------------------------------------
# Stage 3: Prose Generation (LLM, parallel by section)
# ---------------------------------------------------------------------------

def stage_3_generate_prose(outline: dict, brief: dict, tensions: list[dict],
                           article_map: dict, verbose: bool = False,
                           approach: str = "thematic") -> list[dict]:
    """Generate 2-3 paragraphs per section."""
    from gemini_llm import call_llm

    sections = outline.get("sections", [])
    if not sections:
        log("  ERROR: No sections in outline")
        return []

    log(f"  Generating prose for {len(sections)} sections...")

    # Build article reference key
    all_article_ids = set()
    for sec in sections:
        all_article_ids.update(sec.get("primary_articles", []))
        all_article_ids.update(sec.get("supporting_articles", []))

    ref_key_lines = []
    for aid in sorted(all_article_ids):
        art = article_map.get(aid, {})
        title = art.get("title", "Untitled")
        ref_key_lines.append(f"  [{title}](article:{aid})")
    ref_key = "\n".join(ref_key_lines)

    def _generate_section(section: dict, index: int, prev_summaries: list[str]) -> dict:
        heading = section.get("heading", "Section")
        theme = section.get("theme_summary", "")
        primary_ids = section.get("primary_articles", [])
        supporting_ids = section.get("supporting_articles", [])
        claims_to_weave = section.get("shared_claims_to_weave", [])
        unique_claims = section.get("unique_claims_to_highlight", [])
        tension_indices = section.get("tension_indices", [])

        # Build article excerpts for this section
        article_excerpts = []
        for aid in primary_ids + supporting_ids:
            art = article_map.get(aid, {})
            if not art:
                continue
            title = art.get("title", "Untitled")
            summary = art.get("full_summary", art.get("one_line_summary", ""))
            key_claims = art.get("key_claims", [])

            # Include relevant sections content
            sections_text = ""
            if art.get("sections"):
                sec_texts = []
                for s in art["sections"][:6]:
                    content = s.get("content", "")
                    if content:
                        sec_texts.append(f"  {s.get('heading', '')}: {content[:800]}")
                if sec_texts:
                    sections_text = "\n" + "\n".join(sec_texts)

            is_primary = aid in primary_ids
            role = "PRIMARY" if is_primary else "SUPPORTING"
            article_excerpts.append(
                f"[{role}] {title} (ID: {aid})\n"
                f"Summary: {summary}\n"
                f"Key claims: {'; '.join(key_claims[:5])}"
                f"{sections_text}"
            )

        # Build tension context
        tension_context = ""
        if tension_indices:
            tension_blocks = []
            for ti in tension_indices:
                if ti < len(tensions):
                    t = tensions[ti]
                    art_a = article_map.get(t["side_a"]["article_id"], {})
                    art_b = article_map.get(t["side_b"]["article_id"], {})
                    tension_blocks.append(
                        f"TENSION: {t['label']}\n"
                        f"  {t['description']}\n"
                        f"  Side A ({art_a.get('title', '?')[:40]}): {t['side_a']['claim_text']}\n"
                        f"  Side B ({art_b.get('title', '?')[:40]}): {t['side_b']['claim_text']}"
                    )
            if tension_blocks:
                tension_context = (
                    "\n\nTENSIONS TO EMBED IN THIS SECTION "
                    "(weave 1-2 of the most relevant as blockquotes):\n" +
                    "\n\n".join(tension_blocks)
                )

        # Build claims context
        claims_context = ""
        if claims_to_weave:
            claims_context = "\n\nSHARED CLAIMS TO WEAVE IN:\n- " + "\n- ".join(
                str(c) for c in claims_to_weave[:6]
            )
        if unique_claims:
            claims_context += "\n\nUNIQUE CLAIMS TO HIGHLIGHT:\n- " + "\n- ".join(
                str(c) for c in unique_claims[:4]
            )

        # Previous sections context (for narrative flow)
        flow_context = ""
        if prev_summaries:
            flow_context = "\n\nPREVIOUS SECTIONS (for narrative continuity):\n" + "\n".join(
                f"- {ps}" for ps in prev_summaries[-2:]
            )

        approach_s3 = APPROACH_STAGE3[approach]
        voice_instruction = approach_s3["voice_instruction"]

        prompt = f"""Write section {index + 1} of a synthesis essay.

SYNTHESIS APPROACH: {approach.upper()}
SECTION HEADING: {heading}
SECTION THEME: {theme}

ARTICLE REFERENCE KEY (use EXACTLY these links when citing sources):
{ref_key}

SOURCE MATERIAL:
{"\\n---\\n".join(article_excerpts)}
{tension_context}
{claims_context}
{flow_context}

Write 2-3 substantial paragraphs (150-250 words each) for this section.

REQUIREMENTS:
1. Reference sources using EXACT markdown links from the ARTICLE REFERENCE KEY above: [Full Article Title](article:ID)
   Every paragraph MUST cite at least one source. Use the COMPLETE title, never truncate it.
2. Write flowing scholarly prose. No bullet lists. No thin summaries.
3. Surface specific facts, methods, arguments, and evidence from the sources.
4. If there are tensions to embed, pick the 1-2 most relevant and weave them as blockquotes:
   > ⚡ **Tension label**
   > 1-2 sentence description using [Full Article Title](article:ID) links for both sides.
   Keep tension blockquotes concise (2-3 lines max). Not every tension needs a blockquote.
5. Include at least one specific detail (a date, name, number, method) per paragraph.
6. Complete every sentence. Never stop mid-sentence.
7. VOICE: {voice_instruction}

Return ONLY the prose paragraphs (with tension blockquotes if applicable). No heading — the heading will be added separately."""

        system_instruction = approach_s3["system_instruction"]

        # Try up to 2 times if truncated
        for attempt in range(2):
            response = call_llm(
                prompt,
                model=MODEL_REASONING,
                max_tokens=4096,
                system_instruction=system_instruction,
            )

            if not response:
                log(f"    Section {index}: LLM returned no response (attempt {attempt+1})")
                continue

            prose = response.strip()

            # Detect truncation: too short or ends mid-sentence
            is_truncated = (
                (prose and prose[-1] not in ".!?*)\n\"'") or
                len(prose) < 500
            )

            if is_truncated and attempt == 0:
                log(f"    Warning: Section {index} appears truncated ({len(prose)} chars), retrying...")
                continue
            elif is_truncated:
                log(f"    Warning: Section {index} still truncated after retry ({len(prose)} chars)")

            break
        else:
            prose = "*Section content could not be generated.*"

        return {
            "index": index,
            "heading": heading,
            "prose": prose,
            "theme_summary": theme,
            "research_question": section.get("suggested_research_question", ""),
        }

    # Generate sections sequentially to maintain narrative flow
    # (parallel would be faster but loses coherence between sections)
    results = []
    prev_summaries = []

    for i, section in enumerate(sections):
        result = _generate_section(section, i, prev_summaries)
        results.append(result)
        prev_summaries.append(f"{result['heading']}: {result['theme_summary']}")
        if verbose:
            log(f"    Section {i}: \"{result['heading']}\" — {len(result['prose'])} chars")

    results.sort(key=lambda r: r["index"])
    log(f"  Generated {len(results)} sections, "
        f"total {sum(len(r['prose']) for r in results)} chars")
    return results


# ---------------------------------------------------------------------------
# Stage 4: Assembly & Verification
# ---------------------------------------------------------------------------

def stage_4_assemble_and_verify(sections: list[dict], brief: dict,
                                tensions: list[dict], outline: dict,
                                article_map: dict, ki: dict,
                                verbose: bool = False) -> dict:
    """Assemble final synthesis, verify, and compute coverage."""
    from gemini_llm import call_llm

    cluster_id = brief["cluster_id"]
    cluster_article_ids = set()
    for entry in brief.get("coverage_if_read_in_order", []):
        cluster_article_ids.add(entry["article_id"])

    # 1. Assemble markdown
    title = outline.get("title", brief.get("label", "Synthesis"))
    md_parts = []
    for sec in sections:
        md_parts.append(f"## {sec['heading']}")
        md_parts.append("")
        md_parts.append(sec["prose"])
        md_parts.append("")

        # Add research question as italic aside
        if sec.get("research_question"):
            md_parts.append(f"*Open question: {sec['research_question']}*")
            md_parts.append("")

    synthesis_md = "\n".join(md_parts).strip()

    # 2. Deterministic checks
    issues = []

    # Check all article links are valid
    link_pattern = re.compile(r'\[([^\]]+)\]\(article:([a-f0-9]+)\)')
    found_links = link_pattern.findall(synthesis_md)
    referenced_article_ids = set()
    for link_text, link_id in found_links:
        referenced_article_ids.add(link_id)
        if link_id not in article_map:
            issues.append(f"Invalid article link: {link_id}")

    # Check all cluster articles are referenced
    unreferenced = cluster_article_ids - referenced_article_ids
    if unreferenced:
        titles = [article_map.get(aid, {}).get("title", aid)[:40] for aid in unreferenced]
        issues.append(f"Unreferenced articles: {', '.join(titles)}")

    # Check no banned headings
    for line in synthesis_md.split("\n"):
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if heading in BANNED_HEADINGS:
                issues.append(f"Banned heading: {line}")

    # Check minimum paragraph count
    paragraphs = [p for p in synthesis_md.split("\n\n") if len(p.strip()) > 50]
    if len(paragraphs) < len(sections) * 2:
        issues.append(f"Too few paragraphs: {len(paragraphs)} (expected >= {len(sections) * 2})")

    # Check tension blocks present
    tension_count = synthesis_md.count("⚡")
    if tension_count == 0 and len(tensions) > 0:
        issues.append("No tension blocks found in synthesis")

    if verbose:
        log(f"  Deterministic checks: {len(issues)} issues")
        for issue in issues:
            log(f"    - {issue}")

    # 3. Compute coverage using similarity data
    article_claims_map = ki.get("article_claims", {})
    claims_dict = ki.get("claims", {})
    similarities = ki.get("similarities", [])

    # Build set of all claim IDs that are "covered" by the synthesis
    # A claim is covered if its article is referenced in the synthesis
    covered_claims = set()
    for aid in referenced_article_ids:
        if aid in cluster_article_ids:
            covered_claims.update(article_claims_map.get(aid, []))

    # Also expand via similarity: claims similar to covered claims
    all_cluster_claims = set()
    for aid in cluster_article_ids:
        all_cluster_claims.update(article_claims_map.get(aid, []))

    expanded_covered = set(covered_claims)
    for pair in similarities:
        if pair["score"] >= THRESHOLD_KNOWN:
            cid_a, cid_b = pair["a"], pair["b"]
            if cid_a in expanded_covered and cid_b in all_cluster_claims:
                expanded_covered.add(cid_b)
            elif cid_b in expanded_covered and cid_a in all_cluster_claims:
                expanded_covered.add(cid_a)

    claims_covered = sorted(expanded_covered & all_cluster_claims)

    # Per-article coverage
    article_coverage = {}
    for aid in cluster_article_ids:
        art_claims = set(article_claims_map.get(aid, []))
        if not art_claims:
            article_coverage[aid] = 1.0  # No claims = fully covered
            continue
        covered_count = len(art_claims & expanded_covered)
        article_coverage[aid] = round(covered_count / len(art_claims), 3)

    # 4. Generate follow-up questions (parallel with verification)
    follow_up_questions = _generate_follow_up_questions(
        synthesis_md, brief, tensions, article_map, verbose
    )

    # 5. Build unique_per_article from brief
    unique_per_article = {}
    for aid, claims in brief.get("unique_claims_per_article", {}).items():
        unique_per_article[aid] = [c["text"] for c in claims[:3]]

    # 6. Build final tensions list from narrated tensions
    final_tensions = []
    for t in tensions:
        art_a = article_map.get(t["side_a"]["article_id"], {})
        art_b = article_map.get(t["side_b"]["article_id"], {})
        final_tensions.append({
            "label": t["label"],
            "description": (
                f'{t["description"]} '
                f'[{art_a.get("title", "?")}](article:{t["side_a"]["article_id"]}) vs '
                f'[{art_b.get("title", "?")}](article:{t["side_b"]["article_id"]})'
            ),
            "article_ids": [t["side_a"]["article_id"], t["side_b"]["article_id"]],
        })

    total_claims_in_cluster = len(all_cluster_claims)

    result = {
        "cluster_id": cluster_id,
        "label": brief.get("label", "Unlabeled"),
        "synthesis_markdown": synthesis_md,
        "article_ids": sorted(cluster_article_ids),
        "article_coverage": article_coverage,
        "claims_covered": claims_covered,
        "unique_per_article": unique_per_article,
        "follow_up_questions": follow_up_questions,
        "tensions": final_tensions,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(cluster_article_ids),
        "total_claims_covered": len(claims_covered),
        "total_claims_in_cluster": total_claims_in_cluster,
        "pipeline_version": 2,
        "pipeline_issues": issues,
    }

    log(f"  Assembly complete: {len(synthesis_md)} chars, "
        f"{len(claims_covered)}/{total_claims_in_cluster} claims covered, "
        f"{len(follow_up_questions)} questions, {len(final_tensions)} tensions")
    if issues:
        log(f"  Issues: {len(issues)}")

    return result


def _generate_follow_up_questions(synthesis_md: str, brief: dict,
                                   tensions: list[dict], article_map: dict,
                                   verbose: bool = False) -> list[dict]:
    """Generate research follow-up questions."""
    from gemini_llm import call_llm

    # Build a compact summary of what the synthesis covers
    tension_labels = [t["label"] for t in tensions[:5]]

    prompt = f"""Based on this synthesis about "{brief.get('label', 'topic')}", generate 5 follow-up research questions.

SYNTHESIS (first 2000 chars):
{synthesis_md[:2000]}

TENSIONS IDENTIFIED:
{chr(10).join(f'- {t}' for t in tension_labels)}

Return JSON array of 5 objects:
[
  {{
    "question": "A specific question a curious reader would want answered",
    "research_prompt": "A search query to find the answer",
    "related_topics": ["topic1", "topic2"]
  }}
]

Questions should be SPECIFIC and build on the synthesis — not generic. They should point to gaps in the current knowledge or unresolved tensions."""

    response = call_llm(
        prompt,
        model=MODEL_EXTRACTION,
        max_tokens=1500,
        response_mime_type="application/json",
    )

    if response:
        try:
            questions = json.loads(response)
            if isinstance(questions, list):
                return questions[:5]
        except json.JSONDecodeError:
            pass

    return []


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(cluster: dict, article_map: dict, ki: dict,
                 verbose: bool = False, start_stage: int = 0,
                 end_stage: int = 4, approach: str = "thematic") -> dict | None:
    """Run the full multi-stage pipeline for a single cluster."""
    cluster_id = f"cluster_{cluster['cluster_id']}"
    # Use approach-specific subdirectories for stages 2+ artifacts
    stage_dir = STAGES_DIR / cluster_id
    if approach != "thematic":
        approach_dir = STAGES_DIR / cluster_id / f"approach_{approach}"
        approach_dir.mkdir(parents=True, exist_ok=True)
    else:
        approach_dir = stage_dir
    stage_dir.mkdir(parents=True, exist_ok=True)

    timings = {}
    report = {"cluster_id": cluster_id, "label": cluster.get("label", ""), "timings": timings}

    # Stage 0: Build brief
    if start_stage <= 0:
        t0 = time.time()
        brief = stage_0_build_brief(cluster, article_map, ki, verbose=verbose)
        timings["stage_0"] = round(time.time() - t0, 1)
        (stage_dir / "brief.json").write_text(
            json.dumps(brief, indent=2, ensure_ascii=False)
        )
        log(f"  Saved brief.json ({timings['stage_0']}s)")
    else:
        brief_path = stage_dir / "brief.json"
        if not brief_path.exists():
            log(f"  ERROR: brief.json not found. Run stage 0 first.")
            return None
        brief = json.loads(brief_path.read_text())
        log(f"  Loaded cached brief.json")

    if end_stage < 1:
        return None

    # Stage 1: Tension narration
    if start_stage <= 1:
        t0 = time.time()
        tensions = stage_1_narrate_tensions(brief, article_map, verbose=verbose)
        timings["stage_1"] = round(time.time() - t0, 1)
        (stage_dir / "tensions.json").write_text(
            json.dumps(tensions, indent=2, ensure_ascii=False)
        )
        log(f"  Saved tensions.json ({timings['stage_1']}s)")
    else:
        tensions_path = stage_dir / "tensions.json"
        if not tensions_path.exists():
            log(f"  ERROR: tensions.json not found. Run stage 1 first.")
            return None
        tensions = json.loads(tensions_path.read_text())
        log(f"  Loaded cached tensions.json")

    if end_stage < 2:
        return None

    # Stage 2: Outline
    if start_stage <= 2:
        t0 = time.time()
        outline = stage_2_generate_outline(brief, tensions, article_map,
                                           verbose=verbose, approach=approach)
        timings["stage_2"] = round(time.time() - t0, 1)
        (approach_dir / "outline.json").write_text(
            json.dumps(outline, indent=2, ensure_ascii=False)
        )
        log(f"  Saved outline.json ({timings['stage_2']}s) [approach={approach}]")
    else:
        outline_path = approach_dir / "outline.json"
        if not outline_path.exists():
            log(f"  ERROR: outline.json not found. Run stage 2 first.")
            return None
        outline = json.loads(outline_path.read_text())
        log(f"  Loaded cached outline.json")

    if end_stage < 3:
        return None

    # Stage 3: Prose generation
    if start_stage <= 3:
        t0 = time.time()
        sections = stage_3_generate_prose(outline, brief, tensions, article_map,
                                          verbose=verbose, approach=approach)
        timings["stage_3"] = round(time.time() - t0, 1)

        # Save individual sections
        sec_dir = approach_dir / "sections"
        sec_dir.mkdir(exist_ok=True)
        for sec in sections:
            (sec_dir / f"section_{sec['index']}.md").write_text(sec["prose"])

        (approach_dir / "sections_meta.json").write_text(
            json.dumps(sections, indent=2, ensure_ascii=False)
        )
        log(f"  Saved {len(sections)} sections ({timings['stage_3']}s) [approach={approach}]")
    else:
        meta_path = approach_dir / "sections_meta.json"
        if not meta_path.exists():
            log(f"  ERROR: sections_meta.json not found. Run stage 3 first.")
            return None
        sections = json.loads(meta_path.read_text())
        log(f"  Loaded cached sections")

    if end_stage < 4:
        return None

    # Stage 4: Assembly & verification
    t0 = time.time()
    result = stage_4_assemble_and_verify(
        sections, brief, tensions, outline, article_map, ki, verbose=verbose
    )
    timings["stage_4"] = round(time.time() - t0, 1)

    # Save assembled synthesis
    (approach_dir / "assembled.md").write_text(result["synthesis_markdown"])

    # Save report
    report["timings"] = timings
    report["total_time"] = round(sum(timings.values()), 1)
    report["synthesis_chars"] = len(result["synthesis_markdown"])
    report["claims_covered"] = result["total_claims_covered"]
    report["total_claims"] = result["total_claims_in_cluster"]
    report["issues"] = result.get("pipeline_issues", [])
    (approach_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )

    log(f"\n  Pipeline complete for {cluster_id}")
    log(f"  Total time: {report['total_time']}s")
    log(f"  Timings: {timings}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Multi-stage synthesis pipeline for Petrarca concept clusters"
    )
    parser.add_argument("--cluster-id", type=int, default=None,
                        help="Run pipeline for cluster with this numeric ID")
    parser.add_argument("--all", action="store_true",
                        help="Run pipeline for all clusters with >= 2 articles")
    parser.add_argument("--stage", type=int, default=None, choices=[0, 1, 2, 3, 4],
                        help="Run only this stage (uses cached artifacts from prior stages)")
    parser.add_argument("--min-articles", type=int, default=2,
                        help="Minimum articles per cluster (default: 2)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if artifacts exist")
    parser.add_argument("--save-to-syntheses", action="store_true",
                        help="Merge result into data/syntheses.json")
    parser.add_argument("--approach", type=str, default="thematic",
                        choices=APPROACHES,
                        help="Synthesis approach: thematic (default), dialectical, progressive, narrative")
    parser.add_argument("--all-approaches", action="store_true",
                        help="Run all 4 approaches for comparison (reuses cached Stage 0 & 1)")
    args = parser.parse_args()

    if not args.all and args.cluster_id is None:
        parser.error("Specify --cluster-id N or --all")

    log("=== Petrarca Multi-Stage Synthesis Pipeline ===")
    log("")

    # Load data
    article_map, ki, clusters_data, existing_syntheses = load_all_data()
    all_clusters = clusters_data.get("clusters", [])

    # Determine stage range
    start_stage = args.stage if args.stage is not None else 0
    end_stage = args.stage if args.stage is not None else 4

    # Select target clusters
    targets = []
    for cluster in all_clusters:
        if cluster["size"] < args.min_articles:
            continue
        if args.cluster_id is not None and cluster["cluster_id"] != args.cluster_id:
            continue
        targets.append(cluster)

    if not targets:
        log("No clusters matched selection criteria.")
        if args.cluster_id is not None:
            log(f"Available cluster IDs:")
            for c in all_clusters:
                if c["size"] >= args.min_articles:
                    log(f"  #{c['cluster_id']} [{c['size']} articles] {c['label']}")
        sys.exit(1)

    log(f"Targets: {len(targets)} clusters")
    for c in targets:
        log(f"  #{c['cluster_id']} [{c['size']} articles, "
            f"{c['total_unique_claims']} claims] {c['label']}")

    # Determine approaches to run
    approaches_to_run = APPROACHES if args.all_approaches else [args.approach]

    # Run pipeline
    results = []
    for cluster in targets:
        cluster_id = f"cluster_{cluster['cluster_id']}"
        for cur_approach in approaches_to_run:
            log(f"\n{'#'*60}")
            log(f"  Processing: {cluster_id} — {cluster['label']} [{cur_approach}]")
            log(f"{'#'*60}")

            # For --all-approaches, reuse cached Stage 0 & 1
            effective_start = start_stage
            if args.all_approaches and cur_approach != approaches_to_run[0]:
                effective_start = max(start_stage, 2)

            result = run_pipeline(
                cluster, article_map, ki,
                verbose=args.verbose,
                start_stage=effective_start,
                end_stage=end_stage,
                approach=cur_approach,
            )

            if result:
                result["approach"] = cur_approach
                results.append(result)

    if not results:
        log("\nNo syntheses generated.")
        sys.exit(0)

    # Optionally merge into syntheses.json
    if args.save_to_syntheses and results:
        merged = dict(existing_syntheses)
        for r in results:
            merged[r["cluster_id"]] = r

        all_syntheses = sorted(merged.values(), key=lambda s: -s.get("total_articles", 0))
        output = {
            "version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "total_syntheses": len(all_syntheses),
                "total_articles_covered": len(set(
                    aid for s in all_syntheses for aid in s.get("article_ids", [])
                )),
                "total_claims_covered": sum(
                    s.get("total_claims_covered", 0) for s in all_syntheses
                ),
            },
            "syntheses": all_syntheses,
        }
        SYNTHESES_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        log(f"\nMerged {len(results)} syntheses into {SYNTHESES_PATH}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Multi-Stage Synthesis Pipeline Results")
    print(f"{'='*60}")
    for r in results:
        coverage_vals = list(r.get("article_coverage", {}).values())
        avg_coverage = sum(coverage_vals) / len(coverage_vals) if coverage_vals else 0
        approach_label = r.get("approach", "thematic")
        print(f"\n  {r['cluster_id']}: {r['label']} [{approach_label}]")
        print(f"    Synthesis: {len(r.get('synthesis_markdown', ''))} chars")
        print(f"    Claims: {r['total_claims_covered']}/{r['total_claims_in_cluster']}")
        print(f"    Avg coverage: {avg_coverage:.0%}")
        print(f"    Tensions: {len(r.get('tensions', []))}")
        print(f"    Follow-ups: {len(r.get('follow_up_questions', []))}")
        issues = r.get("pipeline_issues", [])
        if issues:
            print(f"    Issues: {len(issues)}")
            for issue in issues:
                print(f"      - {issue}")


if __name__ == "__main__":
    main()
