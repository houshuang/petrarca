#!/usr/bin/env python3
"""Generate sequence cards from key_facts + entity date ranges.

Sequence cards test chronological ordering within bounded periods.
Each card has 5-8 milestones (mix of events and persons), shown as a
timeline with 2 blanks per appearance that rotate based on FSRS state.

Uses Gemini Flash for speed (batch generation, not user-facing).
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from curriculum_db import get_connection

# ── Prompt for sequence identification + milestone generation ────────────

SEQUENCE_IDENTIFICATION_PROMPT = """You are identifying natural chronological sequences for a knowledge retention system.

Given a domain's key_facts (with dates) and notable entities with date ranges, identify 3-8 NATURAL SEQUENCE BOUNDARIES — periods with clear start/end points that tell a coherent story.

Good sequence boundaries:
- A person's career: "Caesar's Rise and Fall" (100–44 BC)
- A dynasty or succession: "The Norman Kings of Sicily" (1071–1194)
- A period arc: "The Punic Wars" (264–146 BC)
- A campaign or conflict: "Hannibal's Italian Campaign" (218–203 BC)

Bad sequence boundaries:
- Too broad: "All of Roman History" — break into meaningful periods
- Too narrow: "The Battle of Cannae" — not enough milestones for a sequence
- Arbitrary: "250–200 BC" — no natural narrative boundary

RULES:
- Each sequence should have 5-8 milestones (mix events AND persons/rulers, not just ruler succession)
- Milestones must be CHRONOLOGICALLY ORDERED with specific years (or approximate: "c. 405 BC")
- Each milestone needs a question_text (what to ask when blanked) and answer_text (what to reveal)
- question_text must NOT leak the answer — frame by context, not by the answer itself
- Include temporal hooks: brief annotations connecting milestones to each other or to known events
- Scale annotations must use meaningful historical connections, NOT arbitrary modern comparisons
  BAD: "273 years, longer than the USA has existed"
  GOOD: "80 years — roughly the same gap as between the World Wars and today"
  BEST: "During this same period, Athens was building the Parthenon"
- Skip sequences where we have fewer than 4 dateable milestones in the data

Domain: {domain_title}
Date-type key_facts:
{date_facts_json}

Event-type key_facts with dates:
{event_facts_json}

Notable entities with date ranges:
{entities_json}

Return JSON:
{{
  "sequences": [
    {{
      "title": "sequence title",
      "description": "1-2 sentence description of the narrative arc",
      "date_start": -264,
      "date_end": -146,
      "milestones": [
        {{
          "position": 0,
          "year": -264,
          "year_display": "264 BC",
          "question_text": "What triggered the First Punic War?",
          "answer_text": "Rome intervened in Messana, starting a 23-year war with Carthage over Sicily",
          "fact_id": "matching_fact_id_if_exists",
          "entity_id": "matching_entity_id_if_exists",
          "hook": "Same decade as Ashoka's edicts in India"
        }}
      ]
    }}
  ]
}}"""


def gather_domain_data(domain_id: str, conn) -> dict:
    """Collect all dateable facts and entities for a domain."""
    domain = conn.execute(
        "SELECT id, title FROM curriculum_domains WHERE id=?", (domain_id,)
    ).fetchone()
    if not domain:
        return None

    # Get all key_facts with dates from this domain's nodes
    nodes = conn.execute("""
        SELECT cn.id, cn.title, cn.key_facts, cn.date_start, cn.date_end
        FROM curriculum_nodes cn
        WHERE cn.domain_id = ? AND cn.key_facts IS NOT NULL AND cn.key_facts != '[]'
        ORDER BY cn.date_start
    """, (domain_id,)).fetchall()

    date_facts = []
    event_facts = []
    for node in nodes:
        kf = json.loads(node['key_facts']) if node['key_facts'] else []
        for f in kf:
            entry = {
                'id': f.get('id', ''),
                'node_id': node['id'],
                'node_title': node['title'],
                'question': f.get('question', ''),
                'answer': f.get('answer', ''),
                'type': f.get('type', ''),
                'entities': f.get('entities', []),
            }
            if f.get('type') == 'date':
                date_facts.append(entry)
            elif f.get('type') == 'event' and any(
                c.isdigit() for c in f.get('answer', '')
            ):
                # Event facts that mention dates in their answer
                event_facts.append(entry)

    # Get entities linked to this domain with date ranges
    entities = conn.execute("""
        SELECT DISTINCT se.entity_id, se.name, se.entity_type,
               se.date_start, se.date_end, se.dates, se.wikidata_qid
        FROM shared_entities se
        JOIN entity_curriculum_links ecl ON ecl.entity_id = se.entity_id
        JOIN curriculum_nodes cn ON cn.id = ecl.node_id
        WHERE cn.domain_id = ?
        AND se.date_start IS NOT NULL
        AND se.entity_type IN ('person', 'ruler', 'dynasty')
        ORDER BY se.date_start
    """, (domain_id,)).fetchall()

    entity_list = [{
        'entity_id': e['entity_id'],
        'name': e['name'],
        'type': e['entity_type'],
        'date_start': e['date_start'],
        'date_end': e['date_end'],
        'dates': e['dates'],
    } for e in entities]

    return {
        'domain_id': domain_id,
        'domain_title': domain['title'],
        'date_facts': date_facts,
        'event_facts': event_facts,
        'entities': entity_list,
    }


def generate_sequences_for_domain(data: dict) -> list[dict] | None:
    """Call Gemini to identify sequences and generate milestones."""
    if not data['date_facts'] and not data['event_facts']:
        print(f"  No dateable facts for {data['domain_title']}")
        return None

    prompt = SEQUENCE_IDENTIFICATION_PROMPT.format(
        domain_title=data['domain_title'],
        date_facts_json=json.dumps(data['date_facts'][:80], indent=2),
        event_facts_json=json.dumps(data['event_facts'][:40], indent=2),
        entities_json=json.dumps(data['entities'][:50], indent=2),
    )

    parsed = call_claude_json(prompt, timeout=300, model='sonnet')

    if not isinstance(parsed, dict):
        print(f"  ERROR: No/invalid response for {data['domain_title']}")
        return None
    return parsed.get('sequences', [])


def store_sequence_card(seq: dict, domain_id: str, conn) -> str:
    """Store a sequence card and its milestone positions."""
    card_id = f"seq_{domain_id[:20]}_{uuid.uuid4().hex[:8]}"
    now_ms = int(time.time() * 1000)

    milestones = seq.get('milestones', [])
    hooks_json = json.dumps([m.get('hook', '') for m in milestones if m.get('hook')])

    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id,
         date_start, date_end, hooks, generation_source, due_at, created_at)
        VALUES (?, 'sequence', ?, ?, ?, ?, ?, ?, 'auto', ?, datetime('now'))
    """, (
        card_id,
        seq.get('title', ''),
        seq.get('description', ''),
        domain_id,
        seq.get('date_start'),
        seq.get('date_end'),
        hooks_json,
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
            pos_id,
            card_id,
            i,
            m.get('fact_id', ''),
            m.get('entity_id', ''),
            m.get('question_text', ''),
            m.get('answer_text', ''),
            json.dumps({
                'year': m.get('year'),
                'year_display': m.get('year_display', ''),
            }),
            m.get('hook', ''),
            now_ms,
        ))

    return card_id


def _domain_has_real_evidence(domain_id: str, conn) -> bool:
    """Does this domain have ≥1 knowledge_item whose sources include a book or voice capture?

    Matches ``_mix_structural_cards`` per-domain gate — gap-fill and self-assessment only
    rows do not count as evidence that the user has engaged with this domain.
    """
    row = conn.execute('''
        SELECT 1 FROM knowledge_items ki
        WHERE ki.curriculum_domain = ?
          AND (
              ki.sources LIKE '%"book_id": "%'
              OR ki.sources LIKE '%"source": "voice_capture%'
              OR ki.sources LIKE '%"transcript_id":%'
          )
        LIMIT 1
    ''', (domain_id,)).fetchone()
    return row is not None


def batch_generate(domain_ids: list[str] | None = None, dry_run: bool = False):
    """Generate sequence cards for specified domains."""
    conn = get_connection()

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

    for domain in domains:
        domain_id = domain['id']
        domain_title = domain['title']
        print(f"\n{'='*60}")
        print(f"Domain: {domain_title}")
        print(f"{'='*60}")

        if not _domain_has_real_evidence(domain_id, conn):
            print(f"  SKIP: no book or voice evidence in this domain")
            continue

        # Check for existing sequence cards
        existing = conn.execute(
            "SELECT COUNT(*) FROM structural_cards WHERE domain_id=? AND card_type='sequence'",
            (domain_id,)
        ).fetchone()[0]
        if existing > 0:
            print(f"  SKIP: {existing} sequence cards already exist")
            continue

        data = gather_domain_data(domain_id, conn)
        if not data:
            print(f"  SKIP: domain not found")
            continue

        print(f"  Data: {len(data['date_facts'])} date facts, {len(data['event_facts'])} event facts, {len(data['entities'])} entities")

        if dry_run:
            print(f"  [DRY RUN]")
            continue

        sequences = generate_sequences_for_domain(data)
        if not sequences:
            print(f"  ERROR: No sequences generated")
            continue

        for seq in sequences:
            milestones = seq.get('milestones', [])
            if len(milestones) < 4:
                print(f"  SKIP (<4 milestones): {seq.get('title', '?')}")
                continue

            card_id = store_sequence_card(seq, domain_id, conn)
            print(f"  OK: {seq.get('title', '?')} ({len(milestones)} milestones)")
            total_cards += 1
            total_positions += len(milestones)

        conn.commit()
        time.sleep(1)  # Rate limit between domains

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Sequences generated: {total_cards}")
    print(f"  Total milestones: {total_positions}")
    if not dry_run:
        print(f"  Committed to database")
    else:
        print(f"  [DRY RUN — nothing written]")

    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate sequence cards from key_facts + entities')
    parser.add_argument('--domains', nargs='*', help='Domain IDs to process (default: all)')
    parser.add_argument('--dry-run', action='store_true', help='Count without generating')
    args = parser.parse_args()

    batch_generate(domain_ids=args.domains, dry_run=args.dry_run)
