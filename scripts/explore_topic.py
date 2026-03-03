#!/usr/bin/env python3
"""Generate a topic exploration plan via claude -p.

Takes a seed topic and produces a structured reading plan with subtopics,
URLs, reading order, and connections to the user's existing knowledge.

Usage:
    python3 scripts/explore_topic.py "Sicily — history, literature, geography"
    python3 scripts/explore_topic.py "Sicily" --dry-run
    python3 scripts/explore_topic.py "Sicily" --concepts-file path/to/concepts.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
EXPLORATIONS_DIR = DATA_DIR / "explorations"
DEFAULT_CONCEPTS = PROJECT_DIR / "app" / "data" / "concepts.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        print(f"  claude error: {result.stderr[:200]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"  claude timed out after {timeout}s", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("  claude CLI not found", file=sys.stderr)
        return None


def _slugify(text: str) -> str:
    """Convert topic string to a filename-safe slug."""
    slug = text.lower()
    # Replace common separators with hyphens
    slug = re.sub(r"[—–\s,;:]+", "-", slug)
    # Remove anything that isn't alphanumeric or hyphen
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:80]


def _load_concepts(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  No concepts file at {path}", file=sys.stderr)
        return []
    try:
        concepts = json.loads(path.read_text())
        if isinstance(concepts, list):
            print(f"  Loaded {len(concepts)} existing concepts", file=sys.stderr)
            return concepts
    except (json.JSONDecodeError, OSError) as e:
        print(f"  Failed to load concepts: {e}", file=sys.stderr)
    return []


def _format_concepts_for_prompt(concepts: list[dict], max_concepts: int = 80) -> str:
    """Format concepts into a compact string for the prompt."""
    if not concepts:
        return "No existing concepts available."

    # Group by topic for readability
    by_topic: dict[str, list[dict]] = {}
    for c in concepts[:max_concepts]:
        topic = c.get("topic", "other")
        by_topic.setdefault(topic, []).append(c)

    lines = []
    for topic, topic_concepts in sorted(by_topic.items()):
        lines.append(f"\n[{topic}]")
        for c in topic_concepts:
            lines.append(f"  - {c['id']}: {c['text']}")

    return "\n".join(lines)


def _build_prompt(topic: str, concepts: list[dict]) -> str:
    concepts_block = _format_concepts_for_prompt(concepts)

    return f"""I want to explore this topic: "{topic}"

I'm a power reader with broad interests in history, literature, classical philology, educational research, politics, AI/technology. I read in English, Norwegian, Swedish, Danish, Italian, German, Spanish, French, Chinese, Indonesian, and Esperanto.

Here are concepts I already know about (from my reading app):
{concepts_block}

Generate a structured exploration plan. For each subtopic, suggest real Wikipedia articles or well-known reference URLs that are likely to exist. Prefer Wikipedia as the starting point since those URLs are stable and predictable.

Return a JSON object with this exact structure:
{{
  "topic": "{topic}",
  "subtopics": [
    {{
      "name": "short subtopic name",
      "description": "1-2 sentence description of what this covers",
      "reading_order": "foundational" or "intermediate" or "deep",
      "urls": ["https://en.wikipedia.org/wiki/...", "https://..."],
      "connects_to": ["concept_id_if_relevant"]
    }}
  ],
  "reading_order_note": "A paragraph explaining the suggested reading path through these subtopics",
  "existing_connections": [
    {{
      "concept_id": "id from the concepts list",
      "concept_text": "the concept text",
      "relevance": "how this existing knowledge connects to the new topic"
    }}
  ]
}}

Requirements:
- Generate 12-15 subtopics
- Each subtopic should have 2-3 URLs (prefer Wikipedia, but include other authoritative sources too)
- Distribute reading_order: roughly 4-5 foundational, 4-5 intermediate, 3-5 deep
- Only include connects_to and existing_connections for genuinely relevant matches — don't force connections
- The reading_order_note should give practical advice on how to approach this topic
- Consider multilingual sources where relevant (e.g., Italian Wikipedia for Italian topics)

Return ONLY valid JSON, no markdown fences or other text."""


def _parse_response(raw: str) -> dict | None:
    """Parse Claude's JSON response, handling markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        print(f"  First 200 chars: {cleaned[:200]}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a topic exploration plan via claude -p"
    )
    parser.add_argument(
        "topic",
        help='Topic to explore, e.g. "Sicily — history, literature, geography"',
    )
    parser.add_argument(
        "--concepts-file",
        type=Path,
        default=DEFAULT_CONCEPTS,
        help=f"Path to concepts.json (default: {DEFAULT_CONCEPTS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt instead of calling Claude",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout for claude call in seconds (default: 180)",
    )
    args = parser.parse_args()

    # Load existing concepts
    concepts = _load_concepts(args.concepts_file)

    # Build prompt
    prompt = _build_prompt(args.topic, concepts)

    if args.dry_run:
        print(prompt)
        return

    # Call Claude
    print(f"  Generating exploration plan for: {args.topic}", file=sys.stderr)
    raw = _call_claude(prompt, timeout=args.timeout)
    if not raw:
        print("ERROR: No response from Claude", file=sys.stderr)
        sys.exit(1)

    # Parse response
    plan = _parse_response(raw)
    if not plan:
        print("ERROR: Failed to parse response as JSON", file=sys.stderr)
        print("Raw response saved to stderr for debugging", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(1)

    # Add metadata
    plan["topic"] = args.topic
    plan["created_at"] = datetime.now(timezone.utc).isoformat()

    # Save
    slug = _slugify(args.topic)
    EXPLORATIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXPLORATIONS_DIR / f"{slug}.json"

    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False))

    # Summary
    subtopics = plan.get("subtopics", [])
    connections = plan.get("existing_connections", [])
    by_order = {}
    for st in subtopics:
        order = st.get("reading_order", "unknown")
        by_order[order] = by_order.get(order, 0) + 1

    print(f"\n  Saved: {out_path}", file=sys.stderr)
    print(f"  Subtopics: {len(subtopics)}", file=sys.stderr)
    for order, count in sorted(by_order.items()):
        print(f"    {order}: {count}", file=sys.stderr)
    print(f"  Connections to existing knowledge: {len(connections)}", file=sys.stderr)
    total_urls = sum(len(st.get("urls", [])) for st in subtopics)
    print(f"  Total URLs: {total_urls}", file=sys.stderr)


if __name__ == "__main__":
    main()
