#!/usr/bin/env python3
"""Generate synchronic cards — cross-domain contemporaries at a single year.

Synchronic cards test cross-domain awareness: "What was happening in Sicily
when Karl XII fought at Poltava?" Each card has 5-8 positions across 3-5
domains, with 2-3 blanks per appearance based on FSRS state.

Uses Gemini Flash for generation (per LLM calling discipline).
"""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from claude_llm import call_claude_json
from curriculum_db import get_connection


# ── Activation gate: only studied domains ─────────────────────────────────

STUDIED_DOMAIN_THRESHOLD = 5  # ≥5 knowledge_items in domain


# ── Anchor selection ──────────────────────────────────────────────────────

ANCHOR_MIN_REVIEWS = 1     # Review count threshold for anchor
ANCHOR_MIN_STABILITY = 3.0  # Stability threshold (days)
MIN_CROSS_DOMAINS = 3       # Need ≥3 studied domains with entities at anchor year
MIN_POSITIONS = 5           # Need ≥5 positions total across domains
MAX_POSITIONS = 8


# ── Prompt ────────────────────────────────────────────────────────────────

SYNCHRONIC_PROMPT = """You are generating a synchronic card for a knowledge retention system.
A synchronic card shows what was happening across different civilizations/domains at a single moment in history.

Anchor: {anchor_name} ({anchor_dates}) — {anchor_domain}
{anchor_description}

Year: {anchor_year}

Contemporaries by domain (entities active at this time):
{contemporaries_json}

Your task:
1. For each domain, pick the 1-2 MOST NOTABLE entities who had significant activity around year {anchor_year}.
   Prefer entities with a concrete connection to the anchor event/period, not just coincidental overlap.
2. For each position, provide:
   - domain: the domain this entity belongs to
   - entity_name: the entity's name
   - entity_id: the entity_id from the input data (MUST match exactly)
   - label: their role/title/significance AT THIS SPECIFIC TIME (not their whole career)
   - question_text: a question to ask when this position is blanked (DO NOT mention the entity name!)
   - connection: 1 sentence explaining WHY this contemporary matters relative to the anchor.
     This must be a GENUINE historical connection, not just "they happened to live at the same time."
     If no genuine connection exists, say "Contemporaneous but independent" — do NOT fabricate connections.

RULES:
- Keep 5-{max_positions} positions total across 3-5 domains
- The anchor entity is ALWAYS included as the first position (it is never blanked)
- DROP any entity whose only connection is "they were alive at the same time" — only keep meaningful ones
- question_text must NOT mention the answer entity — frame by role, location, or what they did
- Labels should be vivid and specific to this year (e.g., "Emperor, just conquered Egypt" not "Roman emperor")
- Include the anchor's own domain as one of the domains (the anchor itself is always shown)

Return JSON:
{{
  "title": "The World in {anchor_year_display}",
  "subtitle": "When {anchor_short}",
  "positions": [
    {{
      "domain": "domain title",
      "domain_id": "domain_id",
      "entity_name": "entity name",
      "entity_id": "entity_id",
      "label": "their role/title at this time",
      "question_text": "question when blanked",
      "connection": "why this matters relative to the anchor"
    }}
  ]
}}"""


def get_studied_domains(conn) -> dict[str, str]:
    """Return domain_id → domain_title for domains the user has genuinely studied.

    "Studied" means ≥ THRESHOLD knowledge_items AND ≥1 of them has book-sourced or
    voice-capture evidence (not just gap-fill rows). A domain made of only curriculum
    scaffolding is not a real anchor for cross-domain contemporaries.
    """
    rows = conn.execute("""
        SELECT ki.curriculum_domain as domain_id, cd.title, COUNT(*) as cnt
        FROM knowledge_items ki
        JOIN curriculum_domains cd ON cd.id = ki.curriculum_domain
        GROUP BY ki.curriculum_domain
        HAVING cnt >= ?
    """, (STUDIED_DOMAIN_THRESHOLD,)).fetchall()
    out = {}
    for r in rows:
        has_evidence = conn.execute('''
            SELECT 1 FROM knowledge_items ki
            WHERE ki.curriculum_domain = ?
              AND (
                  ki.sources LIKE '%"book_id": "%'
                  OR ki.sources LIKE '%"source": "voice_capture%'
                  OR ki.sources LIKE '%"transcript_id":%'
              )
            LIMIT 1
        ''', (r['domain_id'],)).fetchone()
        if has_evidence:
            out[r['domain_id']] = r['title']
    return out


def get_anchor_candidates(conn, studied_domains: dict) -> list[dict]:
    """Find well-reviewed knowledge items that could anchor synchronic cards.

    Returns items with dates, sorted by stability (strongest first).
    """
    ph = ','.join(['?' for _ in studied_domains])
    rows = conn.execute(f"""
        SELECT ki.curriculum_domain, ki.curriculum_node_id,
               cn.title as node_title, cn.description as node_desc,
               cn.date_start, cn.date_end,
               ki.review_count, ki.stability_days,
               cd.title as domain_title
        FROM knowledge_items ki
        JOIN curriculum_nodes cn ON cn.id = ki.curriculum_node_id
            AND cn.domain_id = ki.curriculum_domain
        JOIN curriculum_domains cd ON cd.id = ki.curriculum_domain
        WHERE ki.review_count >= ?
        AND ki.stability_days >= ?
        AND cn.date_start IS NOT NULL
        AND ki.curriculum_domain IN ({ph})
        ORDER BY ki.stability_days DESC
    """, [ANCHOR_MIN_REVIEWS, ANCHOR_MIN_STABILITY] + list(studied_domains.keys())).fetchall()
    return [dict(r) for r in rows]


def pick_anchor_year(anchor: dict) -> tuple[int, str]:
    """Pick a representative year from an anchor's date range.

    For single-year events, use that year. For ranges, use the midpoint
    or start if the range is very long (probably a period, not an event).
    """
    ds, de = anchor['date_start'], anchor['date_end']
    if ds == de:
        year = ds
    elif (de - ds) <= 5:
        year = ds  # Short event — use start
    elif (de - ds) <= 50:
        year = (ds + de) // 2  # Moderate period — use midpoint
    else:
        year = ds  # Long period — use start (most notable moment)

    # Format display
    if year < 0:
        display = f"{abs(year)} BC"
    else:
        display = f"{year} AD"
    return year, display


def find_contemporaries(anchor_year: int, anchor_domain: str,
                        studied_domains: dict, conn) -> dict[str, list[dict]]:
    """Find entities from other studied domains active at the anchor year.

    Returns {domain_id: [entity_dicts]} for domains other than anchor's.
    """
    other_domains = {k: v for k, v in studied_domains.items() if k != anchor_domain}
    if not other_domains:
        return {}

    ph = ','.join(['?' for _ in other_domains])
    rows = conn.execute(f"""
        SELECT DISTINCT se.entity_id, se.name, se.entity_type,
               se.date_start, se.date_end, se.description,
               se.nexus_score, se.wikidata_qid,
               ecl.domain_id
        FROM shared_entities se
        JOIN entity_curriculum_links ecl ON ecl.entity_id = se.entity_id
        WHERE se.date_start <= ?
        AND se.date_end >= ?
        AND se.date_start IS NOT NULL
        AND ecl.domain_id IN ({ph})
        ORDER BY se.nexus_score DESC
    """, [anchor_year, anchor_year] + list(other_domains.keys())).fetchall()

    # Group by domain
    by_domain: dict[str, list[dict]] = {}
    for r in rows:
        d = r['domain_id']
        if d not in by_domain:
            by_domain[d] = []
        by_domain[d].append({
            'entity_id': r['entity_id'],
            'name': r['name'],
            'entity_type': r['entity_type'],
            'date_start': r['date_start'],
            'date_end': r['date_end'],
            'description': (r['description'] or '')[:200],
            'nexus_score': r['nexus_score'] or 0,
        })

    return by_domain


def find_anchor_entity(anchor: dict, conn) -> dict | None:
    """Find the shared_entity matching the anchor knowledge item's node."""
    # Look for entities linked to this node
    rows = conn.execute("""
        SELECT se.entity_id, se.name, se.entity_type, se.date_start, se.date_end,
               se.description, se.nexus_score
        FROM shared_entities se
        JOIN entity_curriculum_links ecl ON ecl.entity_id = se.entity_id
        WHERE ecl.node_id = ? AND ecl.domain_id = ?
        ORDER BY se.nexus_score DESC
        LIMIT 1
    """, (anchor['curriculum_node_id'], anchor['curriculum_domain'])).fetchall()
    if rows:
        return dict(rows[0])
    return None


def generate_synchronic_card(anchor: dict, anchor_year: int, anchor_year_display: str,
                              contemporaries: dict[str, list[dict]],
                              studied_domains: dict, conn) -> dict | None:
    """Call Gemini Flash to generate a synchronic card."""
    # Build contemporaries JSON grouped by domain
    contemp_text_parts = []
    for domain_id, entities in contemporaries.items():
        domain_title = studied_domains.get(domain_id, domain_id)
        contemp_text_parts.append(f"\n{domain_title}:")
        for e in entities[:5]:  # Limit per domain to keep prompt manageable
            dates = f"{e['date_start']}–{e['date_end']}"
            desc = e['description'][:150] if e['description'] else ''
            contemp_text_parts.append(
                f"  - {e['name']} ({dates}, {e['entity_type']}) [{e['entity_id']}]: {desc}"
            )

    anchor_short = anchor['node_title'].split(':')[0].strip()[:60]

    prompt = SYNCHRONIC_PROMPT.format(
        anchor_name=anchor['node_title'],
        anchor_dates=f"{anchor['date_start']}–{anchor['date_end']}",
        anchor_domain=anchor['domain_title'],
        anchor_description=anchor.get('node_desc', '')[:300],
        anchor_year=anchor_year,
        anchor_year_display=anchor_year_display,
        contemporaries_json='\n'.join(contemp_text_parts),
        anchor_short=anchor_short,
        max_positions=MAX_POSITIONS,
    )

    result = call_claude_json(prompt, timeout=180, model='sonnet')
    if not isinstance(result, dict):
        print("  ERROR: No/invalid response")
        return None
    return result


def store_synchronic_card(card_data: dict, anchor: dict, anchor_year: int,
                           conn) -> str:
    """Store a synchronic card and its positions."""
    card_id = f"sync_{anchor_year}_{uuid.uuid4().hex[:8]}"
    now_ms = int(time.time() * 1000)

    positions = card_data.get('positions', [])
    hooks = [p.get('connection', '') for p in positions if p.get('connection')]

    conn.execute("""
        INSERT INTO structural_cards
        (id, card_type, title, description, domain_id,
         date_anchor, hooks, generation_source, due_at, created_at)
        VALUES (?, 'synchronic', ?, ?, ?, ?, ?, 'auto', ?, datetime('now'))
    """, (
        card_id,
        card_data.get('title', f'The World in {anchor_year}'),
        card_data.get('subtitle', ''),
        anchor['curriculum_domain'],  # Primary domain = anchor's domain
        anchor_year,
        json.dumps(hooks),
        now_ms,
    ))

    for i, p in enumerate(positions):
        pos_id = f"{card_id}_pos{i}"
        # Store domain_id and entity_id in question_variants for the component
        conn.execute("""
            INSERT INTO structural_positions
            (id, card_id, position, entity_id,
             question_text, answer_text, question_variants,
             hook_type, mnemonic, stability_days, due_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PARALLEL', ?, 1.0, ?, datetime('now'))
        """, (
            pos_id,
            card_id,
            i,
            p.get('entity_id', ''),
            p.get('question_text', ''),
            p.get('entity_name', ''),  # answer_text = the entity name
            json.dumps({
                'domain': p.get('domain', ''),
                'domain_id': p.get('domain_id', ''),
                'label': p.get('label', ''),
                'connection': p.get('connection', ''),
            }),
            p.get('connection', ''),  # mnemonic = the connection text
            now_ms,
        ))

    return card_id


def already_has_card_for_year(anchor_year: int, conn) -> bool:
    """Check if a synchronic card already exists for this year."""
    row = conn.execute(
        "SELECT COUNT(*) FROM structural_cards WHERE card_type='synchronic' AND date_anchor=?",
        (anchor_year,),
    ).fetchone()
    return row[0] > 0


def batch_generate(max_cards: int = 10, dry_run: bool = False):
    """Generate synchronic cards from the user's strongest temporal anchors."""
    conn = get_connection()

    # 1. Find studied domains
    studied = get_studied_domains(conn)
    print(f"Studied domains ({len(studied)}):")
    for did, title in studied.items():
        print(f"  {title}")

    if len(studied) < 2:
        print("\nNeed ≥2 studied domains for synchronic cards. Aborting.")
        conn.close()
        return

    # 2. Find anchor candidates
    anchors = get_anchor_candidates(conn, studied)
    print(f"\nAnchor candidates: {len(anchors)}")

    # 3. For each anchor, check cross-domain coverage and generate
    generated = 0
    seen_years = set()

    for anchor in anchors:
        if generated >= max_cards:
            break

        year, display = pick_anchor_year(anchor)

        # Deduplicate: skip years too close to already-generated cards
        if any(abs(year - sy) < 10 for sy in seen_years):
            continue
        if already_has_card_for_year(year, conn):
            continue

        # Find contemporaries
        contemporaries = find_contemporaries(year, anchor['curriculum_domain'], studied, conn)

        # Filter: need ≥ MIN_CROSS_DOMAINS domains with entities
        if len(contemporaries) < MIN_CROSS_DOMAINS - 1:  # -1 because anchor's domain excluded
            continue

        # Count total available positions (including anchor itself)
        total_positions = 1 + sum(min(len(ents), 2) for ents in contemporaries.values())
        if total_positions < MIN_POSITIONS:
            continue

        print(f"\n{'='*60}")
        print(f"Anchor: {anchor['node_title']} (year {display})")
        print(f"  Domain: {anchor['domain_title']}")
        print(f"  Stability: {anchor['stability_days']:.1f}d, Reviews: {anchor['review_count']}")
        print(f"  Cross-domain coverage: {len(contemporaries)} domains, {total_positions} positions")
        for did, ents in contemporaries.items():
            names = ', '.join(e['name'] for e in ents[:3])
            print(f"    {studied[did][:40]:40s} → {names}")

        if dry_run:
            print(f"  [DRY RUN]")
            seen_years.add(year)
            generated += 1
            continue

        # Generate via Gemini Flash
        card_data = generate_synchronic_card(
            anchor, year, display, contemporaries, studied, conn,
        )
        if not card_data:
            print(f"  ERROR: Generation failed")
            continue

        positions = card_data.get('positions', [])
        if len(positions) < 4:
            print(f"  SKIP: Only {len(positions)} positions (need ≥4)")
            continue

        card_id = store_synchronic_card(card_data, anchor, year, conn)
        conn.commit()

        print(f"  OK: {card_data.get('title', '?')} — {len(positions)} positions")
        for p in positions:
            print(f"    [{p.get('domain', '?')[:25]:25s}] {p.get('entity_name', '?'):30s} "
                  f"— {p.get('connection', '')[:60]}")

        seen_years.add(year)
        generated += 1
        time.sleep(1)  # Rate limit

    print(f"\n{'='*60}")
    print(f"SUMMARY: Generated {generated} synchronic cards")
    if not dry_run and generated > 0:
        print("Committed to database")
    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Generate synchronic cards')
    parser.add_argument('--max-cards', type=int, default=10, help='Maximum cards to generate')
    parser.add_argument('--dry-run', action='store_true', help='Scan without generating')
    args = parser.parse_args()

    batch_generate(max_cards=args.max_cards, dry_run=args.dry_run)
