#!/usr/bin/env python3
"""Extract entity-style concepts from all articles using claude -p or API fallback.

Replaces the old sentence-style concepts with short, named knowledge entities.
Example: "Garibaldi", "Greek colonization of Sicily", "spaced repetition"

Usage:
  python3 scripts/extract_entity_concepts.py                # full extraction
  python3 scripts/extract_entity_concepts.py --test 3       # test with 3 articles
  python3 scripts/extract_entity_concepts.py --dry-run      # show prompts, don't call LLM
"""

import json
import hashlib
import subprocess
import sys
import os
import re
import time
import argparse

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ARTICLES_PATH = os.path.join(DATA_DIR, "articles.json")
CONCEPTS_PATH = os.path.join(DATA_DIR, "concepts.json")
CONCEPTS_BACKUP = os.path.join(DATA_DIR, "concepts_old.json")

BATCH_SIZE = 5  # articles per LLM call


def load_articles():
    with open(ARTICLES_PATH) as f:
        return json.load(f)


def build_extraction_prompt(batch: list[dict]) -> str:
    articles_block = []
    for a in batch:
        claims = a.get("key_claims", [])
        topics = a.get("topics", [])
        summary = a.get("full_summary", a.get("one_line_summary", ""))
        articles_block.append(
            f"ARTICLE {a['id']}\n"
            f"Title: {a['title']}\n"
            f"Topics: {', '.join(topics)}\n"
            f"Summary: {summary}\n"
            f"Claims:\n" + "\n".join(f"  - {c}" for c in claims)
        )

    return f"""You are extracting knowledge entities from articles for a personal reading app.

A knowledge entity is a specific person, place, event, historical period, theory, technique, concept, or topic that a reader would recognize and want to track across their reading. These are the building blocks of knowledge.

GOOD entities (short, recognizable, noun phrases):
- "Garibaldi"
- "Greek colonization of Sicily"
- "spaced repetition"
- "Norman conquest of Sicily"
- "Battle of Thermopylae"
- "Claude Code"
- "incremental reading"
- "FSRS algorithm"

BAD entities (too verbose — these are claims, not entities):
- "AGENTS.md files provide structured context to help AI coding agents navigate complex codebases"
- "Running 10-15 sessions simultaneously enables parallel development"

BAD entities (too generic):
- "software engineering"
- "history"
- "technology"

For each entity extract:
- name: Short recognizable name (1-6 words, noun phrase). This is how it appears in text.
- description: 1-2 sentence definition or context. What would a reader need to know?
- topic: One primary topic tag (lowercase, hyphenated)
- aliases: Other names/spellings this entity is known by (empty array if none)
- source_article_ids: Which articles from this batch discuss this entity

Deduplicate across articles in this batch. If two articles discuss the same entity, produce ONE entry with both article IDs.

Extract 5-12 entities per article. Focus on entities specific enough to be useful (not "programming" but "agentic coding patterns").

Articles:
---
{chr(10).join(articles_block)}
---

Return ONLY a valid JSON array:
[
  {{
    "name": "short entity name",
    "description": "1-2 sentence explanation",
    "topic": "primary-topic",
    "aliases": ["alt name 1"],
    "source_article_ids": ["article_id_1", "article_id_2"]
  }}
]"""


def build_relationship_prompt(concepts: list[dict]) -> str:
    concept_list = "\n".join(
        f"  {c['id']}: {c['name']} — {c['description'][:80]}"
        for c in concepts[:80]  # cap at 80 to fit context
    )
    return f"""Given these knowledge entities, identify relationships between them.
For each entity, list IDs of related entities (max 5 per entity).
Two entities are related if understanding one helps understand the other.

Entities:
{concept_list}

Return ONLY a valid JSON object mapping entity ID to array of related IDs:
{{
  "entity_id_1": ["related_id_a", "related_id_b"],
  "entity_id_2": ["related_id_c"]
}}

Only include entities that have at least one relationship."""


def call_claude_p(prompt: str) -> str | None:
    """Call claude -p (Max plan, free)."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        print(f"    claude -p returned code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"    stderr: {result.stderr[:200]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("    claude -p timed out", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("    claude CLI not found, falling back to API", file=sys.stderr)
        return None


def call_api(prompt: str) -> str | None:
    """Fallback: call Anthropic API directly."""
    api_key = os.environ.get("ANTHROPIC_KEY", "")
    if not api_key:
        # Try loading from .env
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("ANTHROPIC_KEY="):
                        api_key = line.strip().split("=", 1)[1]
    if not api_key:
        print("    No ANTHROPIC_KEY available", file=sys.stderr)
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip() if message.content else None
    except Exception as e:
        print(f"    API error: {e}", file=sys.stderr)
        return None


def call_llm(prompt: str) -> str | None:
    """Try claude -p first, fall back to API."""
    result = call_claude_p(prompt)
    if result:
        return result
    return call_api(prompt)


def parse_json_response(response: str) -> list | dict | None:
    """Parse JSON from LLM response, stripping markdown fences."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try finding JSON array/object in the response
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = cleaned.find(start_char)
            end = cleaned.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    continue
        return None


def deduplicate_concepts(concepts: list[dict]) -> list[dict]:
    """Deduplicate by name similarity (case-insensitive exact + alias matching)."""
    seen_names: dict[str, int] = {}  # lowercase name -> index in result
    result = []

    for c in concepts:
        name_lower = c["name"].lower().strip()

        # Check if we've seen this name or any of its aliases
        matched_idx = seen_names.get(name_lower)
        if matched_idx is None:
            for alias in c.get("aliases", []):
                matched_idx = seen_names.get(alias.lower().strip())
                if matched_idx is not None:
                    break

        if matched_idx is not None:
            # Merge: combine source_article_ids
            existing = result[matched_idx]
            for aid in c.get("source_article_ids", []):
                if aid not in existing["source_article_ids"]:
                    existing["source_article_ids"].append(aid)
            # Add aliases
            for alias in c.get("aliases", []):
                if alias not in existing.get("aliases", []):
                    existing.setdefault("aliases", []).append(alias)
        else:
            idx = len(result)
            result.append(c)
            seen_names[name_lower] = idx
            for alias in c.get("aliases", []):
                seen_names[alias.lower().strip()] = idx

    return result


def main():
    parser = argparse.ArgumentParser(description="Extract entity-style concepts")
    parser.add_argument("--test", type=int, help="Test with N articles only")
    parser.add_argument("--dry-run", action="store_true", help="Show prompts without calling LLM")
    parser.add_argument("--no-relationships", action="store_true", help="Skip relationship extraction")
    parser.add_argument("--incremental", action="store_true", help="Only process articles not already covered in concepts.json")
    args = parser.parse_args()

    articles = load_articles()
    print(f"Loaded {len(articles)} articles", file=sys.stderr)

    # Load existing concepts for incremental mode
    existing_concepts = []
    covered_article_ids = set()
    if args.incremental and os.path.exists(CONCEPTS_PATH):
        with open(CONCEPTS_PATH) as f:
            existing_concepts = json.load(f)
        # Only treat as valid entity concepts if they have 'name' field (not old sentence-style)
        if existing_concepts and isinstance(existing_concepts[0], dict) and existing_concepts[0].get("name"):
            for c in existing_concepts:
                for aid in c.get("source_article_ids", []):
                    covered_article_ids.add(aid)
            print(f"  Incremental mode: {len(existing_concepts)} existing concepts covering {len(covered_article_ids)} articles", file=sys.stderr)
        else:
            print(f"  Incremental mode: existing concepts are old-style, will extract all", file=sys.stderr)
            existing_concepts = []

    if args.test:
        articles = articles[: args.test]
        print(f"  (test mode: using {len(articles)} articles)", file=sys.stderr)

    # Filter to articles that have content
    articles = [a for a in articles if a.get("key_claims") or a.get("full_summary")]
    print(f"  {len(articles)} articles with content", file=sys.stderr)

    # In incremental mode, skip already-covered articles
    if args.incremental and covered_article_ids:
        articles = [a for a in articles if a["id"] not in covered_article_ids]
        print(f"  After filtering covered articles: {len(articles)} new articles to process", file=sys.stderr)
        if len(articles) == 0:
            print(f"  No new articles to process, keeping existing concepts.", file=sys.stderr)
            return

    # Backup old concepts
    if os.path.exists(CONCEPTS_PATH):
        import shutil
        shutil.copy2(CONCEPTS_PATH, CONCEPTS_BACKUP)
        print(f"  Backed up old concepts to {CONCEPTS_BACKUP}", file=sys.stderr)

    # Extract in batches
    all_concepts = []
    total_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"\n  [{batch_num}/{total_batches}] Extracting from: {', '.join(a['title'][:40] for a in batch)}", file=sys.stderr)

        prompt = build_extraction_prompt(batch)

        if args.dry_run:
            print(f"    Prompt length: {len(prompt)} chars", file=sys.stderr)
            print(f"    First 200 chars: {prompt[:200]}...", file=sys.stderr)
            continue

        response = call_llm(prompt)
        if not response:
            print("    LLM call failed, skipping batch", file=sys.stderr)
            continue

        parsed = parse_json_response(response)
        if not isinstance(parsed, list):
            print(f"    Unexpected response type: {type(parsed)}", file=sys.stderr)
            continue

        batch_concepts = []
        for item in parsed:
            name = item.get("name", "").strip()
            if not name:
                continue
            concept = {
                "id": hashlib.sha256(name.lower().encode()).hexdigest()[:10],
                "name": name,
                "description": item.get("description", ""),
                "topic": item.get("topic", ""),
                "source_article_ids": item.get("source_article_ids", []),
                "aliases": item.get("aliases", []),
            }
            batch_concepts.append(concept)

        all_concepts.extend(batch_concepts)
        print(f"    Extracted {len(batch_concepts)} entities", file=sys.stderr)

        # Brief pause between batches
        if batch_num < total_batches:
            time.sleep(1)

    if args.dry_run:
        print(f"\n  Dry run complete. Would process {total_batches} batches.", file=sys.stderr)
        return

    # Deduplicate across batches
    print(f"\n  Deduplicating {len(all_concepts)} raw concepts...", file=sys.stderr)
    all_concepts = deduplicate_concepts(all_concepts)
    print(f"  After dedup: {len(all_concepts)} concepts", file=sys.stderr)

    # In incremental mode, merge new concepts with existing ones
    if args.incremental and existing_concepts:
        print(f"  Merging {len(all_concepts)} new concepts with {len(existing_concepts)} existing...", file=sys.stderr)
        all_concepts = deduplicate_concepts(existing_concepts + all_concepts)
        print(f"  After merge: {len(all_concepts)} total concepts", file=sys.stderr)

    # Extract relationships
    if not args.no_relationships and len(all_concepts) > 5:
        print(f"\n  Extracting relationships...", file=sys.stderr)
        rel_prompt = build_relationship_prompt(all_concepts)
        rel_response = call_llm(rel_prompt)
        if rel_response:
            rel_data = parse_json_response(rel_response)
            if isinstance(rel_data, dict):
                # Build concept ID lookup
                id_set = {c["id"] for c in all_concepts}
                for c in all_concepts:
                    related = rel_data.get(c["id"], [])
                    # Filter to valid IDs
                    c["related_concepts"] = [r for r in related if r in id_set and r != c["id"]]
                related_count = sum(1 for c in all_concepts if c.get("related_concepts"))
                print(f"  Added relationships to {related_count} concepts", file=sys.stderr)
            else:
                print("  Relationship extraction returned unexpected format", file=sys.stderr)

    # Sort by topic then name
    all_concepts.sort(key=lambda c: (c.get("topic", ""), c.get("name", "")))

    # Save
    with open(CONCEPTS_PATH, "w") as f:
        json.dump(all_concepts, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved {len(all_concepts)} entity concepts to {CONCEPTS_PATH}", file=sys.stderr)

    # Update manifest hash
    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
        concepts_hash = hashlib.sha256(json.dumps(all_concepts).encode()).hexdigest()[:16]
        manifest["concepts_hash"] = concepts_hash
        manifest["concept_count"] = len(all_concepts)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"  Updated manifest (hash: {concepts_hash})", file=sys.stderr)

    # Print summary
    topics = {}
    for c in all_concepts:
        t = c.get("topic", "other")
        topics[t] = topics.get(t, 0) + 1
    print(f"\n  Topics breakdown:", file=sys.stderr)
    for t, count in sorted(topics.items(), key=lambda x: -x[1]):
        print(f"    {t}: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
