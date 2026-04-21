#!/usr/bin/env python3
"""Bootstrap shared_entities from curriculum nodes using LLM extraction.

Reads all curriculum nodes, extracts named entities (places, people, events,
periods) with coordinates, descriptions, Wikipedia URLs, and curriculum links.
Writes results to shared_entities + entity_curriculum_links tables.

Usage:
    python3 bootstrap_entities.py                    # all domains
    python3 bootstrap_entities.py --domain sicily    # one domain
    python3 bootstrap_entities.py --dry-run          # show prompt, don't call LLM
    python3 bootstrap_entities.py --dump             # dump current entities as JSON
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_connection, init_db
from curriculum_db import load_curriculum, list_curricula

try:
    from claude_llm import call_claude
except ImportError:
    call_claude = None


def build_extraction_prompt(domain: dict) -> str:
    """Build prompt to extract entities from curriculum nodes."""
    nodes_block = []
    for n in domain['nodes']:
        if n.get('level', 1) < 2:
            continue  # skip top-level area headers
        dates = ""
        if n.get('date_start') is not None:
            start = n['date_start']
            end = n.get('date_end')
            dates = f" [{start}{'–' + str(end) if end else ''} {'BC' if start < 0 else 'AD'}]"
        nodes_block.append(
            f"  {n['id']}: {n['title']}{dates}\n"
            f"    {n.get('description', '')[:200]}"
        )

    return f"""Extract named entities from this curriculum. Be CONCISE — short descriptions, no verbose fields.

Curriculum: {domain['title']}

Nodes:
{chr(10).join(nodes_block)}

For each entity, output ONE compact JSON line. Fields:
entity_id (slug), name, entity_type (place/person/event/period), description (MAX 20 words),
modern_name (null if same), wikipedia_url, latitude/longitude (places only, null otherwise),
aliases (array), date_start/date_end (int, negative=BCE), node_ids (array of node IDs only)

Extract 40-60 entities. Include every place, person, battle, and period from the nodes.

Return ONLY a JSON array. Keep descriptions SHORT — max 20 words each.

Example: {{"entity_id":"akragas","name":"Akragas","entity_type":"place","description":"Wealthy Greek colony in southwest Sicily, destroyed by Carthage 406 BC.","modern_name":"Agrigento","wikipedia_url":"https://en.wikipedia.org/wiki/Akragas","latitude":37.31,"longitude":13.58,"aliases":["Agrigentum"],"date_start":-580,"date_end":-406,"node_ids":["sicily_his_greeks_versus_carthage_the_struggle_for"]}}"""


def parse_json_response(text: str) -> list | None:
    """Extract JSON array from LLM response."""
    if not text:
        return None
    # Try direct parse
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    # Try extracting complete array
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    # Handle truncated JSON: find last complete object in array
    if text.startswith('['):
        last_complete = text.rfind('},')
        if last_complete > 0:
            truncated = text[:last_complete + 1] + ']'
            try:
                data = json.loads(truncated)
                if isinstance(data, list):
                    print(f'  (parsed truncated response: {len(data)} complete entities)')
                    return data
            except json.JSONDecodeError:
                pass
    return None


def insert_entities(entities: list, domain_id: str, conn) -> tuple[int, int]:
    """Insert entities and links into database. Returns (entities_created, links_created)."""
    entities_created = 0
    links_created = 0

    for e in entities:
        eid = e.get('entity_id', '')
        if not eid:
            continue

        # Upsert entity
        existing = conn.execute(
            'SELECT entity_id FROM shared_entities WHERE entity_id = ?', (eid,)
        ).fetchone()

        if existing:
            conn.execute('''
                UPDATE shared_entities SET
                    name = COALESCE(?, name),
                    description = COALESCE(?, description),
                    entity_type = COALESCE(?, entity_type),
                    modern_name = COALESCE(?, modern_name),
                    wikipedia_url = COALESCE(?, wikipedia_url),
                    latitude = COALESCE(?, latitude),
                    longitude = COALESCE(?, longitude),
                    aliases = COALESCE(?, aliases),
                    date_start = COALESCE(?, date_start),
                    date_end = COALESCE(?, date_end),
                    nexus_score = nexus_score + 1
                WHERE entity_id = ?
            ''', (
                e.get('name'), e.get('description'), e.get('entity_type'),
                e.get('modern_name'), e.get('wikipedia_url'),
                e.get('latitude'), e.get('longitude'),
                json.dumps(e.get('aliases', [])),
                e.get('date_start'), e.get('date_end'),
                eid,
            ))
        else:
            conn.execute('''
                INSERT INTO shared_entities
                (entity_id, name, description, entity_type, modern_name,
                 wikipedia_url, latitude, longitude, aliases, dates,
                 date_start, date_end, nexus_score, location)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', (
                eid, e.get('name', ''), e.get('description'),
                e.get('entity_type'), e.get('modern_name'),
                e.get('wikipedia_url'), e.get('latitude'), e.get('longitude'),
                json.dumps(e.get('aliases', [])),
                e.get('dates', ''),
                e.get('date_start'), e.get('date_end'),
                1, e.get('location', ''),
            ))
            entities_created += 1

        # Insert curriculum links — supports both node_ids (compact) and node_links (verbose)
        node_ids = e.get('node_ids', [])
        node_links = e.get('node_links', [])
        if node_links and not node_ids:
            node_ids = [l.get('node_id', '') for l in node_links if l.get('node_id')]
        for node_id in node_ids:
            if not node_id:
                continue
            lens_title = ''
            lens_emphasis = ''
            for nl in node_links:
                if nl.get('node_id') == node_id:
                    lens_title = nl.get('lens_title', '')
                    lens_emphasis = nl.get('lens_emphasis', '')
                    break
            try:
                conn.execute('''
                    INSERT OR IGNORE INTO entity_curriculum_links
                    (entity_id, domain_id, node_id, lens_title, lens_emphasis)
                    VALUES (?,?,?,?,?)
                ''', (eid, domain_id, node_id, lens_title, lens_emphasis))
                links_created += 1
            except Exception as ex:
                print(f'  Link skip {eid}→{node_id}: {ex}', flush=True)

    return entities_created, links_created


def dump_entities(conn):
    """Dump all entities as JSON to stdout."""
    rows = conn.execute('''
        SELECT e.*, GROUP_CONCAT(l.domain_id || ':' || l.node_id, '|') as links
        FROM shared_entities e
        LEFT JOIN entity_curriculum_links l ON e.entity_id = l.entity_id
        GROUP BY e.entity_id
        ORDER BY e.name
    ''').fetchall()
    entities = []
    for r in rows:
        entities.append({
            'entity_id': r['entity_id'],
            'name': r['name'],
            'entity_type': r['entity_type'],
            'description': r['description'],
            'modern_name': r['modern_name'],
            'wikipedia_url': r['wikipedia_url'],
            'latitude': r['latitude'],
            'longitude': r['longitude'],
            'aliases': json.loads(r['aliases'] or '[]'),
            'date_start': r['date_start'],
            'date_end': r['date_end'],
            'nexus_score': r['nexus_score'],
            'links': r['links'],
        })
    print(json.dumps(entities, indent=2, ensure_ascii=False))
    print(f'\n{len(entities)} entities total', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Bootstrap entities from curriculum nodes')
    parser.add_argument('--domain', help='Only process this domain (partial match)')
    parser.add_argument('--dry-run', action='store_true', help='Show prompt without calling LLM')
    parser.add_argument('--dump', action='store_true', help='Dump current entities as JSON')
    parser.add_argument('--model', default=None, help='LLM model override')
    args = parser.parse_args()

    init_db()
    conn = get_connection()

    if args.dump:
        dump_entities(conn)
        conn.close()
        return

    curricula = list_curricula(conn)
    if not curricula:
        print('No curricula found')
        conn.close()
        return

    for meta in curricula:
        domain_id = meta['id']
        if args.domain and args.domain.lower() not in domain_id.lower():
            continue

        print(f'\n=== {meta["title"]} ({domain_id}) ===', flush=True)
        curriculum = load_curriculum(domain_id, conn)
        if not curriculum:
            print('  Failed to load curriculum')
            continue

        level2_plus = [n for n in curriculum['nodes'] if n.get('level', 1) >= 2]
        print(f'  {len(level2_plus)} nodes (level 2+)', flush=True)

        prompt = build_extraction_prompt(curriculum)

        if args.dry_run:
            print(f'\n--- PROMPT ({len(prompt)} chars) ---')
            print(prompt[:2000])
            print('...')
            continue

        if not call_claude:
            print('  No LLM available (claude_llm not importable)')
            continue

        print(f'  Calling LLM ({len(prompt)} chars)...', flush=True)
        raw = call_claude(prompt, timeout=600, model='sonnet')

        print(f'  Response: {len(raw) if raw else 0} chars', flush=True)
        entities = parse_json_response(raw)
        if not entities:
            print(f'  Failed to parse response')
            if raw:
                print(f'  First 200: {raw[:200]}')
                print(f'  Last 200: {raw[-200:]}')
            continue

        print(f'  Extracted {len(entities)} entities', flush=True)
        created, links = insert_entities(entities, domain_id, conn)
        conn.commit()
        print(f'  Inserted: {created} entities, {links} links', flush=True)

    # Summary
    total = conn.execute('SELECT COUNT(*) FROM shared_entities').fetchone()[0]
    total_links = conn.execute('SELECT COUNT(*) FROM entity_curriculum_links').fetchone()[0]
    print(f'\nTotal: {total} entities, {total_links} links')
    conn.close()


if __name__ == '__main__':
    main()
