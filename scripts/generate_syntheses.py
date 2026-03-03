#!/usr/bin/env python3
"""Generate cross-article syntheses for topic clusters.

Groups articles by primary topic (topics[0]), generates a synthesis
via `claude -p` for topics with 3+ articles.

Usage:
    python3 scripts/generate_syntheses.py
    python3 scripts/generate_syntheses.py --min-articles 2   # lower threshold
    python3 scripts/generate_syntheses.py --dry-run           # skip LLM calls
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
APP_DATA_DIR = PROJECT_DIR / "app" / "data"
ARTICLES_PATH = APP_DATA_DIR / "articles.json"
SYNTHESES_PATH = APP_DATA_DIR / "syntheses.json"


def _call_claude(prompt: str, timeout: int = 180) -> str | None:
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--max-turns", "1"],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"    claude error: {result.stderr[:200]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"    claude timed out after {timeout}s", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("    claude CLI not found", file=sys.stderr)
        return None


def group_by_primary_topic(articles: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        if a.get("topics"):
            primary = a["topics"][0]
            groups[primary].append(a)
    return dict(groups)


def build_synthesis_prompt(topic: str, articles: list[dict]) -> str:
    article_summaries = []
    for a in articles:
        claims = "\n".join(f"  - {c}" for c in a.get("key_claims", []))
        article_summaries.append(
            f"Title: {a['title']}\n"
            f"Summary: {a.get('full_summary', a.get('one_line_summary', ''))}\n"
            f"Key claims:\n{claims}"
        )

    joined = "\n---\n".join(article_summaries)

    return f"""You are synthesizing {len(articles)} articles about the topic "{topic}" for a read-later app.

The reader has saved these articles and wants to understand the landscape of ideas across them.

Articles:
{joined}

Write a synthesis (3-6 paragraphs) covering:
1. **Main themes**: What are the key ideas these articles share?
2. **Points of agreement**: Where do the articles converge?
3. **Points of tension**: Where do they disagree or offer different perspectives?
4. **Gaps**: What questions remain unanswered across these articles?

Style: Direct, informative, no filler. Write as if briefing an expert reader.
Do NOT use bullet points — use flowing prose paragraphs.
Return ONLY the synthesis text, no JSON wrapping or markdown headers."""


def generate_syntheses(articles: list[dict], min_articles: int = 3,
                       dry_run: bool = False) -> list[dict]:
    groups = group_by_primary_topic(articles)

    eligible = {
        topic: arts for topic, arts in groups.items()
        if len(arts) >= min_articles
    }

    if not eligible:
        print(f"  No topics with {min_articles}+ articles", file=sys.stderr)
        return []

    print(f"  Topics eligible for synthesis: {len(eligible)}", file=sys.stderr)
    for topic, arts in sorted(eligible.items(), key=lambda x: -len(x[1])):
        print(f"    {topic}: {len(arts)} articles", file=sys.stderr)

    syntheses = []

    for topic, arts in sorted(eligible.items(), key=lambda x: -len(x[1])):
        article_ids = [a["id"] for a in arts]

        if dry_run:
            print(f"  [dry-run] Would synthesize: {topic} ({len(arts)} articles)", file=sys.stderr)
            syntheses.append({
                "topic": topic,
                "synthesis_text": f"[dry run] Synthesis for {topic} across {len(arts)} articles.",
                "article_ids": article_ids,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })
            continue

        print(f"  Generating synthesis: {topic} ({len(arts)} articles)...", file=sys.stderr)
        prompt = build_synthesis_prompt(topic, arts)
        response = _call_claude(prompt)

        if response:
            # Strip any markdown code fences if present
            text = response
            if text.startswith("```"):
                text = re.sub(r"^```(?:\w+)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            print(f"    OK: {len(text)} chars", file=sys.stderr)
            syntheses.append({
                "topic": topic,
                "synthesis_text": text,
                "article_ids": article_ids,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            print(f"    FAILED for topic: {topic}", file=sys.stderr)

    return syntheses


def main():
    parser = argparse.ArgumentParser(description="Generate cross-article syntheses")
    parser.add_argument("--min-articles", type=int, default=3,
                        help="Minimum articles per topic for synthesis (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls")
    args = parser.parse_args()

    if not ARTICLES_PATH.exists():
        print(f"ERROR: No articles at {ARTICLES_PATH}", file=sys.stderr)
        sys.exit(1)

    articles = json.loads(ARTICLES_PATH.read_text())
    print(f"  Loaded {len(articles)} articles", file=sys.stderr)

    syntheses = generate_syntheses(articles, min_articles=args.min_articles,
                                   dry_run=args.dry_run)

    SYNTHESES_PATH.write_text(json.dumps(syntheses, indent=2, ensure_ascii=False))
    print(f"\n  {len(syntheses)} syntheses written to {SYNTHESES_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
