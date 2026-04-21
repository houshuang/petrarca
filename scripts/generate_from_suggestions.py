#!/usr/bin/env python3
"""Generate structural cards from approved suggestions in the suggested_cards table.

Reads pending/approved suggestions, calls Gemini Flash to produce milestones/positions,
and writes to structural_cards + structural_positions tables.

Usage:
  python3 scripts/generate_from_suggestions.py                    # process all approved
  python3 scripts/generate_from_suggestions.py --id sc_sequence_xxx  # process one
  python3 scripts/generate_from_suggestions.py --dry-run          # preview without writing

Run on server: cd /opt/petrarca && python3 scripts/generate_from_suggestions.py
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from db import get_connection, init_db

# ── Prompts ─────────────────────────────────────────────────────────────

SEQUENCE_FROM_ENTITIES_PROMPT = """You are generating a chronological sequence card for a knowledge retention system.

Given a set of historical entities (persons/events) with dates, produce a sequence card with 5-8 milestones ordered chronologically.

Each milestone must have:
- A question_text that tests recall WITHOUT revealing the answer (frame by context/position in sequence)
- An answer_text that reveals the key fact
- A year (integer, negative for BC)
- A year_display (string, e.g. "264 BC")
- A hook connecting this milestone to the previous one or to known events

RULES:
- question_text must NOT leak the answer. Ask "Who ruled after X?" not "When did Y rule?"
- Milestones should be a mix of persons AND events, not just ruler succession
- Include at least one milestone that connects to another domain if possible
- Hooks should reference the user's likely prior knowledge (classical/medieval history focus)

Entities:
{entities_json}

Domain: {domain_id}
Rationale: {rationale}

Return JSON:
{{
  "title": "sequence card title (concise, narrative arc)",
  "description": "1-2 sentence description of what this sequence covers",
  "date_start": -264,
  "date_end": -146,
  "milestones": [
    {{
      "position": 0,
      "year": -264,
      "year_display": "264 BC",
      "question_text": "What triggered this period?",
      "answer_text": "Rome intervened in Messana...",
      "entity_id": "matching_entity_id_if_exists",
      "hook": "Same decade as Ashoka's edicts in India"
    }}
  ]
}}"""

SYNCHRONIC_FROM_ENTITIES_PROMPT = """You are generating a synchronic (contemporaries) card for a knowledge retention system.

Given a set of historical persons from DIFFERENT domains who lived at the same time, produce a synchronic card that tests knowledge of cross-domain connections.

Each position represents one person and tests: "Who was active in [domain] around [year]?"

RULES:
- anchor_year should be the approximate midpoint of when all these persons overlapped
- Each position needs a question_text (by domain/role, not by name) and answer_text (name + key contribution)
- Include a connection note for each person explaining why their contemporaneity matters
- Focus on surprising or illuminating cross-domain connections

Entities:
{entities_json}

Domains: {domain_ids}
Rationale: {rationale}

Return JSON:
{{
  "title": "synchronic card title (reference the anchor year/period)",
  "description": "1-2 sentence description of what connects these figures",
  "date_anchor": 1150,
  "positions": [
    {{
      "position": 0,
      "question_text": "Who was the leading figure in [domain] at this time?",
      "answer_text": "Name — key contribution",
      "domain_id": "domain for this person",
      "label": "Short role label (e.g. 'Norman King')",
      "connection": "Why this person's contemporaneity with others matters"
    }}
  ]
}}"""


def _check_entity_overlap(suggestion: dict, conn) -> list[str]:
    """Check if suggestion entities overlap with existing structural card positions."""
    entity_names = {e['name'].lower() for e in suggestion.get('entities', [])}
    card_type = suggestion['card_type']

    overlaps = []
    rows = conn.execute('''
        SELECT sc.id, sc.title, sp.answer_text
        FROM structural_cards sc
        JOIN structural_positions sp ON sp.card_id = sc.id
        WHERE sc.card_type = ?
    ''', (card_type,)).fetchall()

    for r in rows:
        answer_lower = (r['answer_text'] or '').lower()
        matching = [n for n in entity_names if n in answer_lower]
        if len(matching) >= 2:
            overlaps.append(f"{r['title']} (card {r['id'][:20]}...)")

    return overlaps


def generate_from_suggestion(suggestion: dict, conn, dry_run: bool = False) -> str | None:
    """Generate a structural card from a suggestion. Returns card_id or None."""
    card_type = suggestion['card_type']
    entities = suggestion.get('entities', [])
    domain_ids = suggestion.get('domain_ids', [])
    rationale = suggestion.get('rationale', '')

    if not entities or len(entities) < 2:
        print(f"  SKIP: not enough entities ({len(entities)})")
        return None

    # Check for overlap with existing cards
    overlaps = _check_entity_overlap(suggestion, conn)
    if overlaps:
        print(f"  WARNING: Entity overlap with existing cards:")
        for o in overlaps:
            print(f"    - {o}")
        if not dry_run:
            print(f"  Proceeding anyway (overlap may be acceptable)")

    domain_id = domain_ids[0] if domain_ids else 'unknown'
    entities_json = json.dumps(entities, indent=2)

    if card_type == 'sequence':
        prompt = SEQUENCE_FROM_ENTITIES_PROMPT.format(
            entities_json=entities_json,
            domain_id=domain_id,
            rationale=rationale,
        )
    elif card_type == 'synchronic':
        prompt = SYNCHRONIC_FROM_ENTITIES_PROMPT.format(
            entities_json=entities_json,
            domain_ids=json.dumps(domain_ids),
            rationale=rationale,
        )
    else:
        print(f"  SKIP: unsupported card type '{card_type}'")
        return None

    print(f"  Calling Claude Sonnet for {card_type} card...")
    parsed = call_claude_json(prompt, timeout=240, model='sonnet')
    if not parsed:
        print("  ERROR: LLM returned empty result")
        return None
    if not isinstance(parsed, dict):
        print("  ERROR: Unexpected shape from LLM")
        return None

    if dry_run:
        print(f"  [DRY RUN] Would generate: {parsed.get('title', '?')}")
        milestones = parsed.get('milestones', parsed.get('positions', []))
        print(f"  {len(milestones)} positions/milestones")
        for m in milestones:
            print(f"    [{m.get('position', '?')}] {m.get('question_text', '?')[:60]}")
        return None

    now_ms = int(time.time() * 1000)

    if card_type == 'sequence':
        return _store_sequence(parsed, domain_id, suggestion['id'], conn, now_ms)
    elif card_type == 'synchronic':
        return _store_synchronic(parsed, domain_ids, suggestion['id'], conn, now_ms)
    return None


def _store_sequence(parsed: dict, domain_id: str, suggestion_id: str, conn, now_ms: int) -> str:
    """Store a sequence card from LLM output."""
    card_id = f"seq_{domain_id[:20]}_{uuid.uuid4().hex[:8]}"
    milestones = parsed.get('milestones', [])
    hooks_json = json.dumps([m.get('hook', '') for m in milestones if m.get('hook')])

    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id,
         date_start, date_end, hooks, generation_source, due_at, created_at)
        VALUES (?, 'sequence', ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        card_id,
        parsed.get('title', ''),
        parsed.get('description', ''),
        domain_id,
        parsed.get('date_start'),
        parsed.get('date_end'),
        hooks_json,
        f'suggestion:{suggestion_id}',
        now_ms,
    ))

    for i, m in enumerate(milestones):
        pos_id = f"{card_id}_pos{i}"
        conn.execute("""
            INSERT INTO structural_positions
            (id, card_id, position, fact_id, entity_id,
             question_text, answer_text, question_variants,
             hook_type, mnemonic, stability_days, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'TEMPORAL', ?, 1.0, ?, datetime('now'))
        """, (
            pos_id, card_id, i,
            m.get('fact_id', ''),
            m.get('entity_id', ''),
            m.get('question_text', ''),
            m.get('answer_text', ''),
            json.dumps({'year': m.get('year'), 'year_display': m.get('year_display', '')}),
            m.get('hook', ''),
            now_ms,
        ))

    print(f"  Created sequence card: {card_id} ({parsed.get('title', '')})")
    print(f"  {len(milestones)} milestones")
    return card_id


def _store_synchronic(parsed: dict, domain_ids: list, suggestion_id: str, conn, now_ms: int) -> str:
    """Store a synchronic card from LLM output."""
    card_id = f"sync_{uuid.uuid4().hex[:8]}"
    positions = parsed.get('positions', [])
    primary_domain = domain_ids[0] if domain_ids else 'unknown'

    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id,
         date_anchor, hooks, generation_source, due_at, created_at)
        VALUES (?, 'synchronic', ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        card_id,
        parsed.get('title', ''),
        parsed.get('description', ''),
        primary_domain,
        parsed.get('date_anchor'),
        json.dumps({'domain_ids': domain_ids}),
        f'suggestion:{suggestion_id}',
        now_ms,
    ))

    for i, p in enumerate(positions):
        pos_id = f"{card_id}_pos{i}"
        conn.execute("""
            INSERT INTO structural_positions
            (id, card_id, position, question_text, answer_text,
             question_variants, hook_type, stability_days, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'IDENTITY', 1.0, ?, datetime('now'))
        """, (
            pos_id, card_id, i,
            p.get('question_text', ''),
            p.get('answer_text', ''),
            json.dumps({
                'domain_id': p.get('domain_id', ''),
                'label': p.get('label', ''),
                'connection': p.get('connection', ''),
            }),
            now_ms,
        ))

    print(f"  Created synchronic card: {card_id} ({parsed.get('title', '')})")
    print(f"  {len(positions)} positions")
    return card_id


def main():
    parser = argparse.ArgumentParser(description='Generate structural cards from suggestions')
    parser.add_argument('--id', help='Process a specific suggestion by ID')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--status', default='approved',
                        help='Process suggestions with this status (default: approved)')
    args = parser.parse_args()

    init_db()
    conn = get_connection()

    if args.id:
        row = conn.execute('SELECT * FROM suggested_cards WHERE id = ?', (args.id,)).fetchone()
        if not row:
            print(f"ERROR: suggestion {args.id} not found")
            sys.exit(1)
        suggestions = [dict(row)]
    else:
        suggestions = [dict(r) for r in conn.execute(
            'SELECT * FROM suggested_cards WHERE status = ? ORDER BY created_at',
            (args.status,)
        ).fetchall()]

    if not suggestions:
        print(f"No suggestions with status='{args.status}' found.")
        print(f"  Use POST /admin/suggested-cards/approve to approve pending suggestions first.")
        return

    print(f"Processing {len(suggestions)} suggestion(s)...")

    for s in suggestions:
        # Parse JSON fields
        s['entities'] = json.loads(s['entities']) if isinstance(s['entities'], str) else s['entities']
        s['domain_ids'] = json.loads(s['domain_ids']) if isinstance(s['domain_ids'], str) else s['domain_ids']

        print(f"\n{'='*60}")
        print(f"[{s['card_type']}] {s['id']}")
        names = ', '.join(e['name'] for e in s['entities'][:5])
        print(f"  Entities: {names}")
        print(f"  Rationale: {s.get('rationale', '')[:80]}")

        card_id = generate_from_suggestion(s, conn, dry_run=args.dry_run)

        if card_id and not args.dry_run:
            conn.execute(
                "UPDATE suggested_cards SET status = 'generated' WHERE id = ?",
                (s['id'],)
            )
            conn.commit()
            print(f"  Status updated to 'generated'")

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(f"\nDone.")


if __name__ == '__main__':
    main()
