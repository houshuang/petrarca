#!/usr/bin/env python3
"""LLM usage auditing for Petrarca pipeline scripts.

Tracks token usage, costs, and cache hits across all LLM calls.
Stores audit records as JSONL in data/llm_audit.jsonl.

Usage:
    from llm_audit import audit_llm_call, get_audit_summary

    # Wrap litellm completion calls
    response = completion(model=model, messages=messages)
    audit_llm_call(response, script="build_articles.py", purpose="claims_extraction")

    # View summary
    python3 scripts/llm_audit.py                    # today's usage
    python3 scripts/llm_audit.py --days 7            # last 7 days
    python3 scripts/llm_audit.py --since 2026-03-01  # since date
"""

import json
import sys
import os
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
AUDIT_PATH = PROJECT_DIR / "data" / "llm_audit.jsonl"

# Approximate costs per 1M tokens (Gemini Flash 2.0)
COST_PER_1M_INPUT = 0.10   # $0.10 / 1M input tokens
COST_PER_1M_OUTPUT = 0.40  # $0.40 / 1M output tokens
COST_PER_1M_CACHED = 0.025 # $0.025 / 1M cached input tokens

_audit_lock = Lock()


def audit_llm_call(response, script: str = "", purpose: str = "") -> dict:
    """Record a litellm completion response for auditing.

    Args:
        response: litellm completion response object
        script: name of the calling script (e.g. "build_articles.py")
        purpose: what this call is for (e.g. "claims_extraction", "delta_report")

    Returns:
        Audit record dict
    """
    usage = getattr(response, "usage", None) or {}
    if hasattr(usage, "prompt_tokens"):
        prompt_tokens = usage.prompt_tokens or 0
        completion_tokens = usage.completion_tokens or 0
        total_tokens = usage.total_tokens or 0
        cached_tokens = getattr(usage, "prompt_tokens_details", None)
        if cached_tokens and hasattr(cached_tokens, "cached_tokens"):
            cached = cached_tokens.cached_tokens or 0
        else:
            cached = 0
    elif isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    else:
        prompt_tokens = completion_tokens = total_tokens = cached = 0

    model = getattr(response, "model", "") or ""

    # Compute cost
    non_cached_input = prompt_tokens - cached
    cost = (
        (non_cached_input / 1_000_000) * COST_PER_1M_INPUT
        + (cached / 1_000_000) * COST_PER_1M_CACHED
        + (completion_tokens / 1_000_000) * COST_PER_1M_OUTPUT
    )

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "script": script,
        "purpose": purpose,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached,
        "cost_usd": round(cost, 6),
    }

    with _audit_lock:
        with open(AUDIT_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")

    return record


def get_audit_records(since: datetime | None = None) -> list[dict]:
    """Load audit records, optionally filtered by date."""
    if not AUDIT_PATH.exists():
        return []

    records = []
    with open(AUDIT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if since:
                    ts = datetime.fromisoformat(r["ts"].replace("Z", "+00:00"))
                    if ts < since:
                        continue
                records.append(r)
            except (json.JSONDecodeError, KeyError):
                continue
    return records


def get_audit_summary(since: datetime | None = None) -> dict:
    """Summarize LLM usage and costs."""
    records = get_audit_records(since)
    if not records:
        return {"total_calls": 0, "total_cost_usd": 0}

    by_script: dict[str, dict] = {}
    by_model: dict[str, dict] = {}

    total_prompt = total_completion = total_cached = 0
    total_cost = 0.0

    for r in records:
        script = r.get("script", "unknown")
        model = r.get("model", "unknown")

        for grouping, key in [(by_script, script), (by_model, model)]:
            if key not in grouping:
                grouping[key] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                 "cached_tokens": 0, "cost_usd": 0.0}
            g = grouping[key]
            g["calls"] += 1
            g["prompt_tokens"] += r.get("prompt_tokens", 0)
            g["completion_tokens"] += r.get("completion_tokens", 0)
            g["cached_tokens"] += r.get("cached_tokens", 0)
            g["cost_usd"] += r.get("cost_usd", 0)

        total_prompt += r.get("prompt_tokens", 0)
        total_completion += r.get("completion_tokens", 0)
        total_cached += r.get("cached_tokens", 0)
        total_cost += r.get("cost_usd", 0)

    return {
        "total_calls": len(records),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_cached_tokens": total_cached,
        "total_cost_usd": round(total_cost, 4),
        "by_script": by_script,
        "by_model": by_model,
        "period": {
            "from": records[0].get("ts", ""),
            "to": records[-1].get("ts", ""),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="View LLM usage audit")
    parser.add_argument("--days", type=int, default=1, help="Show usage for last N days (default: 1)")
    parser.add_argument("--since", type=str, help="Show usage since date (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

    summary = get_audit_summary(since)

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    if summary["total_calls"] == 0:
        print("No LLM calls recorded in this period.")
        return

    print(f"\n{'='*50}")
    print(f"  Petrarca LLM Usage Audit")
    print(f"{'='*50}")
    print(f"  Period: {summary['period']['from']} → {summary['period']['to']}")
    print(f"  Total calls:       {summary['total_calls']}")
    print(f"  Prompt tokens:     {summary['total_prompt_tokens']:,}")
    print(f"  Completion tokens: {summary['total_completion_tokens']:,}")
    print(f"  Cached tokens:     {summary['total_cached_tokens']:,}")
    print(f"  Total cost:        ${summary['total_cost_usd']:.4f}")
    print()

    if summary["by_script"]:
        print("  By script:")
        for script, data in sorted(summary["by_script"].items(), key=lambda x: x[1]["cost_usd"], reverse=True):
            print(f"    {script}: {data['calls']} calls, ${data['cost_usd']:.4f}")

    if summary["by_model"]:
        print("\n  By model:")
        for model, data in sorted(summary["by_model"].items()):
            print(f"    {model}: {data['calls']} calls, {data['prompt_tokens']:,} in / {data['completion_tokens']:,} out")
    print()


if __name__ == "__main__":
    main()
