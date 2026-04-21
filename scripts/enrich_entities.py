#!/usr/bin/env python3
"""Entity enrichment: extract all named entities from card content and add to shared_entities.

Scans all completed microlearning cards and knowledge_item rich answers,
extracts entities via Gemini Flash, deduplicates against existing DB, and
inserts new ones. Run as a batch script after deploy.

Usage:
    cd /opt/petrarca/scripts && python3 enrich_entities.py [--dry-run]
"""
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Load env vars (Gemini API key etc.)
for env_file in [Path('/opt/petrarca/.env'), Path(__file__).parent.parent / '.env']:
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, val = line.partition('=')
                # Strip quotes from values
                val = val.strip().strip('"').strip("'")
                os.environ[key.strip()] = val
        break

from db import get_connection

# Generic entities to skip (matches curriculum_db._GENERIC_ENTITIES)
GENERIC_ENTITIES = {
    'italy', 'greece', 'sicily', 'venice', 'spain', 'france', 'germany', 'england',
    'egypt', 'turkey', 'syria', 'india', 'china', 'europe', 'africa', 'asia',
    'north africa', 'central asia', 'russia', 'united states', 'tunisia',
    'gaul', 'persia', 'bulgaria', 'gaza', 'kiev', 'rome', 'athens', 'jerusalem',
    'constantinople', 'the mediterranean', 'mediterranean',
}

EXTRACTION_PROMPT = """Extract ALL named entities from this text. Include every:
- Person (historical figures, authors, rulers, generals, scholars)
- Place (cities, regions, islands, rivers, mountains, specific buildings/temples/churches)
- Event (battles, treaties, sieges, conquests, revolts)
- Period (dynasties, eras, ages)

For each entity, provide:
- "name": The most formal/complete canonical name (e.g. "Julius Caesar" not "Caesar", "Diodorus Siculus" not "Diodorus")
- "type": One of: person, place, event, period, concept
- "dates": Approximate dates if mentioned or inferable (e.g. "480 BC", "1st century AD", "1693")

IMPORTANT:
- Use the MOST COMPLETE form of names (e.g., "Gelon of Syracuse" not just "Gelon")
- Include authors referenced as sources (Thucydides, Diodorus Siculus, Polybius, etc.)
- Include specific buildings, temples, churches by name
- Do NOT include generic terms like "the Greeks", "the Romans", "the Arabs"
- Do NOT include modern country names (Italy, France, etc.)

Output JSON array only, e.g.: [{{"name": "Diodorus Siculus", "type": "person", "dates": "1st century BC"}}]

TEXT:
{text}"""


def extract_entities_batch(texts: list[str]) -> list[dict]:
    """Extract entities from a batch of texts via Claude Sonnet."""
    combined = '\n\n---\n\n'.join(t[:2000] for t in texts)
    if not combined.strip():
        return []

    try:
        from claude_llm import call_claude_json
        entities = call_claude_json(
            EXTRACTION_PROMPT.format(text=combined[:8000]),
            timeout=180,
            model='sonnet',
        )
        if isinstance(entities, list):
            return entities
        if entities is None:
            print('  [warn] empty response from LLM')
        else:
            print(f'  [warn] unexpected response type: {type(entities)}')
    except Exception as e:
        import traceback
        print(f'  [warn] extraction failed: {e}')
        traceback.print_exc()
    return []


def normalize_entity_id(name: str) -> str:
    """Convert entity name to a canonical ID."""
    return re.sub(r'[^a-z0-9_]', '_', name.lower().strip()).strip('_')


def main():
    dry_run = '--dry-run' in sys.argv
    conn = get_connection()

    # Load existing entities for dedup
    existing = {}
    for row in conn.execute('SELECT entity_id, name, aliases FROM shared_entities').fetchall():
        existing[row['entity_id']] = row['name']
        # Also index by lowercase name and aliases
        existing[row['name'].lower()] = row['entity_id']
        try:
            for alias in json.loads(row['aliases'] or '[]'):
                existing[alias.lower()] = row['entity_id']
        except Exception:
            pass

    print(f'Existing entities: {len(set(existing.values()))}')

    # Collect text from all completed ML cards
    texts = []
    card_rows = conn.execute("""
        SELECT id, content, title FROM microlearning_cards
        WHERE status = 'completed' AND content IS NOT NULL AND content != ''
    """).fetchall()
    for row in card_rows:
        text = f"{row['title'] or ''}\n{row['content']}"
        if len(text.strip()) > 50:
            texts.append(text)
    print(f'ML card texts: {len(texts)}')

    # Also collect rich_answer from knowledge_items
    ki_rows = conn.execute("""
        SELECT id, cached_question FROM knowledge_items
        WHERE cached_question IS NOT NULL AND cached_question != ''
    """).fetchall()
    for row in ki_rows:
        try:
            cq = json.loads(row['cached_question'])
            ra = cq.get('rich_answer', '')
            q = cq.get('question', '')
            text = f"{q}\n{ra}"
            if len(text.strip()) > 50:
                texts.append(text)
        except Exception:
            pass
    print(f'Total texts to process: {len(texts)}')

    # Process in batches
    BATCH_SIZE = 15
    all_extracted = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        print(f'Processing batch {i // BATCH_SIZE + 1}/{(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE}...')
        entities = extract_entities_batch(batch)
        all_extracted.extend(entities)
        if i + BATCH_SIZE < len(texts):
            time.sleep(1)  # Rate limit

    print(f'\nTotal entities extracted: {len(all_extracted)}')

    # Deduplicate and count references
    entity_counts = {}  # normalized_name -> {name, type, dates, count}
    for e in all_extracted:
        name = (e.get('name') or '').strip()
        if not name or len(name) < 3:
            continue
        if name.lower() in GENERIC_ENTITIES:
            continue
        norm = name.lower()
        if norm in entity_counts:
            entity_counts[norm]['count'] += 1
            # Prefer longer/more formal name
            if len(name) > len(entity_counts[norm]['name']):
                entity_counts[norm]['name'] = name
        else:
            entity_counts[norm] = {
                'name': name,
                'type': e.get('type', 'concept'),
                'dates': e.get('dates', ''),
                'count': 1,
            }

    print(f'Unique entities after dedup: {len(entity_counts)}')

    # Filter: require 2+ references (reduces noise)
    candidates = {k: v for k, v in entity_counts.items() if v['count'] >= 2}
    print(f'Entities with 2+ references: {len(candidates)}')

    # Check which are new vs existing
    new_entities = []
    updated_aliases = []
    for norm, info in candidates.items():
        eid = normalize_entity_id(info['name'])
        if eid in existing or norm in existing:
            # Already exists — check if we should add an alias
            existing_eid = existing.get(eid) or existing.get(norm)
            if isinstance(existing_eid, str) and norm not in existing:
                updated_aliases.append((existing_eid, info['name']))
            continue
        new_entities.append({
            'entity_id': eid,
            'name': info['name'],
            'entity_type': info['type'],
            'dates': info['dates'],
            'count': info['count'],
        })

    print(f'\nNew entities to add: {len(new_entities)}')
    print(f'Aliases to add: {len(updated_aliases)}')

    if dry_run:
        print('\n--- DRY RUN — would add: ---')
        for e in sorted(new_entities, key=lambda x: -x['count'])[:30]:
            print(f"  [{e['count']}x] {e['name']} ({e['entity_type']}) {e['dates']}")
        if updated_aliases:
            print('\n--- Would add aliases: ---')
            for eid, alias in updated_aliases[:10]:
                print(f'  {eid} += {alias}')
        conn.close()
        return

    # Insert new entities
    inserted = 0
    for e in new_entities:
        try:
            conn.execute('''
                INSERT OR IGNORE INTO shared_entities
                (entity_id, name, entity_type, dates, nexus_score, aliases)
                VALUES (?,?,?,?,?,?)
            ''', (e['entity_id'], e['name'], e['entity_type'], e['dates'], 1, '[]'))
            inserted += 1
        except Exception as ex:
            print(f'  [warn] insert failed for {e["name"]}: {ex}')

    # Add aliases
    alias_added = 0
    for eid, alias in updated_aliases:
        try:
            row = conn.execute('SELECT aliases FROM shared_entities WHERE entity_id=?', (eid,)).fetchone()
            if row:
                aliases = json.loads(row['aliases'] or '[]')
                if alias not in aliases:
                    aliases.append(alias)
                    conn.execute('UPDATE shared_entities SET aliases=? WHERE entity_id=?',
                                 (json.dumps(aliases), eid))
                    alias_added += 1
        except Exception:
            pass

    conn.commit()
    conn.close()

    print(f'\nDone! Inserted {inserted} new entities, added {alias_added} aliases.')


if __name__ == '__main__':
    main()
