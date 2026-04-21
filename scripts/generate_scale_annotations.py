#!/usr/bin/env python3
"""Generate rich scale annotations for sequence card gaps.

Adds human-meaningful comparisons for temporal gaps between milestones.
Instead of just "— 46 years —", produces things like:
"46 years — roughly a human lifetime, the same gap as WWII to today"

Uses the user's known entities from shared_entities to create personalized anchors.

Usage:
  python3 scripts/generate_scale_annotations.py               # all sequence cards
  python3 scripts/generate_scale_annotations.py --card ID     # single card
  python3 scripts/generate_scale_annotations.py --dry-run     # preview

Run on server: cd /opt/petrarca && python3 scripts/generate_scale_annotations.py
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from db import get_connection, init_db

SCALE_PROMPT = """You are generating scale annotations for gaps between milestones on a history timeline card.

For each gap between consecutive milestones, generate a SHORT (under 15 words) human-meaningful comparison that makes the time span visceral.

RULES:
- Use HISTORICAL parallels the learner likely knows, not modern pop culture
- Good: "roughly the same span as Augustus' principate" (41 years)
- Good: "longer than Alexander's entire life" (for 35+ year gaps)
- Good: "barely a decade — within living memory" (for 10-year gaps)
- BAD: "about as long as the iPhone has existed" — not historical
- BAD: "273 years, longer than the USA has existed" — modern, not historical
- For gaps < 10 years: use "within a decade" or "just X years" — don't force a comparison
- For gaps > 100 years: reference a major period ("longer than the entire Pax Romana")
- NEVER use the same comparison twice in one card

The user has studied these historical domains: {user_domains}

Milestones:
{milestones_json}

Return JSON:
{{
  "annotations": [
    {{
      "from_position": 0,
      "to_position": 1,
      "gap_years": 46,
      "annotation": "roughly a human lifetime in antiquity"
    }}
  ]
}}"""


def generate_for_card(card: dict, positions: list[dict], user_domains: list[str]) -> list[dict] | None:
    """Generate scale annotations for gaps between milestones."""
    milestones_for_prompt = []
    for p in positions:
        v = json.loads(p['question_variants'] or '{}') if isinstance(p['question_variants'], str) else (p['question_variants'] or {})
        milestones_for_prompt.append({
            'position': p['position'],
            'year': v.get('year'),
            'year_display': v.get('year_display', ''),
            'answer_text': p['answer_text'][:80],
        })

    prompt = SCALE_PROMPT.format(
        user_domains=', '.join(user_domains[:10]),
        milestones_json=json.dumps(milestones_for_prompt, indent=2),
    )

    parsed = call_claude_json(prompt, timeout=120, model='sonnet')
    if not isinstance(parsed, dict):
        return None
    return parsed.get('annotations', [])


def main():
    parser = argparse.ArgumentParser(description='Generate scale annotations for sequence card gaps')
    parser.add_argument('--card', type=str, help='Process a single card by ID')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    parser.add_argument('--force', action='store_true', help='Regenerate even if annotations exist')
    args = parser.parse_args()

    init_db()
    conn = get_connection()

    # Get user's studied domains for personalized comparisons
    user_domains = [r['title'] for r in conn.execute('''
        SELECT cd.title FROM curriculum_domains cd
        WHERE EXISTS (SELECT 1 FROM knowledge_items ki WHERE ki.curriculum_domain = cd.id)
        ORDER BY (SELECT COUNT(*) FROM knowledge_items ki WHERE ki.curriculum_domain = cd.id) DESC
    ''').fetchall()]

    if args.card:
        cards = conn.execute('''
            SELECT sc.id, sc.title, sc.domain_id, sc.hooks
            FROM structural_cards sc
            WHERE sc.id = ? AND sc.card_type = 'sequence'
        ''', (args.card,)).fetchall()
    else:
        cards = conn.execute('''
            SELECT sc.id, sc.title, sc.domain_id, sc.hooks
            FROM structural_cards sc
            WHERE sc.card_type = 'sequence'
            ORDER BY sc.review_count DESC, sc.created_at
        ''').fetchall()

    if not cards:
        print('No sequence cards found.')
        return

    print(f'Processing {len(cards)} sequence cards...')
    print(f'User domains: {", ".join(user_domains[:5])}...')

    total_annotations = 0
    errors = 0

    for i, card in enumerate(cards):
        card = dict(card)

        # Check if card already has scale annotations
        existing_hooks = json.loads(card['hooks'] or '{}') if card['hooks'] else {}
        if isinstance(existing_hooks, list):
            existing_hooks = {}
        if not args.force and existing_hooks.get('scale_annotations'):
            print(f'[{i+1}/{len(cards)}] {card["title"][:50]} — SKIP (has annotations)')
            continue

        positions = [dict(r) for r in conn.execute('''
            SELECT id, position, question_text, answer_text, question_variants
            FROM structural_positions
            WHERE card_id = ?
            ORDER BY position
        ''', (card['id'],)).fetchall()]

        if len(positions) < 2:
            continue

        print(f'[{i+1}/{len(cards)}] {card["title"][:50]} ({len(positions)-1} gaps)...', end='', flush=True)

        if args.dry_run:
            print(' [DRY RUN]')
            continue

        annotations = generate_for_card(card, positions, user_domains)
        if not annotations:
            print(' FAILED')
            errors += 1
            time.sleep(1)
            continue

        # Store annotations in the card's hooks JSON
        if isinstance(existing_hooks, list):
            existing_hooks = {'milestone_hooks': existing_hooks}
        existing_hooks['scale_annotations'] = annotations
        conn.execute(
            'UPDATE structural_cards SET hooks = ? WHERE id = ?',
            (json.dumps(existing_hooks), card['id'])
        )

        # Also store per-position: update question_variants with scale_to_next
        ann_by_from = {a['from_position']: a for a in annotations}
        for p in positions:
            ann = ann_by_from.get(p['position'])
            if ann:
                v = json.loads(p['question_variants'] or '{}') if isinstance(p['question_variants'], str) else (p['question_variants'] or {})
                v['scale_to_next'] = ann.get('annotation', '')
                v['gap_years'] = ann.get('gap_years', 0)
                conn.execute(
                    'UPDATE structural_positions SET question_variants = ? WHERE id = ?',
                    (json.dumps(v), p['id'])
                )

        conn.commit()
        total_annotations += len(annotations)
        print(f' OK ({len(annotations)} annotations)')
        time.sleep(0.3)

    print(f'\n{"="*60}')
    print(f'SUMMARY')
    print(f'  Cards processed: {len(cards)}')
    print(f'  Total annotations: {total_annotations}')
    print(f'  Errors: {errors}')
    conn.close()


if __name__ == '__main__':
    main()
