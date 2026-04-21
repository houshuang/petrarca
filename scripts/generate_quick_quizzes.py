#!/usr/bin/env python3
"""Generate diverse quick quiz types from key_facts.

Quiz types:
  - date_reverse: "What happened in {year}?" (deterministic)
  - order: "What came first, A or B?" (deterministic, same-domain pairs)
  - role: "What was {person}'s role in {event}?" (Gemini Flash)
  - causal: "What caused {event}?" / "What resulted from {event}?" (Gemini Flash)
  - location: "Where did {event} take place?" (Gemini Flash)

Follows principle #7: generate DETERMINISTICALLY from key_facts where possible.
Only use LLM for natural-language quality (role, causal, location).

Deduplicates against existing microlearning_quizzes at 0.82 cosine via limbic.
"""
import hashlib
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from curriculum_db import get_connection
from claude_llm import call_claude_json

# ── Prompts ──────────────────────────────────────────────────────────────

ROLE_QUIZ_PROMPT = """Generate role-based quiz questions for a knowledge retention system.

For each person-fact below, generate a quiz that tests the person's SPECIFIC role in the context given.
The question should be answerable with the person's name. The answer should include
their specific role (not just their general biography).

BAD question: "Who was a Roman general?" (too vague)
GOOD question: "Who commanded the two-year siege of Syracuse and allegedly ordered Archimedes spared?"

Facts:
{facts_json}

Return JSON array:
[
  {{
    "fact_idx": 0,
    "question": "role-testing question",
    "answer": "Person Name — specific role description"
  }}
]"""

CAUSAL_QUIZ_PROMPT = """Generate cause/effect quiz questions for a knowledge retention system.

For each event-fact below, generate ONE quiz that tests either:
- What CAUSED this event (if a clear cause exists)
- What RESULTED from this event (if a clear consequence exists)
- Where this event TOOK PLACE (if a specific location is relevant)

Pick whichever angle produces the most useful learning question. The answer should be
concise (1-2 sentences) and specific.

BAD: "What caused Rome to fall?" (too broad)
GOOD: "What military reform by Marius (107 BC) shifted soldier loyalty from state to commander?"

Facts:
{facts_json}

Return JSON array:
[
  {{
    "fact_idx": 0,
    "quiz_type": "causal" or "location",
    "question": "cause/effect/location question",
    "answer": "concise specific answer"
  }}
]"""


def _ensure_quiz_type_column(conn):
    """Add quiz_type column if it doesn't exist yet."""
    try:
        conn.execute("SELECT quiz_type FROM microlearning_quizzes LIMIT 0")
    except Exception:
        conn.execute("ALTER TABLE microlearning_quizzes ADD COLUMN quiz_type TEXT")
        conn.commit()
        print("[quick-quiz] Added quiz_type column to microlearning_quizzes")


def _load_dedup_model(conn):
    """Load embedding model + existing quiz embeddings for dedup."""
    try:
        from limbic.amygdala import EmbeddingModel
        model = EmbeddingModel()
        existing_texts = [r['question'] for r in conn.execute(
            "SELECT question FROM microlearning_quizzes WHERE status='active'"
        ).fetchall()]
        existing_embedded = []
        if existing_texts:
            # Batch embed in chunks of 256
            for i in range(0, len(existing_texts), 256):
                chunk = existing_texts[i:i + 256]
                vecs = model.embed_batch(chunk)
                existing_embedded.extend(zip(chunk, vecs))
        print(f"[quick-quiz] Loaded {len(existing_embedded)} existing quizzes for dedup")
        return model, existing_embedded
    except Exception as e:
        print(f"[quick-quiz] WARNING: dedup disabled: {e}")
        return None, []


def _is_duplicate(question: str, existing_embedded: list, model, threshold: float = 0.82) -> bool:
    """Check if a question is too similar to any existing quiz."""
    if not model or not existing_embedded:
        return False
    import numpy as np
    qvec = model.embed(question)
    for _, evec in existing_embedded:
        sim = float(np.dot(qvec, evec) / (np.linalg.norm(qvec) * np.linalg.norm(evec) + 1e-9))
        if sim >= threshold:
            return True
    return False


def _find_or_create_card(conn, node_id: str, domain_id: str) -> str:
    """Find or create a microlearning_cards container for quizzes."""
    mc = conn.execute(
        'SELECT id FROM microlearning_cards WHERE source_node_id=? AND source_domain=? LIMIT 1',
        (node_id, domain_id)).fetchone()
    if mc:
        return mc['id']
    card_id = hashlib.md5(f"{node_id}:{domain_id}:quickquiz".encode()).hexdigest()[:12]
    now_ms = int(time.time() * 1000)
    conn.execute('''
        INSERT OR IGNORE INTO microlearning_cards
        (id, query, source_node_id, source_domain, content, status, created_at, source_type)
        VALUES (?,?,?,?,?,?,?,?)
    ''', (card_id, f"Quick quizzes for {node_id}", node_id,
          domain_id, '', 'completed', now_ms, 'quick_quiz'))
    return card_id


def _store_quiz(conn, card_id: str, question: str, answer: str, fact_id: str,
                rich_answer: str, quiz_type: str, existing_embedded: list, model) -> bool:
    """Store a quiz, returning True if stored (not deduped)."""
    if _is_duplicate(question, existing_embedded, model):
        return False
    quiz_id = hashlib.md5(f"{card_id}:{fact_id}:{quiz_type}:{question[:40]}".encode()).hexdigest()[:12]
    now_ms = int(time.time() * 1000)
    try:
        conn.execute('''
            INSERT OR IGNORE INTO microlearning_quizzes
            (id, card_id, question, answer, fact_id, rich_answer,
             status, stability_days, due_at, review_count, created_at, quiz_type)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (quiz_id, card_id, question, answer, fact_id, rich_answer,
              'active', 1.0, now_ms + 86400000, 0, now_ms, quiz_type))
    except Exception as e:
        print(f"  Store error: {e}")
        return False
    if model:
        existing_embedded.append((question, model.embed(question)))
    return True


# ── Deterministic generators ─────────────────────────────────────────────

def generate_date_reverse_quizzes(conn, model, existing_embedded) -> tuple[int, int]:
    """For date facts with year answers, generate "What happened in {year}?" reversal."""
    stored, skipped = 0, 0

    rows = conn.execute('''
        SELECT cn.id as node_id, cn.domain_id, cn.key_facts, cn.title as node_title
        FROM curriculum_nodes cn
        JOIN curriculum_domains cd ON cd.id = cn.domain_id
        WHERE cn.key_facts IS NOT NULL AND cn.key_facts != '[]'
    ''').fetchall()

    for row in rows:
        key_facts = json.loads(row['key_facts'])
        for fact in key_facts:
            if fact.get('type') != 'date':
                continue
            question = fact.get('question', '')
            answer = fact.get('answer', '')
            if not question or not answer:
                continue

            # The existing question is typically "When did X happen?"
            # Generate the reverse: "What happened in {year}?"
            # Extract year-like content from the answer
            year = answer.strip().rstrip('.')
            if not year:
                continue

            reverse_q = f"What happened in {year}? (Context: {row['node_title']})"
            reverse_a = question.replace('When did ', '').replace('When was ', '').rstrip('?').strip()
            if not reverse_a or len(reverse_a) < 5:
                reverse_a = question  # fallback to original question as hint

            card_id = _find_or_create_card(conn, row['node_id'], row['domain_id'])
            if _store_quiz(conn, card_id, reverse_q, reverse_a,
                          fact.get('id', ''), answer, 'date_reverse',
                          existing_embedded, model):
                stored += 1
            else:
                skipped += 1

    return stored, skipped


def generate_order_quizzes(conn, model, existing_embedded) -> tuple[int, int]:
    """Generate "What came first, A or B?" quizzes from date pairs in same domain."""
    stored, skipped = 0, 0

    # Collect all date facts with numeric years, grouped by domain
    domain_date_facts: dict[str, list] = {}
    rows = conn.execute('''
        SELECT cn.id as node_id, cn.domain_id, cn.key_facts, cn.title as node_title
        FROM curriculum_nodes cn
        WHERE cn.key_facts IS NOT NULL AND cn.key_facts != '[]'
    ''').fetchall()

    for row in rows:
        key_facts = json.loads(row['key_facts'])
        for fact in key_facts:
            if fact.get('type') != 'date':
                continue
            answer = fact.get('answer', '').strip()
            question = fact.get('question', '').strip()
            if not answer or not question:
                continue

            # Parse year from answer (handle "X BC", "X AD", plain numbers)
            year_num = _parse_year(answer)
            if year_num is None:
                continue

            domain = row['domain_id']
            if domain not in domain_date_facts:
                domain_date_facts[domain] = []
            domain_date_facts[domain].append({
                'node_id': row['node_id'],
                'node_title': row['node_title'],
                'fact': fact,
                'year': year_num,
                'year_display': answer.strip().rstrip('.'),
                'event_desc': question,
            })

    # Generate order quizzes: pick pairs within 200 years
    for domain, facts in domain_date_facts.items():
        facts.sort(key=lambda f: f['year'])
        pairs_generated = 0
        max_pairs_per_domain = 30

        for i in range(len(facts)):
            if pairs_generated >= max_pairs_per_domain:
                break
            # Find a suitable partner (within 200 years, different node)
            candidates = [f for f in facts[i + 1:]
                         if abs(f['year'] - facts[i]['year']) <= 200
                         and f['node_id'] != facts[i]['node_id']]
            if not candidates:
                continue

            partner = random.choice(candidates)
            a, b = facts[i], partner
            if random.random() > 0.5:
                a, b = b, a  # randomize order in question

            # Extract event description from the question
            event_a = _event_from_question(a['event_desc'])
            event_b = _event_from_question(b['event_desc'])

            question = f"What came first: {event_a} or {event_b}?"
            if a['year'] < b['year']:
                first, second = a, b
            else:
                first, second = b, a
            answer = f"{_event_from_question(first['event_desc'])} ({first['year_display']}) came before {_event_from_question(second['event_desc'])} ({second['year_display']})"

            card_id = _find_or_create_card(conn, a['node_id'], domain)
            if _store_quiz(conn, card_id, question, answer,
                          a['fact']['id'], '', 'order',
                          existing_embedded, model):
                stored += 1
                pairs_generated += 1
            else:
                skipped += 1

    return stored, skipped


def _parse_year(answer: str) -> int | None:
    """Parse a year from a key_fact answer like '480 BC', '1091 AD', '1453'."""
    import re
    answer = answer.strip().rstrip('.')
    m = re.match(r'^(\d{1,4})\s*(?:BC|BCE)$', answer, re.IGNORECASE)
    if m:
        return -int(m.group(1))
    m = re.match(r'^(\d{1,4})\s*(?:AD|CE)?$', answer, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Handle "c. 750 BC" style
    m = re.match(r'^c\.?\s*(\d{1,4})\s*(?:BC|BCE)$', answer, re.IGNORECASE)
    if m:
        return -int(m.group(1))
    m = re.match(r'^c\.?\s*(\d{1,4})\s*(?:AD|CE)?$', answer, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _event_from_question(q: str) -> str:
    """Extract event description from 'When did X happen?' style questions."""
    q = q.strip().rstrip('?')
    for prefix in ['When did ', 'When was ', 'In what year did ', 'In what year was ']:
        if q.startswith(prefix):
            q = q[len(prefix):]
            break
    # Remove trailing "take place", "occur", "happen"
    for suffix in [' take place', ' occur', ' happen', ' begin', ' start', ' end']:
        if q.endswith(suffix):
            q = q[:-len(suffix)]
            break
    return q.strip()


# ── LLM-based generators ────────────────────────────────────────────────

def generate_role_quizzes(conn, model, existing_embedded) -> tuple[int, int]:
    """Generate role quizzes for person-type facts using Gemini Flash."""
    stored, skipped = 0, 0

    # Collect person facts in batches by domain
    rows = conn.execute('''
        SELECT cn.id as node_id, cn.domain_id, cn.key_facts, cn.title as node_title
        FROM curriculum_nodes cn
        WHERE cn.key_facts IS NOT NULL AND cn.key_facts != '[]'
    ''').fetchall()

    # Group person facts into batches of ~15 for efficient LLM calls
    batch = []
    batch_meta = []  # (node_id, domain_id, fact)

    for row in rows:
        key_facts = json.loads(row['key_facts'])
        for fact in key_facts:
            if fact.get('type') != 'person':
                continue
            if not fact.get('question') or not fact.get('answer'):
                continue
            batch.append({
                'question': fact['question'],
                'answer': fact['answer'],
                'context': row['node_title'],
            })
            batch_meta.append((row['node_id'], row['domain_id'], fact))

            if len(batch) >= 15:
                s, sk = _process_role_batch(conn, batch, batch_meta, model, existing_embedded)
                stored += s
                skipped += sk
                batch, batch_meta = [], []
                time.sleep(1)  # rate limit

    if batch:
        s, sk = _process_role_batch(conn, batch, batch_meta, model, existing_embedded)
        stored += s
        skipped += sk

    return stored, skipped


def _process_role_batch(conn, batch, batch_meta, model, existing_embedded) -> tuple[int, int]:
    """Process a batch of person facts through Gemini Flash."""
    stored, skipped = 0, 0
    facts_for_prompt = [{'idx': i, **f} for i, f in enumerate(batch)]
    prompt = ROLE_QUIZ_PROMPT.format(facts_json=json.dumps(facts_for_prompt, indent=2))

    quizzes = call_claude_json(prompt, timeout=180, model='sonnet')
    if not isinstance(quizzes, list):
        print("  WARNING: No/invalid result for role batch")
        return 0, 0

    for quiz in quizzes:
        idx = quiz.get('fact_idx', -1)
        if idx < 0 or idx >= len(batch_meta):
            continue
        node_id, domain_id, fact = batch_meta[idx]
        question = quiz.get('question', '').strip()
        answer = quiz.get('answer', '').strip()
        if not question or not answer:
            continue

        card_id = _find_or_create_card(conn, node_id, domain_id)
        if _store_quiz(conn, card_id, question, answer,
                      fact.get('id', ''), fact.get('answer', ''),
                      'role', existing_embedded, model):
            stored += 1
        else:
            skipped += 1

    return stored, skipped


def generate_causal_location_quizzes(conn, model, existing_embedded) -> tuple[int, int]:
    """Generate causal/location quizzes for event-type facts using Gemini Flash."""
    stored, skipped = 0, 0

    rows = conn.execute('''
        SELECT cn.id as node_id, cn.domain_id, cn.key_facts, cn.title as node_title
        FROM curriculum_nodes cn
        WHERE cn.key_facts IS NOT NULL AND cn.key_facts != '[]'
    ''').fetchall()

    batch = []
    batch_meta = []

    for row in rows:
        key_facts = json.loads(row['key_facts'])
        for fact in key_facts:
            if fact.get('type') not in ('event', 'significance'):
                continue
            if not fact.get('question') or not fact.get('answer'):
                continue
            batch.append({
                'question': fact['question'],
                'answer': fact['answer'],
                'context': row['node_title'],
                'type': fact['type'],
            })
            batch_meta.append((row['node_id'], row['domain_id'], fact))

            if len(batch) >= 15:
                s, sk = _process_causal_batch(conn, batch, batch_meta, model, existing_embedded)
                stored += s
                skipped += sk
                batch, batch_meta = [], []
                time.sleep(1)

    if batch:
        s, sk = _process_causal_batch(conn, batch, batch_meta, model, existing_embedded)
        stored += s
        skipped += sk

    return stored, skipped


def _process_causal_batch(conn, batch, batch_meta, model, existing_embedded) -> tuple[int, int]:
    """Process a batch of event facts through Gemini Flash."""
    stored, skipped = 0, 0
    facts_for_prompt = [{'idx': i, **f} for i, f in enumerate(batch)]
    prompt = CAUSAL_QUIZ_PROMPT.format(facts_json=json.dumps(facts_for_prompt, indent=2))

    quizzes = call_claude_json(prompt, timeout=180, model='sonnet')
    if not isinstance(quizzes, list):
        return 0, 0

    for quiz in quizzes:
        idx = quiz.get('fact_idx', -1)
        if idx < 0 or idx >= len(batch_meta):
            continue
        node_id, domain_id, fact = batch_meta[idx]
        question = quiz.get('question', '').strip()
        answer = quiz.get('answer', '').strip()
        quiz_type = quiz.get('quiz_type', 'causal')
        if quiz_type not in ('causal', 'location'):
            quiz_type = 'causal'
        if not question or not answer:
            continue

        card_id = _find_or_create_card(conn, node_id, domain_id)
        if _store_quiz(conn, card_id, question, answer,
                      fact.get('id', ''), fact.get('answer', ''),
                      quiz_type, existing_embedded, model):
            stored += 1
        else:
            skipped += 1

    return stored, skipped


# ── Main ─────────────────────────────────────────────────────────────────

def main(dry_run: bool = False, types: list[str] | None = None):
    conn = get_connection()
    _ensure_quiz_type_column(conn)

    # Count existing quizzes
    existing_count = conn.execute(
        "SELECT COUNT(*) as n FROM microlearning_quizzes WHERE status='active'"
    ).fetchone()['n']
    print(f"\nExisting active quizzes: {existing_count}")

    # Count key_facts by type
    type_counts: dict[str, int] = {}
    rows = conn.execute(
        "SELECT key_facts FROM curriculum_nodes WHERE key_facts IS NOT NULL AND key_facts != '[]'"
    ).fetchall()
    for r in rows:
        for f in json.loads(r['key_facts']):
            t = f.get('type', 'unknown')
            type_counts[t] = type_counts.get(t, 0) + 1
    print(f"Key facts by type: {json.dumps(type_counts, indent=2)}")

    if dry_run:
        print("\n[DRY RUN] Would generate quizzes for types:", types or 'all')
        conn.close()
        return

    model, existing_embedded = _load_dedup_model(conn)

    all_types = types or ['date_reverse', 'order', 'role', 'causal']
    results = {}

    if 'date_reverse' in all_types:
        print(f"\n{'='*50}")
        print("Generating date_reverse quizzes (deterministic)...")
        s, sk = generate_date_reverse_quizzes(conn, model, existing_embedded)
        results['date_reverse'] = (s, sk)
        print(f"  Stored: {s}, Deduped: {sk}")
        conn.commit()

    if 'order' in all_types:
        print(f"\n{'='*50}")
        print("Generating order quizzes (deterministic)...")
        s, sk = generate_order_quizzes(conn, model, existing_embedded)
        results['order'] = (s, sk)
        print(f"  Stored: {s}, Deduped: {sk}")
        conn.commit()

    if 'role' in all_types:
        print(f"\n{'='*50}")
        print("Generating role quizzes (Gemini Flash)...")
        s, sk = generate_role_quizzes(conn, model, existing_embedded)
        results['role'] = (s, sk)
        print(f"  Stored: {s}, Deduped: {sk}")
        conn.commit()

    if 'causal' in all_types:
        print(f"\n{'='*50}")
        print("Generating causal/location quizzes (Gemini Flash)...")
        s, sk = generate_causal_location_quizzes(conn, model, existing_embedded)
        results['causal'] = (s, sk)
        print(f"  Stored: {s}, Deduped: {sk}")
        conn.commit()

    # Summary
    total_stored = sum(s for s, _ in results.values())
    total_skipped = sum(sk for _, sk in results.values())
    new_count = conn.execute(
        "SELECT COUNT(*) as n FROM microlearning_quizzes WHERE status='active'"
    ).fetchone()['n']

    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"  Before: {existing_count} quizzes")
    print(f"  Generated: {total_stored} new, {total_skipped} deduped")
    print(f"  After: {new_count} quizzes")
    for qt, (s, sk) in results.items():
        print(f"    {qt}: {s} stored, {sk} deduped")

    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate diverse quick quiz types from key_facts')
    parser.add_argument('--dry-run', action='store_true', help='Count facts without generating')
    parser.add_argument('--types', nargs='*',
                       choices=['date_reverse', 'order', 'role', 'causal'],
                       help='Quiz types to generate (default: all)')
    args = parser.parse_args()
    main(dry_run=args.dry_run, types=args.types)
