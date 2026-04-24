#!/usr/bin/env python3
"""
Extract key_facts from curriculum node descriptions.

Processes a curriculum in batches (by level-1 area), using Claude Opus
to extract structured, testable facts per node. Each fact has a type,
priority, question/answer, and entity references.

Usage:
    # Extract one area (proof of concept)
    python extract_key_facts.py --curriculum sicily_history_culture_and_legacy --area 0

    # Extract all areas for a curriculum
    python extract_key_facts.py --curriculum sicily_history_culture_and_legacy

    # Dry run (show prompt, don't call LLM)
    python extract_key_facts.py --curriculum sicily_history_culture_and_legacy --area 0 --dry-run

    # Load results into SQLite
    python extract_key_facts.py --load results/sicily_key_facts.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / 'data' / 'curricula'
RESULTS_DIR = Path(__file__).parent / 'key_facts_results'

EXTRACTION_PROMPT = """You are extracting structured, testable facts from curriculum node descriptions.

## Context

Curriculum: {curriculum_title}
Area: {area_title}

These nodes form a coherent section of a history curriculum. For each node,
extract the 3-6 most important testable facts — the load-bearing knowledge
that makes everything else about this topic click into place.

## Entity reference list

Use these EXACT entity_ids when tagging facts. Only use IDs from this list:

{entity_list}

If a fact involves an entity NOT in this list, use the entity name as a
provisional ID (lowercase, underscored, e.g. "battle_of_salamis").

## Nodes to process

{nodes_json}

## Output schema

For each node, produce a JSON object with the node_id and key_facts array:

```json
[
  {{
    "node_id": "the_node_id",
    "key_facts": [
      {{
        "id": "short_snake_case_id",
        "type": "date|person|event|connection|significance",
        "priority": 1,
        "question": "Short question (6-15 words)",
        "answer": "Specific factual answer (1-2 sentences max)",
        "rich_answer": "4-5 vivid sentences placing this fact in context. Include temporal anchors to other periods. Only for priority 2-3 facts.",
        "entities": ["entity_id_1", "entity_id_2"]
      }}
    ]
  }}
]
```

## Rules

1. **Priority 1** (2-3 per node): The load-bearing facts. Dates, key figures, key events.
   What happened? When? Who? These are always testable as simple recall.
   Short answer only — no rich_answer needed.

2. **Priority 2** (1-2 per node): Connections to other nodes or curricula.
   "This happened simultaneously with X." "This person also appears in Y."
   Include rich_answer for teaching moment.

3. **Priority 3** (0-1 per node): Significance — why this matters for what came after.
   Include rich_answer explaining the long-term consequence.

4. **Fact types**:
   - `date`: When did X happen? What century/year?
   - `person`: Who was X? What was their role?
   - `event`: What happened? What was the outcome?
   - `connection`: What was happening elsewhere? What came before/after?
   - `significance`: Why did this matter? What changed because of it?

5. **Entity tagging**: Every fact MUST have an `entities` array with at least one entity_id.
   Use IDs from the entity list. Cross-node connections should reference entities
   from other nodes in this batch.

6. **Fact IDs**: Use short, descriptive snake_case IDs within each node.
   E.g., "himera_date", "gelon_role", "himera_salamis_connection".

7. **Answers must be SHORT and SPECIFIC**. A date, a name, a 1-sentence event.
   Never "X was characterized by..." — always concrete facts.

8. **Connection facts can reference other curricula**. If a fact connects to Greek,
   Roman, or Islamic history, note it. The entity system handles cross-curriculum links.

9. For Level 1 (area overview) nodes: extract 2-3 framing facts only.
   The detail lives in the child nodes.

Output ONLY the JSON array. No markdown, no commentary.
"""


def load_curriculum(curriculum_id: str) -> dict:
    """Load curriculum JSON from data/curricula/."""
    path = DATA_DIR / f'{curriculum_id}.json'
    if not path.exists():
        print(f'Curriculum not found: {path}', file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def load_entities(curriculum_id: str) -> list[dict]:
    """Load entities for a curriculum. Tries local cache, then server."""
    # Check local cache
    cache = Path('/tmp') / f'{curriculum_id}_entities.json'
    if cache.exists():
        return json.loads(cache.read_text())

    # Try fetching from server
    print(f'No local entity cache at {cache}. Run the SSH command to fetch entities.',
          file=sys.stderr)
    print(f'Or create an empty file: echo "[]" > {cache}', file=sys.stderr)
    return []


def group_nodes_by_area(curriculum: dict) -> list[dict]:
    """Group nodes into batches by level-1 area."""
    nodes = curriculum['nodes']
    areas = []

    for node in nodes:
        if node.get('level') == 1:
            # Collect all descendants
            area_id = node['id']
            children = []
            for n in nodes:
                if n.get('parent_id') == area_id:
                    children.append(n)
                    # Also get grandchildren
                    for gc in nodes:
                        if gc.get('parent_id') == n['id']:
                            children.append(gc)
            areas.append({
                'area_node': node,
                'children': children,
                'all_nodes': [node] + children,
            })

    return areas


def format_entity_list(entities: list[dict], area_node_ids: set) -> str:
    """Format entity list for the prompt, filtering to relevant entities."""
    relevant = []
    for e in entities:
        # Include entity if any of its node_ids are in this area
        if any(nid in area_node_ids for nid in e.get('node_ids', [])):
            relevant.append(e)

    if not relevant:
        return "(No pre-defined entities for this area. Use descriptive provisional IDs.)"

    lines = []
    for e in sorted(relevant, key=lambda x: x['name']):
        dates = ''
        if e.get('date_start') is not None:
            ds = e['date_start']
            de = e.get('date_end')
            if ds < 0:
                dates = f' ({abs(ds)} BC'
            else:
                dates = f' ({ds}'
            if de is not None:
                dates += f'–{abs(de)} {"BC" if de < 0 else "AD"}'
            dates += ')'
        lines.append(f'- {e["entity_id"]}: {e["name"]} [{e.get("entity_type", "?")}]{dates}')

    return '\n'.join(lines)


def format_nodes_for_prompt(nodes: list[dict]) -> str:
    """Format nodes as JSON for the prompt."""
    simplified = []
    for n in nodes:
        entry = {
            'node_id': n['id'],
            'title': n['title'],
            'level': n.get('level', 1),
            'description': n.get('description', ''),
            'date_start': n.get('date_start'),
            'date_end': n.get('date_end'),
            'prerequisites': n.get('prerequisites', []),
        }
        simplified.append(entry)
    return json.dumps(simplified, indent=2)


def build_prompt(curriculum: dict, area: dict, entities: list[dict]) -> str:
    """Build the full extraction prompt for one area."""
    area_node_ids = {n['id'] for n in area['all_nodes']}

    return EXTRACTION_PROMPT.format(
        curriculum_title=curriculum.get('title', curriculum.get('name', 'Unknown')),
        area_title=area['area_node']['title'],
        entity_list=format_entity_list(entities, area_node_ids),
        nodes_json=format_nodes_for_prompt(area['all_nodes']),
    )


def call_claude(prompt: str, timeout: int = 600) -> str | None:
    """Call Claude via claude -p for Opus quality."""
    # Strip CLAUDECODE + ANTHROPIC_* so the CLI uses Max/OAuth auth (not API-key
    # billing) — matches the pattern in research-server.py + curriculum.py.
    _strip = ('CLAUDECODE', 'ANTHROPIC_API_KEY', 'ANTHROPIC_KEY', 'ANTHROPIC_AUTH_TOKEN')
    cli_env = {k: v for k, v in os.environ.items() if k not in _strip}
    try:
        result = subprocess.run(
            ['claude', '-p', '--output-format', 'text', prompt],
            capture_output=True, text=True, timeout=timeout, env=cli_env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if result.stderr:
            print(f'Claude stderr: {result.stderr[:200]}', file=sys.stderr)
    except subprocess.TimeoutExpired:
        print('Claude timed out', file=sys.stderr)
    except FileNotFoundError:
        print('claude CLI not found', file=sys.stderr)
    return None


def parse_response(text: str) -> list[dict] | None:
    """Parse LLM JSON response, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)

    # Find the JSON array
    match = re.search(r'\[[\s\S]*\]', cleaned)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            print(f'JSON parse error: {e}', file=sys.stderr)
            # Try to fix common issues
            try:
                # Sometimes trailing commas
                fixed = re.sub(r',\s*([}\]])', r'\1', match.group())
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
    return None


def validate_facts(results: list[dict], area_nodes: list[dict]) -> list[str]:
    """Validate extracted facts. Returns list of warnings."""
    warnings = []
    node_ids = {n['id'] for n in area_nodes}

    for entry in results:
        nid = entry.get('node_id', '?')
        if nid not in node_ids:
            warnings.append(f'Unknown node_id: {nid}')
            continue

        facts = entry.get('key_facts', [])
        if len(facts) < 2:
            warnings.append(f'{nid}: only {len(facts)} facts (expected 3-6)')
        if len(facts) > 8:
            warnings.append(f'{nid}: {len(facts)} facts (expected 3-6, seems too many)')

        fact_ids = set()
        for f in facts:
            fid = f.get('id', '?')
            if fid in fact_ids:
                warnings.append(f'{nid}: duplicate fact id "{fid}"')
            fact_ids.add(fid)

            if not f.get('entities'):
                warnings.append(f'{nid}/{fid}: no entities tagged')
            if f.get('priority') not in (1, 2, 3):
                warnings.append(f'{nid}/{fid}: invalid priority {f.get("priority")}')
            if f.get('type') not in ('date', 'person', 'event', 'connection', 'significance'):
                warnings.append(f'{nid}/{fid}: invalid type "{f.get("type")}"')
            if f.get('priority', 1) >= 2 and not f.get('rich_answer'):
                warnings.append(f'{nid}/{fid}: priority {f["priority"]} missing rich_answer')

    # Check for missing nodes
    covered = {e['node_id'] for e in results}
    for nid in node_ids:
        if nid not in covered:
            warnings.append(f'Missing node: {nid} (no facts extracted)')

    return warnings


def load_into_db(results_path: str):
    """Load key_facts from a results JSON file into SQLite."""
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_connection

    results = json.loads(Path(results_path).read_text())
    conn = get_connection()

    updated = 0
    for entry in results:
        node_id = entry['node_id']
        domain_id = entry.get('domain_id', '')
        key_facts = json.dumps(entry['key_facts'])

        # Try to find the domain_id if not provided
        if not domain_id:
            row = conn.execute(
                'SELECT domain_id FROM curriculum_nodes WHERE id = ?', (node_id,)
            ).fetchone()
            if row:
                domain_id = row['domain_id']
            else:
                print(f'Warning: node {node_id} not found in DB, skipping', file=sys.stderr)
                continue

        conn.execute(
            'UPDATE curriculum_nodes SET key_facts = ? WHERE domain_id = ? AND id = ?',
            (key_facts, domain_id, node_id)
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f'Updated {updated} nodes with key_facts')


def main():
    parser = argparse.ArgumentParser(description='Extract key_facts from curriculum nodes')
    parser.add_argument('--curriculum', '-c', help='Curriculum ID')
    parser.add_argument('--area', '-a', type=int, help='Area index (0-based). Omit for all.')
    parser.add_argument('--dry-run', action='store_true', help='Show prompt without calling LLM')
    parser.add_argument('--load', help='Load results JSON into SQLite')
    parser.add_argument('--entities', help='Path to entities JSON file')
    args = parser.parse_args()

    if args.load:
        load_into_db(args.load)
        return

    if not args.curriculum:
        parser.error('--curriculum is required (or --load to import results)')

    curriculum = load_curriculum(args.curriculum)
    areas = group_nodes_by_area(curriculum)

    print(f'Curriculum: {curriculum.get("title", args.curriculum)}')
    print(f'Areas: {len(areas)}')
    for i, a in enumerate(areas):
        print(f'  [{i}] {a["area_node"]["title"]} ({len(a["all_nodes"])} nodes)')
    print()

    # Load entities
    if args.entities:
        entities = json.loads(Path(args.entities).read_text())
    else:
        entities = load_entities(args.curriculum)

    # Determine which areas to process
    if args.area is not None:
        if args.area >= len(areas):
            print(f'Area index {args.area} out of range (0-{len(areas)-1})', file=sys.stderr)
            sys.exit(1)
        target_areas = [(args.area, areas[args.area])]
    else:
        target_areas = list(enumerate(areas))

    # Process each area
    RESULTS_DIR.mkdir(exist_ok=True)
    all_results = []

    for idx, area in target_areas:
        area_name = area['area_node']['title']
        print(f'\n{"="*60}')
        print(f'Processing area [{idx}]: {area_name} ({len(area["all_nodes"])} nodes)')
        print(f'{"="*60}')

        prompt = build_prompt(curriculum, area, entities)

        if args.dry_run:
            print(f'\n--- PROMPT ({len(prompt)} chars) ---')
            print(prompt)
            print(f'--- END PROMPT ---\n')
            continue

        print(f'Calling Claude ({len(prompt)} chars)...')
        raw = call_claude(prompt)
        if not raw:
            print(f'ERROR: No response for area {idx}', file=sys.stderr)
            continue

        # Save raw response
        raw_path = RESULTS_DIR / f'{args.curriculum}_area{idx}_raw.txt'
        raw_path.write_text(raw)
        print(f'Raw response saved to {raw_path}')

        # Parse
        results = parse_response(raw)
        if not results:
            print(f'ERROR: Could not parse response for area {idx}', file=sys.stderr)
            continue

        # Validate
        warnings = validate_facts(results, area['all_nodes'])
        if warnings:
            print(f'\nWarnings ({len(warnings)}):')
            for w in warnings:
                print(f'  ⚠ {w}')

        # Add domain_id to each entry
        for entry in results:
            entry['domain_id'] = args.curriculum

        all_results.extend(results)

        # Stats
        total_facts = sum(len(e.get('key_facts', [])) for e in results)
        total_entities = sum(
            len(f.get('entities', []))
            for e in results for f in e.get('key_facts', [])
        )
        print(f'\nExtracted: {len(results)} nodes, {total_facts} facts, {total_entities} entity refs')

        # Print summary
        for entry in results:
            nid = entry['node_id']
            facts = entry.get('key_facts', [])
            print(f'\n  {nid} ({len(facts)} facts):')
            for f in facts:
                ents = ', '.join(f.get('entities', []))
                print(f'    P{f.get("priority",0)} [{f.get("type","?")}] {f.get("question","?")}')
                print(f'       → {f.get("answer","?")}')
                print(f'       entities: [{ents}]')

    if all_results and not args.dry_run:
        # Save combined results
        out_path = RESULTS_DIR / f'{args.curriculum}_key_facts.json'
        out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
        print(f'\n✓ Results saved to {out_path}')
        print(f'  To load into DB: python {__file__} --load {out_path}')


if __name__ == '__main__':
    main()
