#!/usr/bin/env python3
"""Compare LLM models for synthesis generation quality/speed/cost.

Runs the same synthesis prompt against multiple models and compares results.

Usage:
    python3 scripts/compare_synthesis_models.py --cluster-id 3
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

# Load env
for env_path in [PROJECT_DIR / ".env", Path("/opt/petrarca/.env")]:
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    if key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()

sys.path.insert(0, str(SCRIPT_DIR))
from generate_syntheses import (
    load_data, build_synthesis_prompt, parse_llm_response
)
from gemini_llm import call_llm

# Models to compare — pricing from Polaris aiModelsData.ts (per 1M tokens)
MODELS = [
    # name, model_id, input_price_per_1M, output_price_per_1M
    ("2.0 Flash", "gemini-2.0-flash", 0.10, 0.40),                       # Current synthesis model
    ("2.5 Flash Lite", "gemini-2.5-flash-lite", 0.15, 0.60),             # Cheapest new model
    ("3.1 Flash Lite", "gemini-3.1-flash-lite-preview", 0.25, 1.50),     # Current pipeline default
    ("2.5 Flash", "gemini-2.5-flash", 0.30, 2.50),                       # Reasoning capable
    ("3 Flash", "gemini-3-flash-preview", 0.50, 3.00),                   # Newest flash
    ("2.5 Pro", "gemini-2.5-pro", 1.25, 10.00),                          # Best quality
]


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars per token for English)."""
    return len(text) // 4


def evaluate_synthesis(result: dict, cluster: dict, article_map: dict) -> dict:
    """Score a synthesis result on multiple quality dimensions."""
    scores = {}

    md = result.get("synthesis_markdown", "")
    claims = result.get("claims_covered", [])
    coverage = result.get("article_coverage", {})
    questions = result.get("follow_up_questions", [])
    tensions = result.get("tensions", [])
    unique = result.get("unique_per_article", {})

    # Length and structure
    scores["synthesis_chars"] = len(md)
    scores["has_overview"] = "## Overview" in md
    scores["has_shared_themes"] = "## Shared Themes" in md or "## Shared" in md
    scores["has_unique"] = "## Unique" in md
    scores["has_tensions"] = "## Tensions" in md or "## Disagreements" in md
    scores["has_synthesis"] = "## Synthesis" in md or "## Takeaway" in md
    scores["section_count"] = sum([
        scores["has_overview"], scores["has_shared_themes"],
        scores["has_unique"], scores["has_tensions"], scores["has_synthesis"]
    ])

    # Claim coverage (before post-processing expansion)
    scores["llm_claims_tagged"] = len(claims)
    total_claims = sum(
        len(article_map.get(a["id"], {}).get("atomic_claims", []))
        for a in cluster["articles"]
    )
    scores["total_claims"] = total_claims

    # Article coverage
    coverage_vals = [v for v in coverage.values() if isinstance(v, (int, float))]
    scores["avg_coverage"] = sum(coverage_vals) / len(coverage_vals) if coverage_vals else 0
    scores["articles_with_coverage"] = len(coverage_vals)
    scores["articles_over_60pct"] = sum(1 for v in coverage_vals if v >= 0.6)

    # Follow-up quality
    scores["question_count"] = len(questions)
    scores["questions_with_research_prompt"] = sum(
        1 for q in questions if q.get("research_prompt")
    )

    # Tensions
    scores["tension_count"] = len(tensions)

    # Unique contributions
    scores["articles_with_unique"] = len(unique)

    # Specificity: count article title references in synthesis
    article_titles = [article_map.get(a["id"], {}).get("title", "") for a in cluster["articles"]]
    title_refs = sum(1 for t in article_titles if t and t[:30] in md)
    scores["title_references"] = title_refs

    # Claim ID references in text
    import re
    claim_refs = len(re.findall(r'\[[a-f0-9]{10,14}\]', md))
    scores["claim_id_references"] = claim_refs

    # Bold emphasis count
    scores["bold_count"] = len(re.findall(r'\*\*[^*]+\*\*', md))

    return scores


def main():
    parser = argparse.ArgumentParser(description="Compare LLM models for synthesis")
    parser.add_argument("--cluster-id", type=int, required=True,
                        help="Cluster ID to use as test case")
    parser.add_argument("--models", nargs="+", default=None,
                        help="Specific model names to test (default: all)")
    args = parser.parse_args()

    print("=== Synthesis Model Comparison ===\n", file=sys.stderr)

    articles, ki, clusters_data = load_data()
    article_map = {a["id"]: a for a in articles}
    all_clusters = clusters_data.get("clusters", [])

    cluster = None
    for c in all_clusters:
        if c.get("cluster_id") == args.cluster_id:
            cluster = c
            break

    if not cluster:
        print(f"Cluster {args.cluster_id} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Test cluster: {cluster['label']} ({cluster['size']} articles)\n", file=sys.stderr)

    prompt, system_instruction = build_synthesis_prompt(cluster, article_map, ki)
    input_tokens = estimate_tokens(prompt + (system_instruction or ""))
    print(f"Prompt: {len(prompt)} chars, ~{input_tokens} tokens\n", file=sys.stderr)

    models_to_test = MODELS
    if args.models:
        models_to_test = [m for m in MODELS if any(n.lower() in m[0].lower() for n in args.models)]

    results = []

    for name, model_id, in_price, out_price in models_to_test:
        print(f"--- {name} ({model_id}) ---", file=sys.stderr)

        start = time.time()
        response = call_llm(
            prompt,
            model=model_id,
            max_tokens=8192,
            system_instruction=system_instruction,
        )
        elapsed = time.time() - start

        if not response:
            print(f"  FAILED: No response\n", file=sys.stderr)
            results.append({
                "model": name, "model_id": model_id,
                "status": "FAILED", "time_s": elapsed
            })
            continue

        parsed = parse_llm_response(response)
        if not parsed:
            print(f"  FAILED: Could not parse JSON ({len(response)} chars)\n", file=sys.stderr)
            results.append({
                "model": name, "model_id": model_id,
                "status": "PARSE_FAILED", "time_s": elapsed,
                "response_chars": len(response)
            })
            continue

        output_tokens = estimate_tokens(response)
        cost = (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)

        scores = evaluate_synthesis(parsed, cluster, article_map)

        result = {
            "model": name,
            "model_id": model_id,
            "status": "OK",
            "time_s": round(elapsed, 1),
            "response_chars": len(response),
            "output_tokens_est": output_tokens,
            "cost_est": round(cost, 6),
            **scores,
        }
        results.append(result)

        print(f"  Time: {elapsed:.1f}s", file=sys.stderr)
        print(f"  Output: {len(response)} chars (~{output_tokens} tokens)", file=sys.stderr)
        print(f"  Cost: ${cost:.6f}", file=sys.stderr)
        print(f"  Sections: {scores['section_count']}/5", file=sys.stderr)
        print(f"  Claims tagged: {scores['llm_claims_tagged']}/{scores['total_claims']}", file=sys.stderr)
        print(f"  Avg coverage: {scores['avg_coverage']:.0%}", file=sys.stderr)
        print(f"  Title refs: {scores['title_references']}", file=sys.stderr)
        print(f"  Claim ID refs: {scores['claim_id_references']}", file=sys.stderr)
        print(f"  Bold emphasis: {scores['bold_count']}", file=sys.stderr)
        print(f"  Questions: {scores['question_count']}", file=sys.stderr)
        print(f"  Tensions: {scores['tension_count']}", file=sys.stderr)
        print("", file=sys.stderr)

    # Save full results
    output_path = DATA_DIR / "model_comparison.json"
    with open(output_path, "w") as f:
        json.dump({
            "cluster": cluster["label"],
            "cluster_id": cluster["cluster_id"],
            "prompt_chars": len(prompt),
            "input_tokens_est": input_tokens,
            "results": results,
        }, f, indent=2)

    # Print comparison table
    print("\n" + "=" * 100)
    print(f"{'Model':<20} {'Status':<8} {'Time':>6} {'Cost':>10} {'Chars':>6} "
          f"{'Sects':>5} {'Claims':>7} {'Cov%':>5} {'TitleRef':>8} {'ClaimRef':>8} "
          f"{'Bold':>5} {'Qs':>3} {'Tens':>4}")
    print("-" * 100)

    for r in results:
        if r["status"] != "OK":
            print(f"{r['model']:<20} {r['status']:<8} {r['time_s']:>5.1f}s")
            continue
        print(f"{r['model']:<20} {r['status']:<8} {r['time_s']:>5.1f}s "
              f"${r['cost_est']:>8.6f} {r['synthesis_chars']:>6} "
              f"{r['section_count']:>4}/5 {r['llm_claims_tagged']:>3}/{r['total_claims']:<3} "
              f"{r['avg_coverage']:>4.0%} {r['title_references']:>8} {r['claim_id_references']:>8} "
              f"{r['bold_count']:>5} {r['question_count']:>3} {r['tension_count']:>4}")

    print("=" * 100)
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()
