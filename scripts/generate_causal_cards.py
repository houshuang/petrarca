#!/usr/bin/env python3
"""Generate causal chain cards from key_facts significance/connection data.

Causal chains test understanding of WHY things happened — cause → effect
chains with 4-7 links. Each link has a cause, an effect, and a "why" text
connecting them.

Uses Gemini Flash for chain identification and link generation.
Stores as card_type='causal' in structural_cards + structural_positions.

Only generates for historical domains (skips Classical Reception + Philosophy
where "causation" is intellectual influence, not event chains).
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from curriculum_db import get_connection

# Historical domains only — no Classical Reception or Philosophy
# Match by substring since domain IDs are long slugs
HISTORICAL_DOMAIN_KEYWORDS = ['sicily', 'roman_republic', 'greece', 'byzantine', 'islamic']

CHAIN_IDENTIFICATION_PROMPT = """You are identifying natural causal chains for a knowledge retention system.

Given a domain's key_facts (significance + connection types), identify 3-5 NATURAL CAUSAL CHAINS —
sequences of causes and effects that tell a coherent "why" story.

Good chains (4-7 links each):
- "From Republic to Empire" — Gracchi reforms → Social War → Marius's army reforms → Civil wars → Caesar → Augustus
- "Why Sicily changed hands" — Greek colonization → Carthaginian competition → Roman conquest → Arab conquest → Norman conquest
- "The Translation Movement" — Greek texts → Syriac translations → Arabic translations → Latin translations → Renaissance

Bad chains:
- Too broad: "All of Roman history" — not a causal chain
- Too narrow: "Archimedes invented a screw" — single event, not a chain
- Just chronological: listing events without explaining WHY each caused the next

RULES:
- Each chain should have 4-7 links
- Each link needs:
  - event: what happened (concise, 1-2 sentences)
  - year_display: date or date range (e.g., "133 BC", "88-30 BC")
  - question_text: question to ask when blanked — frame by CAUSE/EFFECT, not by the answer
    BAD: "What did Marius do?" (too vague)
    GOOD: "What military reform changed soldier loyalty from state to commander?"
  - connection_to_next: 1-2 sentences explaining WHY this link caused the next one
    This is the educational payload — it should reveal a causal mechanism, not just say "and then"
- The FIRST link is always shown (anchor) — it sets the context
- Links should be CAUSALLY connected, not just chronologically ordered
- Use the key_facts data as raw material but synthesize chains, don't just list facts

Domain: {domain_title}

Significance-type key_facts (these reveal why things mattered):
{significance_facts}

Connection-type key_facts (these reveal links between events):
{connection_facts}

Date-type key_facts (for chronological grounding):
{date_facts}

Return JSON:
{{
  "chains": [
    {{
      "title": "chain title (evocative, not a spoiler)",
      "theme": "1-sentence description of what this chain explains",
      "links": [
        {{
          "event": "what happened",
          "year_display": "date or range",
          "question_text": "question when blanked",
          "connection_to_next": "why this caused the next link (null for last link)"
        }}
      ]
    }}
  ]
}}"""


def gather_domain_facts(conn, domain_id: str) -> tuple[list, list, list]:
    """Gather significance, connection, and date facts for a domain."""
    rows = conn.execute('''
        SELECT cn.id, cn.title, cn.key_facts
        FROM curriculum_nodes cn
        WHERE cn.domain_id = ? AND cn.key_facts IS NOT NULL AND cn.key_facts != '[]'
    ''', (domain_id,)).fetchall()

    sig_facts, conn_facts, date_facts = [], [], []
    for row in rows:
        key_facts = json.loads(row['key_facts'])
        for f in key_facts:
            entry = {
                'node_title': row['title'],
                'question': f.get('question', ''),
                'answer': f.get('answer', ''),
            }
            if f.get('type') == 'significance':
                sig_facts.append(entry)
            elif f.get('type') == 'connection':
                conn_facts.append(entry)
            elif f.get('type') == 'date':
                date_facts.append(entry)

    return sig_facts, conn_facts, date_facts


def generate_chains_for_domain(domain_id: str, domain_title: str, conn) -> list[dict] | None:
    """Generate causal chains for a domain via Gemini Flash."""
    sig_facts, conn_facts, date_facts = gather_domain_facts(conn, domain_id)

    if len(sig_facts) + len(conn_facts) < 5:
        print(f"  Skipping {domain_title}: too few significance/connection facts "
              f"({len(sig_facts)} sig, {len(conn_facts)} conn)")
        return None

    prompt = CHAIN_IDENTIFICATION_PROMPT.format(
        domain_title=domain_title,
        significance_facts=json.dumps(sig_facts[:30], indent=2),
        connection_facts=json.dumps(conn_facts[:30], indent=2),
        date_facts=json.dumps(date_facts[:30], indent=2),
    )

    parsed = call_claude_json(prompt, timeout=240, model='sonnet')
    if not isinstance(parsed, dict):
        return None
    return parsed.get('chains', [])


def store_causal_card(chain: dict, domain_id: str, conn) -> str:
    """Store a causal chain as structural_card + structural_positions."""
    card_id = f"causal_{domain_id}_{uuid.uuid4().hex[:8]}"
    now_ms = int(time.time() * 1000)

    links = chain.get('links', [])
    if len(links) < 3:
        return ''

    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id,
         generation_source, due_at, created_at)
        VALUES (?, 'causal', ?, ?, ?, 'auto', ?, datetime('now'))
    """, (
        card_id,
        chain.get('title', 'Causal Chain'),
        chain.get('theme', ''),
        domain_id,
        now_ms,
    ))

    for i, link in enumerate(links):
        pos_id = f"{card_id}_pos{i}"
        # Store connection_to_next in question_variants
        question_variants = json.dumps({
            'event': link.get('event', ''),
            'year_display': link.get('year_display', ''),
            'connection_to_next': link.get('connection_to_next'),
        })
        conn.execute("""
            INSERT INTO structural_positions
            (id, card_id, position, question_text, answer_text,
             question_variants, hook_type, stability_days, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'STRUCTURAL', 1.0, ?, datetime('now'))
        """, (
            pos_id,
            card_id,
            i,
            link.get('question_text', ''),
            link.get('event', ''),
            question_variants,
            now_ms,
        ))

    return card_id


def batch_generate(domain_ids: list[str] | None = None, dry_run: bool = False):
    """Generate causal chains for historical domains."""
    conn = get_connection()

    domains = conn.execute(
        "SELECT id, title FROM curriculum_domains"
    ).fetchall()
    domains = [dict(d) for d in domains]

    # Filter to historical domains (match by keyword in domain ID)
    if domain_ids:
        domains = [d for d in domains if d['id'] in domain_ids]
    else:
        domains = [d for d in domains
                   if any(kw in d['id'] for kw in HISTORICAL_DOMAIN_KEYWORDS)]

    # Check which domains already have causal cards
    existing = set(r['domain_id'] for r in conn.execute(
        "SELECT DISTINCT domain_id FROM structural_cards WHERE card_type = 'causal'"
    ).fetchall())

    total_cards = 0
    total_links = 0
    errors = 0

    for domain in domains:
        domain_id = domain['id']
        domain_title = domain['title']
        print(f"\n{'='*60}")
        print(f"Domain: {domain_title}")

        # Skip domains with no book or voice evidence — causal chains must test content
        # the user has actually read, not a synthesized lesson from the curriculum tree.
        has_evidence = conn.execute('''
            SELECT 1 FROM knowledge_items ki
            WHERE ki.curriculum_domain = ?
              AND (
                  ki.sources LIKE '%"book_id": "%'
                  OR ki.sources LIKE '%"source": "voice_capture%'
                  OR ki.sources LIKE '%"transcript_id":%'
              )
            LIMIT 1
        ''', (domain_id,)).fetchone()
        if not has_evidence:
            print(f"  SKIP: no book or voice evidence in this domain")
            continue

        if domain_id in existing:
            print(f"  SKIP (already has causal cards)")
            continue

        if dry_run:
            sig, con, dat = gather_domain_facts(conn, domain_id)
            print(f"  Facts: {len(sig)} significance, {len(con)} connection, {len(dat)} date")
            print(f"  [DRY RUN]")
            continue

        print(f"  Generating chains...", end='', flush=True)
        chains = generate_chains_for_domain(domain_id, domain_title, conn)
        if not chains:
            print(f" FAILED or skipped")
            errors += 1
            continue

        print(f" got {len(chains)} chains")
        for chain in chains:
            n_links = len(chain.get('links', []))
            print(f"    \"{chain.get('title', '?')}\" ({n_links} links)...", end='', flush=True)
            card_id = store_causal_card(chain, domain_id, conn)
            if card_id:
                print(f" OK")
                total_cards += 1
                total_links += n_links
            else:
                print(f" SKIP (too few links)")

        time.sleep(1)  # rate limit between domains

    if not dry_run:
        conn.commit()

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Chains generated: {total_cards}")
    print(f"  Total links: {total_links}")
    print(f"  Errors: {errors}")
    if not dry_run:
        print(f"  Committed to database")
    else:
        print(f"  [DRY RUN — nothing written]")

    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate causal chain cards')
    parser.add_argument('--domains', nargs='*', help='Domain IDs (default: historical only)')
    parser.add_argument('--dry-run', action='store_true', help='Count facts without generating')
    args = parser.parse_args()
    batch_generate(domain_ids=args.domains, dry_run=args.dry_run)
