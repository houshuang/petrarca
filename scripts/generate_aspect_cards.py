#!/usr/bin/env python3
"""Generate aspect cards from existing key_facts.

Each curriculum node with key_facts becomes an aspect card.
For each fact, we generate:
  1. A non-leaking card title (doesn't give away any aspect answers)
  2. Reverse cue variants per fact
  3. Hook type classification

Uses Gemini Flash for speed (this is batch generation, not user-facing).
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from curriculum_db import get_connection

# ── Prompt for title + reverse cue generation ────────────────────────────

CARD_GENERATION_PROMPT = """You are generating review cards for a knowledge retention system.

Given a curriculum node with its key_facts, generate:
1. A **non-leaking card title** — a title that describes the topic WITHOUT giving away any of the fact answers. The title should frame the topic by event, period, or theme — NOT by a specific person or date that is one of the quiz answers.
2. For each fact, **1-3 reverse cue variants** — alternative questions that test the SAME knowledge from a different angle.

RULES FOR TITLES:
- BAD: "Pompey's Pirate Campaign" (leaks "who led it?" → Pompey)
- GOOD: "The Mediterranean Pirate Crisis, 67 BC" or "Clearing the Pirates"
- BAD: "Gelon and the Battle of Himera" (leaks "who won?" → Gelon)
- GOOD: "The Battle of Himera, 480 BC" or "The Western Greeks vs Carthage"
- If the node title already doesn't leak, you can keep it or improve it
- Include dates when available (helps temporal anchoring)

RULES FOR REVERSE CUES:
- Each reverse cue must test the SAME fact from a DIFFERENT direction
- For date facts: "What happened in [year]?" or "When did [entity] [action]?"
- For event facts: "What role did [person] play?" or "What happened at [place]?"
- For person facts: "What is [person] known for in this context?"
- For connection facts: "What parallels [the referenced event]?"
- For significance facts: "What demonstrated that [consequence]?"
- Reverse cues should be self-contained questions (not "What about X?")
- Each reverse cue should have a clear, unambiguous answer

Input:
  Node title: {node_title}
  Domain: {domain_title}
  Date range: {date_start} to {date_end}
  Key facts:
{facts_json}

Return JSON:
{{
  "card_title": "non-leaking title for the card",
  "positions": [
    {{
      "fact_id": "the fact's id",
      "reverse_cues": [
        "reverse question variant 1",
        "reverse question variant 2"
      ]
    }}
  ]
}}"""


def generate_card_for_node(node: dict, domain_title: str) -> dict | None:
    """Generate aspect card data for a single node."""
    key_facts = json.loads(node['key_facts']) if node['key_facts'] else []
    if len(key_facts) < 2:
        return None  # need at least 2 aspects for a card

    # Format facts for the prompt
    facts_for_prompt = []
    for f in key_facts:
        facts_for_prompt.append({
            'id': f.get('id', ''),
            'type': f.get('type', 'unknown'),
            'question': f.get('question', ''),
            'answer': f.get('answer', ''),
            'entities': f.get('entities', []),
        })

    prompt = CARD_GENERATION_PROMPT.format(
        node_title=node['title'],
        domain_title=domain_title,
        date_start=node.get('date_start', '?'),
        date_end=node.get('date_end', '?'),
        facts_json=json.dumps(facts_for_prompt, indent=2),
    )

    parsed = call_claude_json(prompt, timeout=180, model='sonnet')

    if not parsed:
        print(f"  ERROR: No response for {node['title']}")
        return None
    if not isinstance(parsed, dict):
        print(f"  ERROR: Unexpected shape for {node['title']}")
        return None

    return parsed


def store_aspect_card(node: dict, generation: dict, domain_id: str, conn) -> str:
    """Store generated aspect card and positions in the database."""
    key_facts = json.loads(node['key_facts']) if node['key_facts'] else []
    fact_by_id = {f.get('id', ''): f for f in key_facts}

    card_id = f"aspect_{node['id']}_{uuid.uuid4().hex[:8]}"
    now_ms = int(time.time() * 1000)

    # Insert card
    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id, node_id,
         date_start, date_end, generation_source, due_at, created_at)
        VALUES (?, 'aspect', ?, ?, ?, ?, ?, ?, 'auto', ?, datetime('now'))
    """, (
        card_id,
        generation.get('card_title', node['title']),
        node.get('description', ''),
        domain_id,
        node['id'],
        node.get('date_start'),
        node.get('date_end'),
        now_ms,  # due immediately
    ))

    # Insert positions
    positions = generation.get('positions', [])
    for i, pos in enumerate(positions):
        fact_id = pos.get('fact_id', '')
        fact = fact_by_id.get(fact_id, {})
        reverse_cues = pos.get('reverse_cues', [])

        # Determine hook type from fact type
        hook_type_map = {
            'date': 'TEMPORAL',
            'event': 'IDENTITY',
            'person': 'RELATIONAL',
            'connection': 'PARALLEL',
            'significance': 'STRUCTURAL',
        }
        hook_type = hook_type_map.get(fact.get('type', ''), 'IDENTITY')

        pos_id = f"{card_id}_pos{i}"
        conn.execute("""
            INSERT INTO structural_positions
            (id, card_id, position, fact_id, question_text, answer_text,
             question_variants, hook_type, stability_days, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, datetime('now'))
        """, (
            pos_id,
            card_id,
            i,
            fact_id,
            fact.get('question', ''),
            fact.get('answer', ''),
            json.dumps(reverse_cues),
            hook_type,
            now_ms,
        ))

    return card_id


def batch_generate(domain_ids: list[str] | None = None, dry_run: bool = False):
    """Generate aspect cards for all nodes in the specified domains."""
    conn = get_connection()

    # Get domains
    if domain_ids:
        ph = ','.join(['?' for _ in domain_ids])
        domains = conn.execute(
            f"SELECT id, title FROM curriculum_domains WHERE id IN ({ph})",
            domain_ids
        ).fetchall()
    else:
        domains = conn.execute(
            "SELECT id, title FROM curriculum_domains"
        ).fetchall()

    total_cards = 0
    total_positions = 0
    errors = 0

    for domain in domains:
        domain_id = domain['id']
        domain_title = domain['title']
        print(f"\n{'='*60}")
        print(f"Domain: {domain_title}")
        print(f"{'='*60}")

        # Get nodes with key_facts AND real evidence (≥1 book/voice-backed KI on this node).
        # Generating aspect cards for nodes the user has never engaged with produces "teach me
        # something new from the taxonomy" cards — structural cards exist to test content the
        # user has actually read or talked through, not to introduce unstudied curriculum nodes.
        nodes = conn.execute("""
            SELECT cn.id, cn.title, cn.key_facts, cn.date_start, cn.date_end,
                   cn.description
            FROM curriculum_nodes cn
            WHERE cn.domain_id = ?
            AND cn.key_facts IS NOT NULL
            AND cn.key_facts != '[]'
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
            ORDER BY cn.date_start
        """, (domain_id,)).fetchall()

        # Check which nodes already have aspect cards
        existing = set(r['node_id'] for r in conn.execute(
            "SELECT node_id FROM structural_cards WHERE domain_id = ? AND card_type = 'aspect'",
            (domain_id,)
        ).fetchall())

        for node in nodes:
            node = dict(node)
            if node['id'] in existing:
                print(f"  SKIP (exists): {node['title'][:50]}")
                continue

            key_facts = json.loads(node['key_facts']) if node['key_facts'] else []
            if len(key_facts) < 2:
                print(f"  SKIP (<2 facts): {node['title'][:50]}")
                continue

            print(f"  Generating: {node['title'][:50]} ({len(key_facts)} facts)...", end='', flush=True)

            if dry_run:
                print(" [DRY RUN]")
                total_cards += 1
                total_positions += len(key_facts)
                continue

            generation = generate_card_for_node(node, domain_title)
            if generation:
                card_id = store_aspect_card(node, generation, domain_id, conn)
                n_pos = len(generation.get('positions', []))
                print(f" OK → {generation.get('card_title', '?')[:40]} ({n_pos} positions)")
                total_cards += 1
                total_positions += n_pos
            else:
                print(" FAILED")
                errors += 1

            # Rate limit — Gemini Flash is fast but has QPM limits
            time.sleep(0.5)

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
    parser = argparse.ArgumentParser(description='Generate aspect cards from key_facts')
    parser.add_argument('--domains', nargs='*', help='Domain IDs to process (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Count cards without generating')
    parser.add_argument('--node', type=str, help='Generate for a single node ID (for testing)')
    args = parser.parse_args()

    if args.node:
        # Single node test mode
        conn = get_connection()
        node = dict(conn.execute(
            "SELECT * FROM curriculum_nodes WHERE id = ?", (args.node,)
        ).fetchone())
        domain = dict(conn.execute(
            "SELECT * FROM curriculum_domains WHERE id = ?", (node['domain_id'],)
        ).fetchone())
        print(f"Testing node: {node['title']}")
        print(f"Domain: {domain['title']}")
        result = generate_card_for_node(node, domain['title'])
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Generation failed")
        conn.close()
    else:
        batch_generate(domain_ids=args.domains, dry_run=args.dry_run)
