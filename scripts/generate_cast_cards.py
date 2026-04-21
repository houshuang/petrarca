#!/usr/bin/env python3
"""Generate cast of characters cards from entity-curriculum links.

Cast cards test knowledge of key figures within a single event or period.
"The Players in the Siege of Syracuse" — tests whether the user can name
the key people and their SPECIFIC roles in that context.

Uses Gemini Flash for role/significance generation.
Stores as card_type='cast' in structural_cards + structural_positions.
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from curriculum_db import get_connection

# ── Prompt ────────────────────────────────────────────────────────────────

CAST_CARD_PROMPT = """You are generating a "cast of characters" card for a knowledge retention system.

Given a historical event/period and its key figures, generate a card that tests
whether the learner can identify each person's SPECIFIC role in THIS context.

Event/Period: {node_title}
Domain: {domain_title}
Date range: {date_start} to {date_end}
Description: {node_description}

Persons linked to this event:
{persons_json}

Generate:
1. A card title that frames the event/period (e.g., "The Players in the Siege of Syracuse")
   - Must NOT give away any person's identity
   - Should evoke the historical moment
2. A 1-2 sentence event_context setting the scene
3. For each person, a position with:
   - role: their SPECIFIC role in THIS event (not general biography)
     BAD: "Roman general"
     GOOD: "Commander of the two-year siege who admired his opponent's genius"
   - question_text: a question to ask when this person is blanked
     Must NOT mention the person's name — frame by their role/actions
   - significance: 1 sentence on why this person matters for this event

RULES:
- Roles must be EVENT-SPECIFIC, not biographical
- Question text must be answerable with ONLY the person's name
- Include ALL persons provided (minimum 3)
- Order by significance to the event (most important first)

Return JSON:
{{
  "title": "card title",
  "event_context": "1-2 sentence scene-setting",
  "positions": [
    {{
      "entity_name": "person name (from input)",
      "entity_id": "entity_id (from input)",
      "role": "specific role in this event",
      "question_text": "question when blanked",
      "significance": "why this person matters here"
    }}
  ]
}}"""


def find_cast_candidates(conn) -> list[dict]:
    """Find curriculum nodes with ≥3 person-type entities linked AND book/voice evidence.

    A cast card tests the user's memory of who-played-what-role in content they read,
    not a taxonomy lesson. The per-node evidence gate matches the one in
    ``_mix_structural_cards`` so generation and rendering stay consistent.
    """
    rows = conn.execute('''
        SELECT cn.id as node_id, cn.title, cn.description,
               cn.date_start, cn.date_end, cn.domain_id,
               cd.title as domain_title
        FROM curriculum_nodes cn
        JOIN curriculum_domains cd ON cd.id = cn.domain_id
        WHERE cn.id IN (
            SELECT ecl.node_id
            FROM entity_curriculum_links ecl
            JOIN shared_entities se ON se.entity_id = ecl.entity_id
            WHERE se.entity_type = 'person'
            GROUP BY ecl.node_id, ecl.domain_id
            HAVING COUNT(DISTINCT se.entity_id) >= 3
        )
        AND EXISTS (
            SELECT 1 FROM knowledge_items ki
            WHERE ki.curriculum_node_id = cn.id
              AND ki.curriculum_domain = cn.domain_id
              AND (
                  ki.sources LIKE '%"book_id": "%'
                  OR ki.sources LIKE '%"source": "voice_capture%'
                  OR ki.sources LIKE '%"transcript_id":%'
              )
        )
        ORDER BY cn.domain_id, cn.date_start
    ''').fetchall()

    candidates = []
    for row in rows:
        row = dict(row)
        # Load linked persons
        persons = conn.execute('''
            SELECT se.entity_id, se.name, se.entity_type, se.wikidata_qid,
                   se.date_start, se.date_end,
                   ecl.lens_title, ecl.lens_emphasis
            FROM entity_curriculum_links ecl
            JOIN shared_entities se ON se.entity_id = ecl.entity_id
            WHERE ecl.node_id = ? AND ecl.domain_id = ?
            AND se.entity_type = 'person'
            ORDER BY se.date_start
        ''', (row['node_id'], row['domain_id'])).fetchall()
        row['persons'] = [dict(p) for p in persons]
        if len(row['persons']) >= 3:
            candidates.append(row)

    return candidates


def generate_cast_card(candidate: dict) -> dict | None:
    """Generate cast card data for a single node via Gemini Flash."""
    persons_for_prompt = []
    for p in candidate['persons']:
        persons_for_prompt.append({
            'entity_id': p['entity_id'],
            'name': p['name'],
            'dates': f"{p.get('date_start', '?')} – {p.get('date_end', '?')}",
            'lens_title': p.get('lens_title', ''),
            'lens_emphasis': p.get('lens_emphasis', ''),
        })

    prompt = CAST_CARD_PROMPT.format(
        node_title=candidate['title'],
        domain_title=candidate['domain_title'],
        date_start=candidate.get('date_start', '?'),
        date_end=candidate.get('date_end', '?'),
        node_description=candidate.get('description', '') or '',
        persons_json=json.dumps(persons_for_prompt, indent=2),
    )

    result = call_claude_json(prompt, timeout=180, model='sonnet')
    if not isinstance(result, dict):
        return None
    return result


def store_cast_card(candidate: dict, generation: dict, conn) -> str:
    """Store generated cast card and positions in the database."""
    card_id = f"cast_{candidate['node_id']}_{uuid.uuid4().hex[:8]}"
    now_ms = int(time.time() * 1000)

    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id, node_id,
         date_start, date_end, generation_source, due_at, created_at)
        VALUES (?, 'cast', ?, ?, ?, ?, ?, ?, 'auto', ?, datetime('now'))
    """, (
        card_id,
        generation.get('title', candidate['title']),
        generation.get('event_context', ''),
        candidate['domain_id'],
        candidate['node_id'],
        candidate.get('date_start'),
        candidate.get('date_end'),
        now_ms,
    ))

    positions = generation.get('positions', [])
    for i, pos in enumerate(positions):
        pos_id = f"{card_id}_pos{i}"
        # Store role + significance in question_variants for the component
        question_variants = json.dumps({
            'role': pos.get('role', ''),
            'significance': pos.get('significance', ''),
            'entity_id': pos.get('entity_id', ''),
        })
        conn.execute("""
            INSERT INTO structural_positions
            (id, card_id, position, fact_id, entity_id, question_text, answer_text,
             question_variants, hook_type, stability_days, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'RELATIONAL', 1.0, ?, datetime('now'))
        """, (
            pos_id,
            card_id,
            i,
            '',  # no fact_id for cast cards
            pos.get('entity_id', ''),
            pos.get('question_text', ''),
            pos.get('entity_name', ''),
            question_variants,
            now_ms,
        ))

    return card_id


def batch_generate(domain_ids: list[str] | None = None, dry_run: bool = False):
    """Generate cast cards for all eligible nodes."""
    conn = get_connection()

    candidates = find_cast_candidates(conn)
    if domain_ids:
        candidates = [c for c in candidates if c['domain_id'] in domain_ids]

    # Filter out nodes that already have cast cards
    existing = set(r['node_id'] for r in conn.execute(
        "SELECT node_id FROM structural_cards WHERE card_type = 'cast'"
    ).fetchall())
    candidates = [c for c in candidates if c['node_id'] not in existing]

    print(f"Found {len(candidates)} nodes eligible for cast cards")
    if domain_ids:
        print(f"  Filtered to domains: {domain_ids}")
    print(f"  Already have cast cards: {len(existing)}")

    total_cards = 0
    total_positions = 0
    errors = 0

    for candidate in candidates:
        n_persons = len(candidate['persons'])
        print(f"  [{candidate['domain_title']}] {candidate['title'][:50]} "
              f"({n_persons} persons)...", end='', flush=True)

        if dry_run:
            print(f" [DRY RUN]")
            total_cards += 1
            total_positions += n_persons
            continue

        generation = generate_cast_card(candidate)
        if generation:
            card_id = store_cast_card(candidate, generation, conn)
            n_pos = len(generation.get('positions', []))
            print(f" OK → {generation.get('title', '?')[:40]} ({n_pos} positions)")
            total_cards += 1
            total_positions += n_pos
        else:
            print(" FAILED")
            errors += 1

        time.sleep(0.5)  # rate limit

    if not dry_run:
        conn.commit()

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Cards generated: {total_cards}")
    print(f"  Total positions: {total_positions}")
    print(f"  Errors: {errors}")
    if not dry_run:
        print(f"  Committed to database")
    else:
        print(f"  [DRY RUN — nothing written]")

    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate cast of characters cards')
    parser.add_argument('--domains', nargs='*', help='Domain IDs to process (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Count candidates without generating')
    parser.add_argument('--node', type=str, help='Generate for a single node ID (for testing)')
    args = parser.parse_args()

    if args.node:
        conn = get_connection()
        candidates = find_cast_candidates(conn)
        match = [c for c in candidates if c['node_id'] == args.node]
        if not match:
            print(f"Node {args.node} not found or has <3 person entities")
        else:
            print(f"Testing: {match[0]['title']}")
            print(f"Persons: {[p['name'] for p in match[0]['persons']]}")
            result = generate_cast_card(match[0])
            if result:
                print(json.dumps(result, indent=2))
            else:
                print("Generation failed")
        conn.close()
    else:
        batch_generate(domain_ids=args.domains, dry_run=args.dry_run)
