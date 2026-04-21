#!/usr/bin/env python3
"""Generate type-specific mnemonics for aspect card positions.

Each position's hook_type determines the mnemonic strategy:
  TEMPORAL   → Anchor to known events: "Same year as X, 50 years after Y"
  RELATIONAL → Role + connection: "X's general who later became Y"
  STRUCTURAL → Cause-effect chain: "Because X happened, Y led to Z"
  PARALLEL   → Contrast pair: "Unlike X who did A, Y did B"
  IDENTITY   → Key identity: "The one who..., known for..."

Processes one card at a time (all positions in one LLM call for context).
Uses Gemini Flash for speed.

Usage:
  python3 scripts/generate_aspect_mnemonics.py                 # all cards without mnemonics
  python3 scripts/generate_aspect_mnemonics.py --limit 50      # first 50 cards
  python3 scripts/generate_aspect_mnemonics.py --dry-run       # preview
  python3 scripts/generate_aspect_mnemonics.py --card CARD_ID  # single card

Run on server: cd /opt/petrarca && python3 scripts/generate_aspect_mnemonics.py
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from db import get_connection, init_db

MNEMONIC_PROMPT = """You are generating memory aids (mnemonics) for a knowledge retention system about history.

For each position on this card, generate a SHORT, memorable mnemonic (1-2 sentences max) using the strategy appropriate to its type:

TYPE-SPECIFIC STRATEGIES:
- **TEMPORAL** (dates): Anchor to well-known events. "Same year as the fall of Constantinople" or "50 years after the Black Death". Use BC/AD events the learner likely knows.
- **RELATIONAL** (people): Role chain or network position. "Caesar's assassin who later lost at Philippi" or "Tutor to Alexander, student of Plato". Show the person's position in a relationship web.
- **STRUCTURAL** (why/significance): Cause-effect chain. "Because Rome lost 80,000 men, they abandoned pitched battle for Fabian delay" or "This is why Sicily switched from Greek to Latin". Make the causal logic stick.
- **PARALLEL** (connections/comparisons): Contrast or parallel. "Unlike Athens which was a democracy, Syracuse was a tyranny" or "Same strategy Hannibal used at Cannae, but at sea". Bridge to something already known.
- **IDENTITY** (events/facts): Vivid image or distinctive detail. "The eruption that preserved an entire Roman city" or "The only Roman dictator who voluntarily gave up power". One striking detail that makes it unforgettable.

RULES:
- Keep each mnemonic to 1-2 sentences max
- Reference OTHER historical events/people the learner likely knows (major events, famous figures)
- Never just restate the answer — CONNECT it to something else
- For dates, always give a relative anchor ("X years before/after Y")
- For people, always mention a relationship or role chain

Card: {card_title}
Domain: {domain_title}

Positions:
{positions_json}

Return JSON:
{{
  "mnemonics": [
    {{
      "position_id": "the position's id",
      "mnemonic": "the memory aid text",
      "mnemonic_type": "the strategy used (temporal_anchor/role_chain/cause_effect/contrast/vivid_detail)"
    }}
  ]
}}"""

# Map hook_type to mnemonic_type for the output
HOOK_TO_MNEMONIC_TYPE = {
    'TEMPORAL': 'temporal_anchor',
    'RELATIONAL': 'role_chain',
    'STRUCTURAL': 'cause_effect',
    'PARALLEL': 'contrast',
    'IDENTITY': 'vivid_detail',
}


def generate_mnemonics_for_card(card: dict, positions: list[dict], domain_title: str) -> list[dict] | None:
    """Generate mnemonics for all positions on one card."""
    pos_for_prompt = []
    for p in positions:
        pos_for_prompt.append({
            'position_id': p['id'],
            'hook_type': p['hook_type'] or 'IDENTITY',
            'question': p['question_text'],
            'answer': p['answer_text'],
        })

    prompt = MNEMONIC_PROMPT.format(
        card_title=card['title'],
        domain_title=domain_title,
        positions_json=json.dumps(pos_for_prompt, indent=2),
    )

    parsed = call_claude_json(prompt, timeout=180, model='sonnet')
    if not isinstance(parsed, dict):
        return None
    return parsed.get('mnemonics', [])


def main():
    parser = argparse.ArgumentParser(description='Generate type-specific mnemonics for aspect positions')
    parser.add_argument('--limit', type=int, help='Process at most N cards')
    parser.add_argument('--card', type=str, help='Process a single card by ID')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--force', action='store_true', help='Regenerate even if mnemonics exist')
    args = parser.parse_args()

    init_db()
    conn = get_connection()

    if args.card:
        cards = conn.execute('''
            SELECT sc.id, sc.title, sc.domain_id, cd.title as domain_title
            FROM structural_cards sc
            LEFT JOIN curriculum_domains cd ON cd.id = sc.domain_id
            WHERE sc.id = ? AND sc.card_type = 'aspect'
        ''', (args.card,)).fetchall()
    else:
        # Find aspect cards that have positions without mnemonics
        mnemonic_filter = '' if args.force else '''
            AND EXISTS (
                SELECT 1 FROM structural_positions sp
                WHERE sp.card_id = sc.id
                AND (sp.mnemonic IS NULL OR sp.mnemonic = '')
            )'''
        cards = conn.execute(f'''
            SELECT sc.id, sc.title, sc.domain_id, cd.title as domain_title
            FROM structural_cards sc
            LEFT JOIN curriculum_domains cd ON cd.id = sc.domain_id
            WHERE sc.card_type = 'aspect'
            {mnemonic_filter}
            ORDER BY sc.review_count DESC, sc.created_at
            {f'LIMIT {args.limit}' if args.limit else ''}
        ''').fetchall()

    print(f'Found {len(cards)} aspect cards to process')
    if not cards:
        print('Nothing to do.')
        return

    total_updated = 0
    errors = 0

    for i, card in enumerate(cards):
        card = dict(card)
        positions = [dict(r) for r in conn.execute('''
            SELECT id, position, question_text, answer_text, hook_type, mnemonic
            FROM structural_positions
            WHERE card_id = ?
            ORDER BY position
        ''', (card['id'],)).fetchall()]

        if not args.force:
            positions = [p for p in positions if not p.get('mnemonic')]

        if not positions:
            continue

        print(f'[{i+1}/{len(cards)}] {card["title"][:50]} ({len(positions)} positions)...', end='', flush=True)

        if args.dry_run:
            print(' [DRY RUN]')
            for p in positions:
                print(f'    {p["hook_type"]:<12} {p["question_text"][:50]}')
            continue

        mnemonics = generate_mnemonics_for_card(card, positions, card.get('domain_title', ''))
        if not mnemonics:
            print(' FAILED')
            errors += 1
            time.sleep(1)
            continue

        # Update positions
        mn_by_id = {m['position_id']: m for m in mnemonics}
        count = 0
        for p in positions:
            mn = mn_by_id.get(p['id'])
            if mn and mn.get('mnemonic'):
                conn.execute('''
                    UPDATE structural_positions
                    SET mnemonic = ?, mnemonic_type = ?
                    WHERE id = ?
                ''', (mn['mnemonic'], mn.get('mnemonic_type', ''), p['id']))
                count += 1

        conn.commit()
        total_updated += count
        print(f' OK ({count} mnemonics)')

        # Rate limit
        time.sleep(0.3)

    print(f'\n{"="*60}')
    print(f'SUMMARY')
    print(f'  Cards processed: {len(cards)}')
    print(f'  Positions updated: {total_updated}')
    print(f'  Errors: {errors}')
    conn.close()


if __name__ == '__main__':
    main()
