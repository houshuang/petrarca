#!/usr/bin/env python3
"""Generate synthetic benchmark dataset for document similarity testing.

Generates 50 article pairs across 5 overlap categories using Gemini,
then validates with amygdala embeddings.
"""

import json
import os
import sys
import time

import numpy as np
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))

os.chdir("/Users/stian/src/petrarca/scripts")
sys.path.insert(0, ".")

# TODO(session-88): migrate to claude_llm when this script gets revived
from gemini_llm import call_llm

from limbic.amygdala import EmbeddingModel

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES = [
    {
        "name": "near_duplicate",
        "expected_score": 4,
        "description": "Near-duplicates: same topic covered from slightly different angles or sources",
        "prompt": """Generate 10 pairs of article summaries that are NEAR-DUPLICATES — they cover the SAME specific event, product, study, or topic from slightly different angles, sources, or publication dates.

Requirements:
- Both articles in each pair discuss the SAME specific subject (same company, same study, same event)
- They should differ in framing, detail emphasis, or information source — like two newspapers covering the same story
- Use diverse domains: mix tech, science, policy, history, culture across the 10 pairs
- Make titles realistic (like real publication headlines)
- Summaries should be 3-5 sentences with specific details (numbers, names, dates)
- Key claims should be insights/patterns/comparisons, NOT feature lists
- Each article should have exactly 3 key claims

Examples of pair concepts (use these as inspiration, vary widely):
- Two different news articles about the same AI product launch
- Two reviews of the same scientific study on ocean temperatures
- Two analyses of the same election result
- Two reports on the same archaeological discovery""",
    },
    {
        "name": "shared_theme",
        "expected_score": 2.5,
        "description": "Shared themes, different specifics: same broad theme but different specific topics",
        "prompt": """Generate 10 pairs of article summaries that share a BROAD THEME but cover DIFFERENT SPECIFIC TOPICS within that theme.

Requirements:
- Both articles relate to the same general area/theme, but focus on different specific subjects
- The connection should be clear but the content substantially different
- Use diverse themes: agent safety, climate adaptation, medieval history, public health, urban design, etc.
- Make titles realistic
- Summaries should be 3-5 sentences with specific details
- Key claims should be insights/patterns/comparisons
- Each article should have exactly 3 key claims

Examples of pair concepts:
- One about agent sandboxing, another about agent orchestration — both agent safety
- One about Venice flooding, another about Miami sea walls — both climate adaptation
- One about Viking trade routes, another about Hanseatic League — both medieval commerce
- One about mRNA vaccines, another about CRISPR gene therapy — both biotech""",
    },
    {
        "name": "same_field",
        "expected_score": 1,
        "description": "Same field, different topics: same broad field but covering unrelated aspects",
        "prompt": """Generate 10 pairs of article summaries in the SAME BROAD FIELD but covering UNRELATED ASPECTS of that field.

Requirements:
- Both articles belong to the same academic/professional field
- But they cover completely different sub-topics with no meaningful overlap
- The only connection is the field itself
- Use diverse fields: AI/ML, biology, architecture, economics, linguistics, physics, etc.
- Make titles realistic
- Summaries should be 3-5 sentences with specific details
- Key claims should be insights/patterns/comparisons
- Each article should have exactly 3 key claims

Examples of pair concepts:
- One about LLM fine-tuning, another about AI agent UI design
- One about protein folding, another about marine ecosystem pH levels
- One about Gothic cathedral acoustics, another about brutalist housing projects
- One about monetary policy in Japan, another about gig economy labor markets""",
    },
    {
        "name": "cross_domain_connection",
        "expected_score": 1.5,
        "description": "Cross-domain with surprising abstract connections",
        "prompt": """Generate 10 pairs of article summaries from DIFFERENT DOMAINS that share a SURPRISING ABSTRACT PATTERN or structural similarity.

Requirements:
- Articles come from clearly different fields/domains
- But they share an abstract pattern, structural similarity, or analogous dynamic
- The connection should be genuine and interesting, not forced
- Describe the abstract connection in the overlap_description
- Use creative cross-domain pairings
- Make titles realistic
- Summaries should be 3-5 sentences with specific details
- Key claims should be insights/patterns/comparisons
- Each article should have exactly 3 key claims

Examples of pair concepts:
- "Byzantine administrative systems" and "microservice architecture" — both managing distributed complexity
- "Ant colony foraging optimization" and "internet packet routing" — both emergent routing algorithms
- "Renaissance banking innovation" and "DeFi protocol design" — both financial trust systems
- "Coral reef symbiosis" and "open source ecosystem dynamics" — both mutual dependency networks""",
    },
    {
        "name": "unrelated",
        "expected_score": 0,
        "description": "Completely unrelated: no thematic connection whatsoever",
        "prompt": """Generate 10 pairs of article summaries that are COMPLETELY UNRELATED — no thematic, structural, or conceptual connection.

Requirements:
- Maximize the topical distance between articles in each pair
- Mix widely: combine hard science with arts, ancient history with modern tech, food with physics, etc.
- There should be NO abstract pattern or hidden connection
- Use diverse, specific topics (not vague)
- Make titles realistic
- Summaries should be 3-5 sentences with specific details
- Key claims should be insights/patterns/comparisons
- Each article should have exactly 3 key claims

Examples of pair concepts:
- "Sicilian baroque architecture" and "Python async programming"
- "Traditional Japanese fermentation techniques" and "Hubble constant measurements"
- "Norwegian stave church preservation" and "GPU memory bandwidth optimization"
- "History of the French baguette law" and "Saturn's ring composition analysis" """,
    },
]

SYSTEM_INSTRUCTION = """You are generating synthetic article summaries for a document similarity benchmark dataset.
Your output must be valid JSON — an array of exactly 10 objects.
Each object represents a pair of articles with controlled overlap.
Be specific and realistic: use real-sounding names, numbers, dates, and details.
Key claims should be INSIGHTS (patterns, comparisons, implications) not feature lists."""

PAIR_SCHEMA = """\nReturn a JSON array of exactly 10 objects, each with this structure:
{
  "article_a": {
    "title": "Realistic headline",
    "summary": "3-5 sentences with specific details",
    "key_claims": ["insight 1", "insight 2", "insight 3"]
  },
  "article_b": {
    "title": "Realistic headline",
    "summary": "3-5 sentences with specific details",
    "key_claims": ["insight 1", "insight 2", "insight 3"]
  },
  "overlap_description": "Why these have this overlap level"
}"""


def generate_category(category: dict) -> list[dict]:
    """Generate 10 pairs for a single category via LLM."""
    prompt = category["prompt"] + PAIR_SCHEMA

    print(f"\nGenerating category: {category['name']} ...")
    result = call_llm(
        prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        max_tokens=16000,
        response_mime_type="application/json",
    )

    if not result:
        print(f"  ERROR: No response for {category['name']}")
        return []

    try:
        pairs = json.loads(result)
    except json.JSONDecodeError as e:
        print(f"  ERROR parsing JSON for {category['name']}: {e}")
        print(f"  Raw response (first 500 chars): {result[:500]}")
        return []

    if not isinstance(pairs, list):
        print(f"  ERROR: Expected list, got {type(pairs)}")
        return []

    print(f"  Got {len(pairs)} pairs")

    # Annotate with category metadata
    for pair in pairs:
        pair["category"] = category["name"]
        pair["expected_score"] = category["expected_score"]

    return pairs


def validate_with_embeddings(benchmark: list[dict]) -> list[dict]:
    """Embed all summaries and compute cosine similarities."""
    print("\nEmbedding summaries with amygdala MiniLM ...")
    model = EmbeddingModel()

    # Collect all summary texts
    texts_a = []
    texts_b = []
    for pair in benchmark:
        # Combine summary + claims for richer representation
        text_a = pair["article_a"]["summary"] + " " + " ".join(pair["article_a"]["key_claims"])
        text_b = pair["article_b"]["summary"] + " " + " ".join(pair["article_b"]["key_claims"])
        texts_a.append(text_a)
        texts_b.append(text_b)

    emb_a = model.embed_batch(texts_a)
    emb_b = model.embed_batch(texts_b)

    # Compute per-pair cosine similarity
    for i, pair in enumerate(benchmark):
        a = emb_a[i]
        b = emb_b[i]
        cos_sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        pair["cosine_similarity"] = round(cos_sim, 4)

    return benchmark


def analyze_results(benchmark: list[dict]):
    """Print correlation analysis between expected scores and cosine sims."""
    print("\n" + "=" * 70)
    print("BENCHMARK VALIDATION RESULTS")
    print("=" * 70)

    categories = {}
    for pair in benchmark:
        cat = pair["category"]
        if cat not in categories:
            categories[cat] = {"expected": pair["expected_score"], "cosines": []}
        categories[cat]["cosines"].append(pair["cosine_similarity"])

    print(f"\n{'Category':<30} {'Expected':>8} {'Mean Cos':>9} {'Min':>7} {'Max':>7} {'StdDev':>7}")
    print("-" * 70)

    all_expected = []
    all_cosine = []
    mismatches = []

    for cat_name in ["near_duplicate", "shared_theme", "same_field", "cross_domain_connection", "unrelated"]:
        if cat_name not in categories:
            continue
        data = categories[cat_name]
        cosines = data["cosines"]
        mean_c = np.mean(cosines)
        min_c = np.min(cosines)
        max_c = np.max(cosines)
        std_c = np.std(cosines)
        print(f"{cat_name:<30} {data['expected']:>8.1f} {mean_c:>9.4f} {min_c:>7.4f} {max_c:>7.4f} {std_c:>7.4f}")

        all_expected.extend([data["expected"]] * len(cosines))
        all_cosine.extend(cosines)

    # Spearman rank correlation
    from scipy.stats import spearmanr, pearsonr

    spearman_r, spearman_p = spearmanr(all_expected, all_cosine)
    pearson_r, pearson_p = pearsonr(all_expected, all_cosine)

    print(f"\nSpearman rank correlation: r={spearman_r:.4f}, p={spearman_p:.2e}")
    print(f"Pearson correlation:       r={pearson_r:.4f}, p={pearson_p:.2e}")

    # Flag mismatches: pairs where cosine doesn't match expected ordering
    print("\nSURPRISING MISMATCHES (cosine disagrees with expected):")
    print("-" * 70)

    # Define expected cosine ranges per category
    expected_ranges = {
        "near_duplicate": (0.65, 1.0),
        "shared_theme": (0.45, 0.80),
        "same_field": (0.20, 0.55),
        "cross_domain_connection": (0.20, 0.60),
        "unrelated": (-0.1, 0.35),
    }

    mismatch_count = 0
    for i, pair in enumerate(benchmark):
        cat = pair["category"]
        cos = pair["cosine_similarity"]
        lo, hi = expected_ranges.get(cat, (0, 1))
        if cos < lo or cos > hi:
            mismatch_count += 1
            pair["mismatch"] = True
            print(f"  [{cat}] cos={cos:.4f} (expected {lo:.2f}-{hi:.2f})")
            print(f"    A: {pair['article_a']['title']}")
            print(f"    B: {pair['article_b']['title']}")
        else:
            pair["mismatch"] = False

    if mismatch_count == 0:
        print("  None! All pairs fall within expected cosine ranges.")
    else:
        print(f"\n  Total mismatches: {mismatch_count}/{len(benchmark)}")

    return benchmark


def main():
    all_pairs = []

    for category in CATEGORIES:
        pairs = generate_category(category)
        if pairs:
            all_pairs.extend(pairs)
        # Small delay between API calls
        time.sleep(1)

    print(f"\nTotal pairs generated: {len(all_pairs)}")

    if not all_pairs:
        print("ERROR: No pairs generated. Check API key and connectivity.")
        sys.exit(1)

    # Validate with embeddings
    all_pairs = validate_with_embeddings(all_pairs)

    # Analyze results
    all_pairs = analyze_results(all_pairs)

    # Save
    output_path = "/Users/stian/src/petrarca/scripts/ground-truth/synthetic_benchmark.json"
    with open(output_path, "w") as f:
        json.dump(all_pairs, f, indent=2)

    print(f"\nSaved {len(all_pairs)} pairs to {output_path}")


if __name__ == "__main__":
    main()
