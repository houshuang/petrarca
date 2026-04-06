"""Curriculum system backed by SQLite.

Drop-in replacement for curriculum.py — same public API, but reads/writes
petrarca.db instead of JSON files in data/curricula/.

Imports db.get_connection() for all database access. All functions that
modify state take an optional `conn` parameter; if omitted, they open
and close their own connection.
"""

import hashlib
import json
import math
import os
import random
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from db import get_connection, init_db

try:
    from claude_llm import call_claude_json
except ImportError:
    call_claude_json = None

# ── LLM helpers (unchanged from curriculum.py) ──────────────────────────────

def _call_opus(prompt: str, max_tokens: int = 32768, timeout: int = 300) -> str | None:
    anthropic_key = os.environ.get('ANTHROPIC_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key, timeout=600.0)
            with client.messages.stream(
                model='claude-opus-4-6', max_tokens=max_tokens,
                messages=[{'role': 'user', 'content': prompt}],
            ) as stream:
                return stream.get_final_text()
        except Exception as e:
            print(f'[curriculum] Anthropic SDK failed: {e}', flush=True)
    try:
        cmd = ['claude', '-p', '--tools', '', '--output-format', 'json',
               '--model', 'opus', '--no-session-persistence']
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout.strip():
            resp = json.loads(proc.stdout)
            if not resp.get('is_error'):
                return resp.get('result', '')
    except Exception as e:
        print(f'[curriculum] claude CLI failed: {e}', flush=True)
    return None


# ── ID helpers ───────────────────────────────────────────────────────────────

def make_node_id(domain_id: str, title: str) -> str:
    slug = title.lower().strip()
    slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
    slug = '_'.join(slug.split()[:6])
    return f"{domain_id[:10]}_{slug}"


def make_domain_id(title: str) -> str:
    slug = title.lower().strip()
    slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
    slug = '_'.join(slug.split()[:8])
    return slug


# ═════════════════════════════════════════════════════════════════════════════
# CURRICULUM CRUD
# ═════════════════════════════════════════════════════════════════════════════

def load_curriculum(domain_id: str, conn=None) -> dict | None:
    """Load a curriculum by ID. Returns dict with {id, title, description, depth, nodes, ...}."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        row = conn.execute(
            'SELECT id, title, description, depth, generated_at, generated_by, node_count '
            'FROM curriculum_domains WHERE id = ?', (domain_id,)
        ).fetchone()
        if not row:
            return None

        nodes = conn.execute(
            'SELECT id, title, description, parent_id, level, obscurity, bloom_floor, '
            'knowledge_type, date_start, date_end '
            'FROM curriculum_nodes WHERE domain_id = ? ORDER BY level, title',
            (domain_id,)
        ).fetchall()

        prereqs = conn.execute(
            'SELECT node_id, prerequisite_id, strength '
            'FROM curriculum_prerequisites WHERE domain_id = ?',
            (domain_id,)
        ).fetchall()
        prereq_map: dict[str, list[str]] = {}
        for p in prereqs:
            prereq_map.setdefault(p['node_id'], []).append(p['prerequisite_id'])

        node_list = []
        for n in nodes:
            node_list.append({
                'id': n['id'],
                'title': n['title'],
                'description': n['description'],
                'parent_id': n['parent_id'],
                'level': n['level'],
                'obscurity': n['obscurity'],
                'bloom_floor': n['bloom_floor'],
                'knowledge_type': n['knowledge_type'] or 'core',
                'date_start': n['date_start'],
                'date_end': n['date_end'],
                'prerequisites': prereq_map.get(n['id'], []),
            })

        return {
            'id': row['id'],
            'title': row['title'],
            'description': row['description'],
            'depth': row['depth'],
            'generated_at': row['generated_at'],
            'generated_by': row['generated_by'],
            'node_count': row['node_count'],
            'nodes': node_list,
        }
    finally:
        if own:
            conn.close()


def list_curricula(conn=None) -> list[dict]:
    """List all available curricula (metadata only)."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        rows = conn.execute(
            'SELECT id, title, depth, node_count, generated_at FROM curriculum_domains ORDER BY title'
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE STATES
# ═════════════════════════════════════════════════════════════════════════════

def load_knowledge_states(domain_id: str, conn=None) -> dict[str, dict]:
    """Load knowledge states for a domain. Returns {node_id: state_dict}."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        rows = conn.execute(
            'SELECT node_id, knowledge, interest, confidence, highest_layer, '
            'source_summary, last_assessed, last_evidence '
            'FROM knowledge_states WHERE domain_id = ?',
            (domain_id,)
        ).fetchall()
        result = {}
        for r in rows:
            sources = r['source_summary']
            if isinstance(sources, str):
                try:
                    sources = json.loads(sources)
                except (json.JSONDecodeError, TypeError):
                    sources = []
            result[r['node_id']] = {
                'knowledge': r['knowledge'],
                'interest': r['interest'],
                'confidence': r['confidence'],
                'highest_layer': r['highest_layer'],
                'sources': sources,
                'last_assessed': r['last_assessed'],
                'last_evidence': r['last_evidence'],
            }
        return result
    finally:
        if own:
            conn.close()


def update_knowledge(domain_id: str, node_id: str,
                     knowledge: str | None = None,
                     interest: str | None = None,
                     confidence: float | None = None,
                     source: str | None = None,
                     highest_layer: int | None = None,
                     conn=None) -> dict:
    """Update knowledge state for a single node. Creates if not exists."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        now = datetime.now().isoformat()
        existing = conn.execute(
            'SELECT knowledge, interest, confidence, highest_layer, source_summary '
            'FROM knowledge_states WHERE domain_id = ? AND node_id = ?',
            (domain_id, node_id)
        ).fetchone()

        if existing:
            # Knowledge level only upgrades, never downgrades
            KNOWLEDGE_ORDER = {'unknown': 0, 'mentioned': 1, 'engaged': 2, 'anchored': 3}
            if knowledge:
                new_level = KNOWLEDGE_ORDER.get(knowledge, 0)
                old_level = KNOWLEDGE_ORDER.get(existing['knowledge'], 0)
                cur_knowledge = knowledge if new_level >= old_level else existing['knowledge']
            else:
                cur_knowledge = existing['knowledge']
            cur_interest = interest or existing['interest']
            # Confidence: take the higher value
            cur_confidence = max(confidence or 0.0, existing['confidence'] or 0.0)
            cur_layer = highest_layer if highest_layer is not None else existing['highest_layer']
            sources = existing['source_summary']
            if isinstance(sources, str):
                try:
                    sources = json.loads(sources)
                except (json.JSONDecodeError, TypeError):
                    sources = []
            if source and source not in sources:
                sources.append(source)

            conn.execute(
                '''UPDATE knowledge_states
                   SET knowledge=?, interest=?, confidence=?, highest_layer=?,
                       source_summary=?, last_assessed=?, last_evidence=?
                   WHERE domain_id=? AND node_id=?''',
                (cur_knowledge, cur_interest, cur_confidence, cur_layer,
                 json.dumps(sources), now, now, domain_id, node_id)
            )
            state = {'knowledge': cur_knowledge, 'interest': cur_interest,
                     'confidence': cur_confidence, 'highest_layer': cur_layer,
                     'sources': sources, 'last_assessed': now}
        else:
            sources = [source] if source else []
            k = knowledge or 'unknown'
            i = interest or 'none'
            c = confidence if confidence is not None else 0.0
            layer = highest_layer if highest_layer is not None else 0
            conn.execute(
                '''INSERT INTO knowledge_states
                   (domain_id, node_id, knowledge, interest, confidence, highest_layer,
                    source_summary, last_assessed, last_evidence)
                   VALUES (?,?,?,?,?,?,?,?,?)''',
                (domain_id, node_id, k, i, c, layer, json.dumps(sources), now, now)
            )
            state = {'knowledge': k, 'interest': i, 'confidence': c,
                     'highest_layer': layer, 'sources': sources, 'last_assessed': now}

        if own:
            conn.commit()
        return state
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# BOOK MAPPING
# ═════════════════════════════════════════════════════════════════════════════

BOOK_MAPPING_PROMPT = """You are mapping a book's content against a curriculum to determine which topics the book covers.

BOOK:
Title: {title}
Author: {author}
Topics: {topics}
Chapters: {chapters}
Thesis: {thesis}
Key terms: {key_terms}

CURRICULUM NODES (the topics we want to map against):
{curriculum_nodes}

For each curriculum node that this book covers, output a JSON object with:
- "node_title": exact title from the curriculum
- "coverage": "surface" (mentions it briefly), "moderate" (covers it meaningfully), or "deep" (substantial coverage)
- "evidence": Brief explanation of why you think this book covers this topic

Only include nodes the book actually covers — don't guess. If uncertain, use "surface" coverage.

Output as a JSON array. No markdown, just the JSON array."""


def map_book_to_curriculum(book_id: str, domain_id: str, conn=None) -> list[dict] | None:
    """Map a book's content against a curriculum. Returns list of mappings."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        curriculum = load_curriculum(domain_id, conn=conn)
        if not curriculum:
            return None

        # Load book from DB
        book_row = conn.execute(
            'SELECT id, title, author, topics, chapters, significance FROM physical_books WHERE id = ?',
            (book_id,)
        ).fetchone()
        if not book_row:
            return None

        book_title = book_row['title']
        book_author = book_row['author']
        book_topics = book_row['topics']
        if isinstance(book_topics, str):
            try:
                book_topics = json.loads(book_topics)
            except (json.JSONDecodeError, TypeError):
                book_topics = []
        chapters_raw = book_row['chapters']
        if isinstance(chapters_raw, str):
            try:
                chapters_raw = json.loads(chapters_raw)
            except (json.JSONDecodeError, TypeError):
                chapters_raw = []
        book_significance = book_row['significance'] or 'read'

        # Format curriculum nodes for prompt
        node_lines = []
        title_to_id = {}
        for node in curriculum['nodes']:
            indent = '  ' * (node['level'] - 1)
            node_lines.append(f"{indent}- {node['title']}: {node['description'][:100]}")
            title_to_id[node['title']] = node['id']

        chapters_text = ', '.join(
            f"Ch {ch.get('number', '?')}: {ch.get('title', '?')}"
            for ch in chapters_raw
        ) or 'No chapters available'

        # Look for book research
        from pathlib import Path as _Path
        research_dir = _Path(os.environ.get('BOOK_RESEARCH_DIR',
                                            '/opt/petrarca/scripts/data/book_research'))
        research_path = research_dir / f'{book_id}.json'
        thesis = ''
        key_terms = ''
        if research_path.exists():
            research = json.loads(research_path.read_text())
            thesis = research.get('thesis', '')
            key_terms = ', '.join(t.get('term', '') for t in research.get('key_terms', [])[:20])

        if not call_claude_json:
            print('[curriculum_db] No LLM available for book mapping', flush=True)
            return None

        prompt = BOOK_MAPPING_PROMPT.format(
            title=book_title, author=book_author,
            topics=', '.join(book_topics), chapters=chapters_text,
            thesis=thesis or 'Not available', key_terms=key_terms or 'Not available',
            curriculum_nodes='\n'.join(node_lines),
        )

        mappings_raw = call_claude_json(prompt, timeout=180)
        if not mappings_raw:
            return None
        if not isinstance(mappings_raw, list):
            return None

        # Confidence based on significance × coverage
        confidence_map = {
            ('essential', 'deep'): 0.9, ('essential', 'moderate'): 0.8, ('essential', 'surface'): 0.6,
            ('read', 'deep'): 0.8, ('read', 'moderate'): 0.65, ('read', 'surface'): 0.45,
            ('skimmed', 'deep'): 0.6, ('skimmed', 'moderate'): 0.4, ('skimmed', 'surface'): 0.25,
        }

        mappings = []
        for m in mappings_raw:
            node_title = m.get('node_title', '')
            if node_title not in title_to_id:
                continue
            node_id = title_to_id[node_title]
            coverage = m.get('coverage', 'surface')
            confidence = confidence_map.get((book_significance, coverage), 0.5)

            # Insert mapping
            conn.execute(
                'INSERT OR REPLACE INTO book_curriculum_mappings '
                '(book_id, domain_id, node_id, coverage, inferred_from) VALUES (?,?,?,?,?)',
                (book_id, domain_id, node_id, coverage, 'llm_inference')
            )

            # Update knowledge state
            update_knowledge(domain_id, node_id,
                             knowledge='mentioned', confidence=confidence,
                             source=f'book:{book_id}', conn=conn)

            mappings.append({
                'node_id': node_id, 'node_title': node_title,
                'coverage': coverage, 'confidence': confidence,
            })

        if own:
            conn.commit()
        print(f"Mapped book '{book_title}' → {len(mappings)} curriculum nodes", flush=True)
        return mappings
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# BOOK CURRICULUM CONTEXT (for client)
# ═════════════════════════════════════════════════════════════════════════════

def get_book_curriculum_context(book_id: str, conn=None) -> dict:
    """Get all curriculum context for a book."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        # Find all domains this book maps to
        domain_rows = conn.execute(
            'SELECT DISTINCT domain_id FROM book_curriculum_mappings WHERE book_id = ?',
            (book_id,)
        ).fetchall()

        domains = []
        for dr in domain_rows:
            domain_id = dr['domain_id']

            # Get domain info
            domain_info = conn.execute(
                'SELECT title, node_count FROM curriculum_domains WHERE id = ?',
                (domain_id,)
            ).fetchone()
            if not domain_info:
                continue

            # Get this book's mappings with node info and knowledge state
            mappings = conn.execute(
                '''SELECT bcm.node_id, cn.title as node_title, bcm.coverage,
                          cn.description, ks.knowledge, ks.interest, ks.confidence
                   FROM book_curriculum_mappings bcm
                   JOIN curriculum_nodes cn ON cn.domain_id = bcm.domain_id AND cn.id = bcm.node_id
                   LEFT JOIN knowledge_states ks ON ks.domain_id = bcm.domain_id AND ks.node_id = bcm.node_id
                   WHERE bcm.book_id = ? AND bcm.domain_id = ?''',
                (book_id, domain_id)
            ).fetchall()

            annotated = [{
                'node_id': m['node_id'], 'node_title': m['node_title'],
                'coverage': m['coverage'], 'description': m['description'] or '',
                'knowledge': m['knowledge'] or 'unknown',
                'interest': m['interest'] or 'none',
                'confidence': m['confidence'] or 0.0,
            } for m in mappings]

            # Cross-book connections: other books mapping to same nodes
            my_node_ids = {m['node_id'] for m in mappings}
            cross_books = []
            if my_node_ids:
                placeholders = ','.join('?' * len(my_node_ids))
                other_mappings = conn.execute(
                    f'''SELECT bcm.node_id, cn.title as node_title, bcm.book_id as other_book_id,
                               bcm.coverage as other_coverage, pb.title as other_book_title
                        FROM book_curriculum_mappings bcm
                        JOIN curriculum_nodes cn ON cn.domain_id = bcm.domain_id AND cn.id = bcm.node_id
                        LEFT JOIN physical_books pb ON pb.id = bcm.book_id
                        WHERE bcm.domain_id = ? AND bcm.book_id != ?
                              AND bcm.node_id IN ({placeholders})''',
                    [domain_id, book_id] + list(my_node_ids)
                ).fetchall()
                cross_books = [{
                    'node_id': om['node_id'], 'node_title': om['node_title'],
                    'other_book_id': om['other_book_id'],
                    'other_book_title': om['other_book_title'] or om['other_book_id'],
                    'other_coverage': om['other_coverage'],
                } for om in other_mappings]

            domains.append({
                'domain_id': domain_id,
                'domain_title': domain_info['title'],
                'node_count': domain_info['node_count'],
                'mappings': annotated,
                'cross_book_connections': cross_books,
            })

        return {'domains': domains}
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# COVERAGE / GAP ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════

def get_coverage_report(domain_id: str, conn=None) -> dict | None:
    """Generate a coverage report for a curriculum domain."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        curriculum = load_curriculum(domain_id, conn=conn)
        if not curriculum:
            return None
        states = load_knowledge_states(domain_id, conn=conn)
        nodes = curriculum['nodes']

        by_state = {'anchored': [], 'engaged': [], 'mentioned': [], 'unknown': []}
        curious = []
        core_interest = []

        for node in nodes:
            state = states.get(node['id'], {})
            knowledge = state.get('knowledge', 'unknown')
            interest = state.get('interest', 'none')
            summary = {
                'id': node['id'], 'title': node['title'], 'level': node['level'],
                'knowledge': knowledge, 'interest': interest,
                'confidence': state.get('confidence', 0.0),
            }
            by_state.get(knowledge, by_state['unknown']).append(summary)
            if interest == 'curious':
                curious.append(summary)
            elif interest == 'core':
                core_interest.append(summary)

        # Ready to learn: unknown nodes with all prerequisites met
        known_ids = {s['id'] for bucket in ('anchored', 'engaged', 'mentioned') for s in by_state[bucket]}
        ready_to_learn = []
        for node in nodes:
            if states.get(node['id'], {}).get('knowledge', 'unknown') != 'unknown':
                continue
            prereqs = node.get('prerequisites', [])
            if all(p in known_ids for p in prereqs):
                ready_to_learn.append({'id': node['id'], 'title': node['title'], 'level': node['level']})

        total = len(nodes)
        covered = total - len(by_state['unknown'])

        return {
            'domain_id': domain_id, 'title': curriculum['title'],
            'total_nodes': total, 'covered_nodes': covered,
            'coverage_percent': round(100 * covered / total) if total > 0 else 0,
            'by_state': {k: len(v) for k, v in by_state.items()},
            'anchored': by_state['anchored'], 'engaged': by_state['engaged'],
            'mentioned': by_state['mentioned'], 'unknown': by_state['unknown'],
            'curious': curious, 'core_interest': core_interest,
            'ready_to_learn': ready_to_learn[:20],
        }
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# RETRIEVAL QUESTIONS — ARCHIVED
# Table still exists with 19 Sicily questions but is no longer read/written.
# Review stream now uses knowledge_items exclusively.
# ═════════════════════════════════════════════════════════════════════════════


def get_timeline(domain_id: str, conn=None) -> list[dict]:
    """Get timeline entries for a domain, sorted chronologically."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        rows = conn.execute(
            'SELECT year, label, detail, node_id FROM timeline_entries '
            'WHERE domain_id = ? ORDER BY year',
            (domain_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# REVIEW SESSION (replaces JSON-based resurfacing review)
# ═════════════════════════════════════════════════════════════════════════════

REVIEW_INTERVALS = [1, 3, 7, 14, 30, 60, 120]
QUESTIONS_PER_SESSION = 8
ORDERING_PER_SESSION = 2
MAX_INTRO_CARDS = 3


def _load_entity_knowledge(conn) -> dict[str, str]:
    """Load best knowledge state per entity (max across linked curriculum nodes).

    Returns {entity_id: knowledge_level} where knowledge_level is one of:
    unknown, mentioned, engaged, anchored.
    """
    rows = conn.execute('''
        SELECT ecl.entity_id, COALESCE(ks.knowledge, 'unknown') as knowledge
        FROM entity_curriculum_links ecl
        LEFT JOIN knowledge_states ks
          ON ks.domain_id = ecl.domain_id AND ks.node_id = ecl.node_id
    ''').fetchall()

    rank = {'unknown': 0, 'mentioned': 1, 'engaged': 2, 'anchored': 3}
    best: dict[str, str] = {}
    for r in rows:
        eid = r['entity_id']
        knowledge = r['knowledge']
        if rank.get(knowledge, 0) > rank.get(best.get(eid, 'unknown'), 0):
            best[eid] = knowledge
    return best


def _load_entity_details_for_intros(entity_ids: list[str], conn) -> dict[str, dict]:
    """Load full entity details for building intro cards."""
    if not entity_ids:
        return {}
    placeholders = ','.join('?' * len(entity_ids))
    rows = conn.execute(f'''
        SELECT entity_id, name, description, entity_type, modern_name,
               wikipedia_url, latitude, longitude, date_start, date_end, aliases
        FROM shared_entities WHERE entity_id IN ({placeholders})
    ''', entity_ids).fetchall()
    return {r['entity_id']: dict(r) for r in rows}


def _build_entity_intro_items(items: list[dict], entity_knowledge: dict[str, str],
                              conn) -> list[dict]:
    """Build entity intro cards for unknown entities referenced in session items.

    Returns a list of (intro_item, before_index) tuples merged into a flat list
    of intro items to be inserted before the session items.
    """
    # Collect unknown entities and which item first references them
    unknown_entities: dict[str, int] = {}  # entity_id -> first item index
    for i, item in enumerate(items):
        spans_by_field = item.get('entity_spans', {})
        for field_spans in spans_by_field.values():
            for span in field_spans:
                eid = span['entity_id']
                if eid in unknown_entities:
                    continue
                knowledge = entity_knowledge.get(eid, 'unknown')
                if knowledge == 'unknown':
                    unknown_entities[eid] = i

    if not unknown_entities:
        return items

    # Cap and load details for the most relevant unknowns
    # Prioritize entities that appear earliest in the session
    sorted_unknowns = sorted(unknown_entities.items(), key=lambda x: x[1])[:MAX_INTRO_CARDS]
    entity_ids = [eid for eid, _ in sorted_unknowns]
    details = _load_entity_details_for_intros(entity_ids, conn)

    # Build intro items and interleave before their first dependent question
    intro_items: list[tuple[dict, int]] = []
    for eid, before_idx in sorted_unknowns:
        d = details.get(eid)
        if not d or not d.get('description'):
            continue
        intro_items.append(({
            'type': 'entity_intro',
            'entity_id': eid,
            'entity_name': d['name'],
            'entity_type': d.get('entity_type'),
            'modern_name': d.get('modern_name'),
            'description': d.get('description'),
            'latitude': d.get('latitude'),
            'longitude': d.get('longitude'),
            'wikipedia_url': d.get('wikipedia_url'),
            'date_start': d.get('date_start'),
            'date_end': d.get('date_end'),
        }, before_idx))

    if not intro_items:
        return items

    # Merge: insert intros before their target index (adjust for prior insertions)
    result = []
    intro_by_idx: dict[int, list[dict]] = {}
    for intro, idx in intro_items:
        intro_by_idx.setdefault(idx, []).append(intro)
    for i, item in enumerate(items):
        for intro in intro_by_idx.get(i, []):
            result.append(intro)
        result.append(item)
    return result


MAX_NEXUS_CARDS = 2  # max nexus cards per review batch


def _insert_nexus_cards(items: list[dict], conn) -> list[dict]:
    """Insert cross-curriculum perspective cards for high-nexus entities.

    When a review card references an entity that appears in 3+ curricula,
    and the learner knows it from a different domain than the card's domain,
    insert a nexus card that surfaces the alternative perspective.
    """
    # Collect entity_ids referenced in review cards and their domains
    card_entities: list[tuple[int, str, str]] = []  # (index, entity_id, card_domain)
    for i, item in enumerate(items):
        if item.get('type') not in ('review', 'question'):
            continue
        domain_id = item.get('domain_id', '')
        entities = item.get('entities', [])
        for eid in entities[:3]:
            if isinstance(eid, str):
                card_entities.append((i, eid, domain_id))

    if not card_entities:
        return items

    # Find high-nexus entities (nexus_score >= 3)
    unique_eids = list({eid for _, eid, _ in card_entities})
    if not unique_eids:
        return items

    placeholders = ','.join('?' * len(unique_eids))
    nexus_rows = conn.execute(f"""
        SELECT entity_id, name, nexus_score
        FROM shared_entities
        WHERE entity_id IN ({placeholders}) AND nexus_score >= 3
    """, unique_eids).fetchall()
    nexus_map = {r['entity_id']: r for r in nexus_rows}

    if not nexus_map:
        return items

    nexus_cards = []
    seen_entities = set()
    for idx, eid, card_domain in card_entities:
        if eid not in nexus_map or eid in seen_entities:
            continue
        if len(nexus_cards) >= MAX_NEXUS_CARDS:
            break

        # Find a different curriculum perspective the learner knows
        alt_row = conn.execute("""
            SELECT ecl.domain_id, ecl.node_id, ecl.lens_title, ecl.lens_emphasis,
                   cn.title as node_title, cn.description as node_description,
                   cd.title as domain_title, ks.knowledge
            FROM entity_curriculum_links ecl
            JOIN curriculum_nodes cn ON cn.id = ecl.node_id AND cn.domain_id = ecl.domain_id
            JOIN curriculum_domains cd ON cd.id = ecl.domain_id
            LEFT JOIN knowledge_states ks ON ks.domain_id = ecl.domain_id AND ks.node_id = ecl.node_id
            WHERE ecl.entity_id = ?
              AND ecl.domain_id != ?
              AND ks.knowledge IN ('engaged', 'anchored')
            ORDER BY CASE ks.knowledge WHEN 'anchored' THEN 0 ELSE 1 END
            LIMIT 1
        """, (eid, card_domain)).fetchone()

        if alt_row:
            entity_name = nexus_map[eid]['name']
            nexus_cards.append((idx + 1, {
                'type': 'nexus',
                'entity_id': eid,
                'entity_name': entity_name,
                'nexus_score': nexus_map[eid]['nexus_score'],
                'card_domain': card_domain,
                'alt_domain_id': alt_row['domain_id'],
                'alt_domain_title': alt_row['domain_title'],
                'alt_node_title': alt_row['node_title'],
                'alt_node_description': alt_row['node_description'][:300],
                'alt_lens': alt_row['lens_title'] or alt_row['lens_emphasis'] or '',
                'alt_knowledge': alt_row['knowledge'],
                'prompt': (f"You know {entity_name} from {alt_row['domain_title']}. "
                           f"How does their role differ in this context?"),
            }))
            seen_entities.add(eid)

    if not nexus_cards:
        return items

    # Insert nexus cards after their triggering review card
    result = []
    nexus_by_idx = {}
    for insert_idx, card in nexus_cards:
        nexus_by_idx.setdefault(insert_idx, []).append(card)
    for i, item in enumerate(items):
        result.append(item)
        for ncard in nexus_by_idx.get(i, []):
            result.append(ncard)
    return result


_GENERIC_ENTITIES = {
    # Modern countries/regions too generic to annotate
    'italy', 'greece', 'sicily', 'venice', 'spain', 'france', 'germany', 'england',
    'egypt', 'turkey', 'syria', 'india', 'china', 'europe', 'africa', 'asia',
    'north africa', 'central asia', 'russia', 'united states', 'tunisia',
    'gaul', 'persia', 'bulgaria', 'gaza', 'kiev',
}


def _load_entity_index(conn) -> list[dict]:
    """Load all entities with their names and aliases for text matching.

    Excludes generic/obvious place names (countries, continents) that add
    noise without teaching anything.
    """
    rows = conn.execute(
        'SELECT entity_id, name, entity_type, aliases FROM shared_entities'
    ).fetchall()
    index = []
    for r in rows:
        # Skip generic places the reader obviously knows
        if r['name'].lower() in _GENERIC_ENTITIES:
            continue
        names = [r['name']]
        try:
            aliases = json.loads(r['aliases'] or '[]')
            if isinstance(aliases, list):
                names.extend(aliases)
        except (json.JSONDecodeError, TypeError):
            pass
        index.append({
            'entity_id': r['entity_id'],
            'name': r['name'],
            'entity_type': r['entity_type'],
            'match_names': names,
        })
    # Sort by longest name first so "Battle of Himera" matches before "Himera"
    index.sort(key=lambda e: max(len(n) for n in e['match_names']), reverse=True)
    return index


def annotate_entity_spans(text: str, entity_index: list[dict]) -> list[dict]:
    """Find entity name mentions in text and return span annotations.

    Returns list of {start, end, entity_id, entity_type, name} dicts,
    non-overlapping, sorted by position.
    """
    if not text or not entity_index:
        return []

    spans = []
    taken = set()  # character positions already claimed

    for entity in entity_index:
        for match_name in entity['match_names']:
            # Case-insensitive search for whole-word matches
            pattern = r'\b' + re.escape(match_name) + r'\b'
            for m in re.finditer(pattern, text, re.IGNORECASE):
                start, end = m.start(), m.end()
                # Skip if overlaps with already-claimed span
                if any(pos in taken for pos in range(start, end)):
                    continue
                spans.append({
                    'start': start,
                    'end': end,
                    'entity_id': entity['entity_id'],
                    'entity_type': entity['entity_type'],
                    'name': entity['name'],
                })
                taken.update(range(start, end))

    spans.sort(key=lambda s: s['start'])
    return spans


def _annotate_item_entities(item: dict, entity_index: list[dict]) -> dict:
    """Add entity_spans to a review session item."""
    if not entity_index:
        return item
    # Annotate rich_answer, memory_hook, and question
    all_spans = {}
    for field in ('rich_answer', 'memory_hook', 'question'):
        text = item.get(field)
        if text and isinstance(text, str):
            spans = annotate_entity_spans(text, entity_index)
            if spans:
                all_spans[field] = spans
    if all_spans:
        # Merge with existing entity_spans (e.g., microlearning 'content' spans)
        existing = item.get('entity_spans') or {}
        existing.update(all_spans)
        item['entity_spans'] = existing
    return item


def generate_review_stream(domain_filter: str | None = None, limit: int = 20,
                           offset: int = 0, conn=None) -> dict:
    """Generate a stream of review cards from knowledge_items.

    Returns an infinite-river style batch: no session boundary, client can
    request more via offset.  Cards are sorted by priority (due + overdue first,
    then never-reviewed, weighted by knowledge depth).
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        now_ms = int(time.time() * 1000)
        soon = now_ms + 24 * 60 * 60 * 1000  # next 24h

        # ── Query knowledge_items with knowledge_states ──────────────────
        domain_clause = "AND ki.curriculum_domain LIKE ?" if domain_filter else ""
        params = [f'%{domain_filter}%'] if domain_filter else []

        rows = conn.execute(
            f'''SELECT ki.id, ki.curriculum_node_id, ki.curriculum_domain,
                       ki.stability_days, ki.due_at, ki.last_reviewed_at,
                       ki.last_score, ki.review_count, ki.sources,
                       ki.cached_question, ki.created_at,
                       ki.triggered_follow_ups,
                       COALESCE(ks.knowledge, 'unknown') as node_knowledge,
                       COALESCE(ks.confidence, 0) as node_confidence,
                       cn.title as node_title, cn.description as node_description,
                       cn.level as node_level, cn.date_start as node_date_start,
                       cd.title as domain_title
                FROM knowledge_items ki
                LEFT JOIN knowledge_states ks
                  ON ks.domain_id = ki.curriculum_domain
                  AND ks.node_id = ki.curriculum_node_id
                LEFT JOIN curriculum_nodes cn
                  ON cn.id = ki.curriculum_node_id
                  AND cn.domain_id = ki.curriculum_domain
                LEFT JOIN curriculum_domains cd
                  ON cd.id = ki.curriculum_domain
                WHERE 1=1 {domain_clause}''',
            params
        ).fetchall()

        # ── Score and filter candidates ──────────────────────────────────
        candidates = []
        for r in rows:
            item = dict(r)
            review_count = item['review_count'] or 0
            due_at = item['due_at'] or 0
            node_knowledge = item['node_knowledge']

            # Skip items with no knowledge state (never encountered the concept)
            if node_knowledge == 'unknown':
                continue

            # Must have a cached question (or we can't show it)
            if not item.get('cached_question'):
                continue

            # Knowledge-weighted base score
            knowledge_weight = {
                'anchored': 8.0, 'engaged': 6.0, 'mentioned': 4.0,
            }.get(node_knowledge, 2.0)

            if review_count == 0:
                # Never reviewed — high priority
                score = knowledge_weight + 2.0 + random.random()
            elif due_at <= now_ms:
                # Overdue — highest priority
                overdue_days = (now_ms - due_at) / (24 * 3600 * 1000)
                score = knowledge_weight + min(overdue_days * 0.3, 5.0) + 10.0
                if item['last_score'] == 'missed':
                    score += 3.0
            elif due_at <= soon:
                # Due soon (next 24h)
                score = knowledge_weight + 1.0
            else:
                # Not due yet — include with low priority for infinite river
                days_until = (due_at - now_ms) / (24 * 3600 * 1000)
                score = max(0.1, knowledge_weight - days_until * 0.5)

            # Boost concrete factual questions (date/event/person) over abstract ones
            try:
                cq_data = json.loads(item.get('cached_question') or '{}')
            except (json.JSONDecodeError, TypeError):
                cq_data = {}
            fact_type = cq_data.get('answer_type', '')
            if fact_type in ('date', 'event', 'person'):
                score += 2.0  # prefer factual scaffolding
            elif fact_type in ('significance', 'connection'):
                score -= 1.0  # defer until facts are solid

            # Deprioritize gap-fill items (no book evidence — prerequisites/siblings)
            # Book-sourced items reinforce actual reading; gap-fills are speculative
            try:
                sources = json.loads(item.get('sources') or '[]')
            except (json.JSONDecodeError, TypeError):
                sources = []
            is_gap_fill = sources and all(
                s.get('book_id') is None for s in sources
            )
            if is_gap_fill:
                score -= 5.0  # push below book-sourced items

            candidates.append((score, item, is_gap_fill))

        # ── Interleave domains for variety ───────────────────────────
        # Group by domain, sort each group by score, then round-robin
        # Cap gap-fill items at 3 per batch to avoid flooding with unexplored topics
        from collections import defaultdict
        domain_groups: dict[str, list] = defaultdict(list)
        for score, item, is_gap_fill in candidates:
            domain_groups[item['curriculum_domain']].append((score, item, is_gap_fill))
        for g in domain_groups.values():
            g.sort(key=lambda x: x[0], reverse=True)

        # Round-robin across domains (largest groups first)
        sorted_domains = sorted(domain_groups.keys(),
                                key=lambda d: len(domain_groups[d]), reverse=True)
        interleaved = []
        gap_fill_count = 0
        GAP_FILL_CAP = 3  # max gap-fill items per batch
        idx = 0
        while len(interleaved) < len(candidates):
            added = False
            for d in sorted_domains:
                if idx < len(domain_groups[d]):
                    _score, _item, _is_gap = domain_groups[d][idx]
                    if _is_gap and gap_fill_count >= GAP_FILL_CAP:
                        continue  # skip excess gap-fill items
                    interleaved.append((_score, _item))
                    if _is_gap:
                        gap_fill_count += 1
                    added = True
            if not added:
                break
            idx += 1

        # Apply offset and limit for infinite river pagination
        selected = interleaved[offset:offset + limit]

        # ── Build response items ─────────────────────────────────────────
        def _parse_json_safe(val, default=None):
            if val is None:
                return default
            if isinstance(val, (list, dict)):
                return val
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        # Pre-load key_facts for all nodes in this batch so we can suggest untested facts
        node_key_facts: dict[tuple[str, str], list] = {}
        for _score, item in selected:
            node_id = item.get('curriculum_node_id')
            domain_id = item.get('curriculum_domain')
            if node_id and domain_id and (domain_id, node_id) not in node_key_facts:
                try:
                    kf_row = conn.execute(
                        'SELECT key_facts FROM curriculum_nodes WHERE id=? AND domain_id=?',
                        (node_id, domain_id)).fetchone()
                    if kf_row and kf_row['key_facts']:
                        node_key_facts[(domain_id, node_id)] = json.loads(kf_row['key_facts'])
                except Exception:
                    pass

        items = []
        for _score, item in selected:
            cq = _parse_json_safe(item['cached_question'], {})
            if not cq or not cq.get('question'):
                continue

            # Build related_facts: other key_facts from the same node
            # Untested ones are actionable; tested ones provide peace of mind
            related_facts = []
            current_fact_id = cq.get('fact_id', '')
            node_id = item.get('curriculum_node_id')
            domain_id = item.get('curriculum_domain')
            kfs = node_key_facts.get((domain_id, node_id), [])
            if kfs:
                question_history = _parse_json_safe(item.get('question_history'), [])
                tested_map = {}  # fact_id -> best score
                for h in question_history:
                    fid = h.get('fact_id')
                    if fid:
                        tested_map[fid] = h.get('score', 'partly')
                for f in kfs:
                    fid = f.get('id', '')
                    if fid == current_fact_id or not f.get('question'):
                        continue
                    if fid in tested_map:
                        related_facts.append({
                            'question': f['question'],
                            'type': f.get('type', 'event'),
                            'status': 'tested',
                            'score': tested_map[fid],
                        })
                    else:
                        related_facts.append({
                            'question': f['question'],
                            'type': f.get('type', 'event'),
                            'status': 'untested',
                        })
                    if len(related_facts) >= 5:
                        break

            card = {
                'type': 'review',
                'question_id': item['id'],  # knowledge_item id for scoring
                'question': cq['question'],
                'answer': cq.get('answer_guidance', ''),
                'rich_answer': cq.get('rich_answer') or cq.get('answer_guidance', ''),
                'answer_type': cq.get('answer_type', 'concept'),
                'node_title': item.get('node_title') or item['curriculum_node_id'],
                'node_description': item.get('node_description', ''),
                'domain': item.get('domain_title') or item['curriculum_domain'],
                'domain_id': item['curriculum_domain'],
                'memory_hook': cq.get('memory_hook') or cq.get('temporal_hook', ''),
                'temporal_hook': cq.get('temporal_hook', ''),
                'curriculum_context': cq.get('curriculum_context', ''),
                'anchors': _parse_json_safe(cq.get('anchors'), []),
                'review_count': item['review_count'] or 0,
                'last_score': item['last_score'],
                'stability_days': item['stability_days'],
                'node_knowledge': item['node_knowledge'],
                'node_confidence': item['node_confidence'],
                'follow_up_queries': _parse_json_safe(cq.get('follow_up_queries'), []),
                'triggered_follow_ups': _parse_json_safe(item.get('triggered_follow_ups'), []),
                'fact_id': cq.get('fact_id', ''),
                'entities': cq.get('entities', []),
                'related_facts': related_facts,
            }
            items.append(card)

        # ── Mix in microlearning ─────────────────────────────────────────
        # Two streams:
        # 1. NEW ML cards (never seen) → full card with all quizzes, front of queue
        # 2. DUE individual quizzes (from previously-seen cards) → interleaved
        try:
            regular_count = len(items)
            if regular_count < 3:
                ml_limit = limit
            else:
                ml_limit = max(3, limit // 4)

            now_ms = int(time.time() * 1000)

            # Helper: build entity spans for a card
            def _build_ml_spans(entities_raw, content_text):
                spans = []
                if not entities_raw or not content_text:
                    return spans
                for ent in entities_raw:
                    name = ent.get('name', '')
                    if not name or len(name) < 2:
                        continue
                    idx = content_text.find(name)
                    while idx != -1:
                        spans.append({
                            'start': idx, 'end': idx + len(name),
                            'entity_id': ent.get('canonical', name.lower().replace(' ', '_')),
                            'name': name, 'entity_type': ent.get('type', 'concept'),
                        })
                        idx = content_text.find(name, idx + len(name))
                spans.sort(key=lambda s: s['start'])
                filtered = []
                last_end = 0
                for sp in spans:
                    if sp['start'] >= last_end:
                        filtered.append(sp)
                        last_end = sp['end']
                return filtered

            # 1. New ML cards — never had any quiz interaction
            # A card is "new" if it has no quizzes with review_count > 0
            new_card_rows = conn.execute('''
                SELECT mc.* FROM microlearning_cards mc
                WHERE mc.status = 'completed'
                  AND NOT EXISTS (
                    SELECT 1 FROM microlearning_quizzes mq
                    WHERE mq.card_id = mc.id AND mq.review_count > 0
                  )
                ORDER BY mc.created_at DESC
                LIMIT ?
            ''', (ml_limit,)).fetchall()

            new_ml = []
            for r in new_card_rows:
                ml = dict(r)
                content_text = ml.get('content') or ''
                entities_raw = _parse_json_safe(ml.get('entities'), [])
                ml_spans = _build_ml_spans(entities_raw, content_text)

                # Load quizzes for this card
                quiz_rows = conn.execute(
                    "SELECT id, question, answer, status FROM microlearning_quizzes "
                    "WHERE card_id=? AND status='active' ORDER BY rowid",
                    (ml['id'],)).fetchall()
                quizzes = [{'id': q['id'], 'question': q['question'],
                            'answer': q['answer']} for q in quiz_rows]

                # Fallback: legacy cards with single question but no quiz rows
                if not quizzes and ml.get('question'):
                    quizzes = [{'id': ml['id'], 'question': ml['question'],
                                'answer': ml.get('answer_guidance') or ''}]

                card = {
                    'type': 'microlearning',
                    'question_id': ml['id'],
                    'title': ml.get('title') or '',
                    'content': content_text,
                    'sections': _parse_json_safe(ml.get('sections'), []),
                    'query': ml['query'],
                    'quizzes': quizzes,
                    # Legacy fields for backward compat
                    'question': quizzes[0]['question'] if quizzes else '',
                    'answer': quizzes[0]['answer'] if quizzes else '',
                    'rich_answer': quizzes[0]['answer'] if quizzes else '',
                    'answer_type': 'concept',
                    'node_title': ml.get('title') or '',
                    'domain': ml.get('source_domain') or '',
                    'memory_hook': '', 'temporal_hook': '',
                    'curriculum_context': '', 'anchors': [],
                    'review_count': 0,
                    'stability_days': 1.0,
                    'node_knowledge': 'mentioned',
                    'node_confidence': 0.5,
                    'follow_up_queries': json.loads(ml.get('follow_up_queries') or '[]'),
                    'triggered_follow_ups': _parse_json_safe(ml.get('triggered_follow_ups'), []),
                    'entities': entities_raw,
                    'entity_spans': {'content': ml_spans} if ml_spans else {},
                }
                new_ml.append(card)

            # 2. Due individual quizzes from previously-seen cards
            due_quiz_rows = conn.execute('''
                SELECT mq.*, mc.content, mc.query as card_query,
                       mc.title as card_title, mc.sections as card_sections,
                       mc.entities, mc.follow_up_queries as card_follow_ups,
                       mc.triggered_follow_ups as card_triggered_follow_ups,
                       mc.source_domain
                FROM microlearning_quizzes mq
                JOIN microlearning_cards mc ON mc.id = mq.card_id
                WHERE mq.status = 'active' AND mq.review_count > 0
                  AND mq.due_at <= ?
                ORDER BY mq.due_at ASC
                LIMIT ?
            ''', (now_ms, ml_limit)).fetchall()

            seen_ml = []
            for q in due_quiz_rows:
                q = dict(q)
                content_text = q.get('content') or ''
                entities_raw = _parse_json_safe(q.get('entities'), [])
                ml_spans = _build_ml_spans(entities_raw, content_text)
                seen_ml.append({
                    'type': 'microlearning_quiz',
                    'question_id': q['id'],
                    'card_id': q['card_id'],
                    'question': q['question'],
                    'answer': q['answer'],
                    'rich_answer': q['answer'],
                    'answer_type': 'concept',
                    'title': q.get('card_title') or '',
                    'content': content_text,
                    'sections': _parse_json_safe(q.get('card_sections'), []),
                    'query': q.get('card_query') or '',
                    'node_title': q.get('card_title') or '', 'domain': q.get('source_domain') or '',
                    'memory_hook': '', 'temporal_hook': '',
                    'curriculum_context': '', 'anchors': [],
                    'review_count': q['review_count'] or 0,
                    'last_score': q.get('last_score'),
                    'stability_days': q.get('stability_days') or 1.0,
                    'node_knowledge': 'mentioned',
                    'node_confidence': 0.5,
                    'follow_up_queries': json.loads(q.get('card_follow_ups') or '[]'),
                    'triggered_follow_ups': _parse_json_safe(q.get('card_triggered_follow_ups'), []),
                    'entities': entities_raw,
                    'entity_spans': {'content': ml_spans} if ml_spans else {},
                })

            # ── Priority-based ML interleaving ──────────────────────
            # Split new ML cards by source_type for different interleave ratios:
            # - voice_wondering / user_request: HIGH priority (1 per 3 SR cards)
            # - follow_up / entity_research / legacy: LOW priority (1 per 7 SR cards)
            high_ml = []  # voice + user_request
            low_ml = []   # follow_up + entity + legacy
            for card in new_ml:
                # Check source_type on the underlying ML card row
                card_id = card.get('question_id', '')
                try:
                    st_row = conn.execute(
                        'SELECT source_type FROM microlearning_cards WHERE id=?',
                        (card_id,)).fetchone()
                    st = st_row[0] if st_row else None
                except Exception:
                    st = None
                if st in ('voice_wondering', 'user_request'):
                    high_ml.append(card)
                else:
                    low_ml.append(card)

            # Merge: SR items first, then interleave ML cards
            # High-priority ML (voice/user): every 3rd SR card
            # Low-priority ML (follow-up) + due quizzes: every 7th SR card
            merged = []
            hi_idx = 0
            lo_idx = 0
            sq_idx = 0  # seen_ml (due quizzes)
            low_pool = low_ml + seen_ml  # combine follow-up new cards with due quizzes

            for i, item in enumerate(items):
                merged.append(item)
                pos = i + 1
                # High-priority ML at 1:3
                if pos % 3 == 0 and hi_idx < len(high_ml):
                    merged.append(high_ml[hi_idx])
                    hi_idx += 1
                # Low-priority ML + due quizzes at 1:7
                if pos % 7 == 0 and lo_idx < len(low_pool):
                    merged.append(low_pool[lo_idx])
                    lo_idx += 1

            # Append any remaining ML cards at the tail (not front-loaded)
            while hi_idx < len(high_ml):
                merged.append(high_ml[hi_idx])
                hi_idx += 1
            while lo_idx < len(low_pool):
                merged.append(low_pool[lo_idx])
                lo_idx += 1

            items = merged
        except Exception as e:
            print(f'[review-stream] microlearning query failed: {e}', flush=True)
            import traceback; traceback.print_exc()

        # ── Entity annotations ───────────────────────────────────────────
        entity_index = _load_entity_index(conn)
        if entity_index:
            items = [_annotate_item_entities(item, entity_index) for item in items]

        # Insert entity intro cards for unknown entities
        entity_knowledge = _load_entity_knowledge(conn)
        items = _build_entity_intro_items(items, entity_knowledge, conn)

        # Insert nexus cards for high-connectivity entities (cross-curriculum perspective)
        items = _insert_nexus_cards(items, conn)

        # ── Stats ────────────────────────────────────────────────────────
        total_items = conn.execute('SELECT COUNT(*) FROM knowledge_items').fetchone()[0]
        total_with_question = conn.execute(
            'SELECT COUNT(*) FROM knowledge_items WHERE cached_question IS NOT NULL'
        ).fetchone()[0]
        due_count = conn.execute(
            'SELECT COUNT(*) FROM knowledge_items WHERE due_at <= ?', (soon,)
        ).fetchone()[0]

        # Count total available microlearning cards
        try:
            total_ml = conn.execute(
                "SELECT COUNT(*) FROM microlearning_cards WHERE status = 'completed'"
            ).fetchone()[0]
        except Exception:
            total_ml = 0

        # Count by domain
        domain_counts = {}
        for r in conn.execute(
            'SELECT curriculum_domain, COUNT(*) as c FROM knowledge_items GROUP BY curriculum_domain'
        ).fetchall():
            domain_counts[r['curriculum_domain']] = r['c']

        # has_more considers both regular candidates and microlearning cards
        total_available = len(candidates) + total_ml
        has_more = len(items) >= limit and offset + limit < total_available

        return {
            'items': items,
            'generated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'offset': offset,
            'has_more': has_more,
            'total_candidates': len(candidates) + total_ml,
            'total_items': total_items,
            'total_with_question': total_with_question,
            'due_count': due_count,
            'domain_counts': domain_counts,
        }
    finally:
        if own:
            conn.close()


# generate_review_session(), record_review_result(), get_review_status() removed —
# retrieval_questions/review_schedule tables archived.
# Scoring now goes through review_engine.record_answer() exclusively.


# ═════════════════════════════════════════════════════════════════════════════
# ASSESSMENT IMPORT (self-report / 20Q)
# ═════════════════════════════════════════════════════════════════════════════

FAMILIARITY_TO_KNOWLEDGE = {
    'unknown': ('unknown', 0.0, 0),
    'heard_of': ('mentioned', 0.4, 1),
    'know_basics': ('engaged', 0.6, 2),
    'could_explain': ('anchored', 0.8, 2),
    'know_deeply': ('anchored', 0.95, 3),
    'new_to_me': ('unknown', 0.0, 0),
    'knew_some': ('engaged', 0.6, 2),
    'knew_all': ('anchored', 0.9, 3),
}

INTEREST_TO_CANONICAL = {
    'core': 'core', 'curious': 'curious', 'none': 'none',
    'interested': 'curious', 'star': 'core', 'skip': 'none',
}


def import_assessment_answers(domain_id: str, answers: dict, conn=None) -> dict:
    """Import assessment answers into knowledge states.

    answers: {node_id: {familiarity, interest, ...}}
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        imported = 0
        by_level = {}
        for node_id, answer in answers.items():
            fam = answer.get('familiarity', 'unknown')
            interest_raw = answer.get('interest', 'none')
            knowledge, confidence, layer = FAMILIARITY_TO_KNOWLEDGE.get(fam, ('unknown', 0.0, 0))
            interest = INTEREST_TO_CANONICAL.get(interest_raw, 'curious')
            update_knowledge(domain_id, node_id, knowledge=knowledge,
                             interest=interest, confidence=confidence,
                             source='self_report', highest_layer=layer, conn=conn)
            imported += 1
            by_level[knowledge] = by_level.get(knowledge, 0) + 1
        if own:
            conn.commit()
        return {'imported': imported, 'total': len(answers), 'by_level': by_level}
    finally:
        if own:
            conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE ATLAS DATA
# ═════════════════════════════════════════════════════════════════════════════

def get_knowledge_atlas_data(conn=None) -> dict:
    """Build complete knowledge atlas data for web visualization.

    Aggregates all curricula, nodes with knowledge states, shared entities,
    books with curriculum mappings, and article counts into a single payload.
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        curricula = []
        all_node_count = 0
        knowledge_dist = {'unknown': 0, 'mentioned': 0, 'engaged': 0, 'anchored': 0}

        for meta in list_curricula(conn=conn):
            domain_id = meta['id']
            curriculum = load_curriculum(domain_id, conn=conn)
            if not curriculum:
                continue
            states = load_knowledge_states(domain_id, conn=conn)

            # Key facts counts per node
            facts_rows = conn.execute(
                'SELECT id, key_facts FROM curriculum_nodes WHERE domain_id = ?',
                (domain_id,)
            ).fetchall()
            facts_count = {}
            for r in facts_rows:
                kf = r['key_facts']
                if kf and kf != '[]':
                    try:
                        facts_count[r['id']] = len(json.loads(kf))
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Book mappings per node
            book_rows = conn.execute('''
                SELECT bcm.node_id, bcm.coverage, pb.id as book_id, pb.title as book_title
                FROM book_curriculum_mappings bcm
                JOIN physical_books pb ON pb.id = bcm.book_id
                WHERE bcm.domain_id = ?
            ''', (domain_id,)).fetchall()
            node_books: dict[str, list] = {}
            for br in book_rows:
                node_books.setdefault(br['node_id'], []).append({
                    'id': br['book_id'], 'title': br['book_title'], 'coverage': br['coverage'],
                })

            # Article counts per node
            article_rows = conn.execute('''
                SELECT node_id, COUNT(DISTINCT article_id) as cnt
                FROM article_curriculum_nodes WHERE domain_id = ?
                GROUP BY node_id
            ''', (domain_id,)).fetchall()
            node_articles = {r['node_id']: r['cnt'] for r in article_rows}

            domain_stats = {'unknown': 0, 'mentioned': 0, 'engaged': 0, 'anchored': 0}
            nodes = []
            for node in curriculum['nodes']:
                state = states.get(node['id'], {})
                knowledge = state.get('knowledge', 'unknown')
                domain_stats[knowledge] = domain_stats.get(knowledge, 0) + 1
                knowledge_dist[knowledge] = knowledge_dist.get(knowledge, 0) + 1
                all_node_count += 1

                # Voice chunks linked to this node
                voice_chunks = []
                try:
                    voice_rows = conn.execute('''
                        SELECT tc.chunk_text, tc.chunk_type
                        FROM transcript_chunks tc
                        JOIN chunk_node_links cnl ON tc.id = cnl.chunk_id
                        WHERE cnl.node_id = ? AND cnl.domain_id = ?
                        AND tc.chunk_type != 'raw_speech'
                        ORDER BY cnl.relevance DESC
                        LIMIT 5
                    ''', (node['id'], domain_id)).fetchall()
                    voice_chunks = [{'text': r['chunk_text'][:200], 'type': r['chunk_type']} for r in voice_rows]
                except Exception:
                    pass

                nodes.append({
                    'id': node['id'],
                    'title': node['title'],
                    'description': node.get('description', ''),
                    'parent_id': node.get('parent_id'),
                    'level': node.get('level', 2),
                    'obscurity': node.get('obscurity', 2),
                    'date_start': node.get('date_start'),
                    'date_end': node.get('date_end'),
                    'knowledge': knowledge,
                    'interest': state.get('interest', 'none'),
                    'confidence': state.get('confidence', 0),
                    'key_facts_count': facts_count.get(node['id'], 0),
                    'prerequisites': node.get('prerequisites', []),
                    'books': node_books.get(node['id'], []),
                    'article_count': node_articles.get(node['id'], 0),
                    'voice_chunks': voice_chunks,
                })

            # Domain knowledge portrait
            portrait = None
            portrait_version = None
            try:
                portrait_row = conn.execute(
                    'SELECT summary, version, updated_at FROM domain_knowledge_summaries WHERE domain_id = ?',
                    (domain_id,)
                ).fetchone()
                if portrait_row:
                    portrait = portrait_row['summary']
                    portrait_version = portrait_row['version']
            except Exception:
                pass

            domain_dict = {
                'id': domain_id,
                'title': curriculum['title'],
                'description': curriculum.get('description', ''),
                'depth': curriculum.get('depth', ''),
                'node_count': len(nodes),
                'nodes': nodes,
                'stats': domain_stats,
            }
            if portrait:
                domain_dict['portrait'] = portrait
                domain_dict['portrait_version'] = portrait_version
            curricula.append(domain_dict)

        # Shared entities with curriculum links and knowledge
        entity_rows = conn.execute('''
            SELECT entity_id, name, entity_type, description, modern_name,
                   nexus_score, date_start, date_end, aliases
            FROM shared_entities ORDER BY nexus_score DESC
        ''').fetchall()

        entity_links = conn.execute('''
            SELECT ecl.entity_id, ecl.domain_id, ecl.node_id, ecl.lens_title, ecl.lens_emphasis,
                   cn.title as node_title, cd.title as domain_title,
                   COALESCE(ks.knowledge, 'unknown') as knowledge
            FROM entity_curriculum_links ecl
            JOIN curriculum_nodes cn ON cn.domain_id = ecl.domain_id AND cn.id = ecl.node_id
            JOIN curriculum_domains cd ON cd.id = ecl.domain_id
            LEFT JOIN knowledge_states ks ON ks.domain_id = ecl.domain_id AND ks.node_id = ecl.node_id
        ''').fetchall()

        entity_link_map: dict[str, list] = {}
        entity_knowledge: dict[str, str] = {}
        rank = {'unknown': 0, 'mentioned': 1, 'engaged': 2, 'anchored': 3}
        for el in entity_links:
            eid = el['entity_id']
            entity_link_map.setdefault(eid, []).append({
                'domain_id': el['domain_id'], 'domain_title': el['domain_title'],
                'node_id': el['node_id'], 'node_title': el['node_title'],
                'lens_title': el['lens_title'], 'knowledge': el['knowledge'],
            })
            if rank.get(el['knowledge'], 0) > rank.get(entity_knowledge.get(eid, 'unknown'), 0):
                entity_knowledge[eid] = el['knowledge']

        entities = []
        for er in entity_rows:
            eid = er['entity_id']
            # Voice chunks linked to this entity
            entity_voice_chunks = []
            try:
                voice_rows = conn.execute('''
                    SELECT tc.chunk_text, tc.chunk_type
                    FROM transcript_chunks tc
                    JOIN chunk_entity_links cel ON tc.id = cel.chunk_id
                    WHERE cel.entity_name = ?
                    AND tc.chunk_type != 'raw_speech'
                    ORDER BY cel.relevance DESC
                    LIMIT 5
                ''', (er['name'],)).fetchall()
                entity_voice_chunks = [{'text': r['chunk_text'][:200], 'type': r['chunk_type']} for r in voice_rows]
            except Exception:
                pass
            entities.append({
                'id': eid, 'name': er['name'], 'entity_type': er['entity_type'],
                'description': er['description'], 'modern_name': er['modern_name'],
                'nexus_score': er['nexus_score'] or 0,
                'date_start': er['date_start'], 'date_end': er['date_end'],
                'knowledge': entity_knowledge.get(eid, 'unknown'),
                'curriculum_links': entity_link_map.get(eid, []),
                'voice_chunks': entity_voice_chunks,
            })

        # Books with curriculum mappings
        book_rows = conn.execute('''
            SELECT id, title, author, reading_status, significance, cover_url
            FROM physical_books ORDER BY title
        ''').fetchall()

        book_mapping_rows = conn.execute('''
            SELECT bcm.book_id, bcm.domain_id, bcm.node_id, bcm.coverage,
                   cn.title as node_title, cd.title as domain_title
            FROM book_curriculum_mappings bcm
            JOIN curriculum_nodes cn ON cn.domain_id = bcm.domain_id AND cn.id = bcm.node_id
            JOIN curriculum_domains cd ON cd.id = bcm.domain_id
        ''').fetchall()
        book_map: dict[str, list] = {}
        for bm in book_mapping_rows:
            book_map.setdefault(bm['book_id'], []).append({
                'domain_id': bm['domain_id'], 'domain_title': bm['domain_title'],
                'node_id': bm['node_id'], 'node_title': bm['node_title'],
                'coverage': bm['coverage'],
            })

        books = []
        for br in book_rows:
            mappings = book_map.get(br['id'], [])
            if mappings:
                books.append({
                    'id': br['id'], 'title': br['title'], 'author': br['author'],
                    'reading_status': br['reading_status'], 'significance': br['significance'],
                    'cover_url': br['cover_url'], 'curriculum_mappings': mappings,
                })

        # Article stats
        article_stats = conn.execute('''
            SELECT COUNT(DISTINCT article_id) as cnt FROM article_curriculum_nodes
        ''').fetchone()

        return {
            'curricula': curricula,
            'entities': entities,
            'books': books,
            'stats': {
                'total_nodes': all_node_count,
                'total_entities': len(entities),
                'total_books': len(books),
                'total_curricula': len(curricula),
                'knowledge_distribution': knowledge_dist,
                'articles_mapped': article_stats['cnt'] if article_stats else 0,
            },
        }
    finally:
        if own:
            conn.close()


def get_dashboard_stats(conn=None) -> dict:
    """Build comprehensive statistics for the dashboard page.

    Returns today's summary, knowledge state per curriculum, review/quiz stats,
    reading progress, voice elicitation stats, and recent activity timeline.
    All items include linkable IDs for navigation.
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        now_ms = int(time.time() * 1000)
        today_start_ms = now_ms - (now_ms % (24 * 60 * 60 * 1000))
        day_7_ms = now_ms - 7 * 24 * 60 * 60 * 1000
        day_30_ms = now_ms - 30 * 24 * 60 * 60 * 1000
        end_today_ms = today_start_ms + 24 * 60 * 60 * 1000

        # ── Today's summary ─────────────────────────────────────────
        reviewed_today = conn.execute(
            'SELECT COUNT(*) FROM knowledge_items WHERE last_reviewed_at >= ?',
            (today_start_ms,)
        ).fetchone()[0]
        reviewed_today += conn.execute(
            'SELECT COUNT(*) FROM microlearning_cards WHERE last_reviewed_at >= ?',
            (today_start_ms,)
        ).fetchone()[0]

        due_today = conn.execute(
            'SELECT COUNT(*) FROM knowledge_items WHERE due_at <= ?',
            (end_today_ms,)
        ).fetchone()[0]
        due_today += conn.execute(
            "SELECT COUNT(*) FROM review_items WHERE due_at <= ? AND item_type != 'book_chapter'",
            (end_today_ms,)
        ).fetchone()[0]

        elicitations_today = conn.execute(
            "SELECT COUNT(*) FROM voice_transcripts WHERE source = 'elicitation' AND created_at >= ?",
            (today_start_ms,)
        ).fetchone()[0]

        # Score distribution today
        scores_today = {'knew': 0, 'partly': 0, 'missed': 0}
        for tbl in ('knowledge_items', 'microlearning_cards'):
            for row in conn.execute(
                f'SELECT last_score FROM {tbl} WHERE last_reviewed_at >= ? AND last_score IS NOT NULL',
                (today_start_ms,)
            ).fetchall():
                s = row[0]
                if s in scores_today:
                    scores_today[s] += 1

        # ── Knowledge state per curriculum ──────────────────────────
        curricula_stats = []
        total_nodes = 0
        total_upgraded_7d = 0
        for meta in list_curricula(conn=conn):
            domain_id = meta['id']
            dist = {'unknown': 0, 'mentioned': 0, 'engaged': 0, 'anchored': 0}
            nodes = conn.execute(
                'SELECT cn.id, COALESCE(ks.knowledge, ?) as knowledge '
                'FROM curriculum_nodes cn '
                'LEFT JOIN knowledge_states ks ON cn.id = ks.node_id AND cn.domain_id = ks.domain_id '
                'WHERE cn.domain_id = ?',
                ('unknown', domain_id)
            ).fetchall()
            for n in nodes:
                k = n['knowledge'] if n['knowledge'] in dist else 'unknown'
                dist[k] += 1
            node_count = len(nodes)
            total_nodes += node_count

            # Nodes upgraded this week (last_assessed within 7 days, not unknown)
            upgraded = conn.execute(
                "SELECT COUNT(*) FROM knowledge_states "
                "WHERE domain_id = ? AND knowledge != 'unknown' AND last_assessed >= ?",
                (domain_id, datetime.utcfromtimestamp(day_7_ms / 1000).isoformat())
            ).fetchone()[0]
            total_upgraded_7d += upgraded

            curricula_stats.append({
                'domain_id': domain_id,
                'title': meta.get('title', domain_id),
                'node_count': node_count,
                'distribution': dist,
                'upgraded_7d': upgraded,
            })

        # ── Review & quiz statistics ────────────────────────────────
        def _count_reviews(table, since_ms=None):
            if since_ms:
                return conn.execute(
                    f'SELECT COUNT(*) FROM {table} WHERE last_reviewed_at >= ? AND review_count > 0',
                    (since_ms,)
                ).fetchone()[0]
            return conn.execute(
                f'SELECT COUNT(*) FROM {table} WHERE review_count > 0'
            ).fetchone()[0]

        def _score_dist(table, since_ms=None):
            dist = {'knew': 0, 'partly': 0, 'missed': 0}
            where = 'WHERE last_score IS NOT NULL'
            params = ()
            if since_ms:
                where += ' AND last_reviewed_at >= ?'
                params = (since_ms,)
            for row in conn.execute(
                f'SELECT last_score, COUNT(*) as cnt FROM {table} {where} GROUP BY last_score',
                params
            ).fetchall():
                if row['last_score'] in dist:
                    dist[row['last_score']] = row['cnt']
            return dist

        review_counts = {
            'all_time': _count_reviews('knowledge_items') + _count_reviews('microlearning_cards'),
            '30d': _count_reviews('knowledge_items', day_30_ms) + _count_reviews('microlearning_cards', day_30_ms),
            '7d': _count_reviews('knowledge_items', day_7_ms) + _count_reviews('microlearning_cards', day_7_ms),
        }

        score_30d_ki = _score_dist('knowledge_items', day_30_ms)
        score_30d_ml = _score_dist('microlearning_cards', day_30_ms)
        score_dist_30d = {
            k: score_30d_ki.get(k, 0) + score_30d_ml.get(k, 0)
            for k in ('knew', 'partly', 'missed')
        }

        followups_launched = conn.execute(
            "SELECT COUNT(*) FROM microlearning_cards WHERE source_item_id IS NOT NULL"
        ).fetchone()[0]

        cards_in_pipeline = conn.execute(
            "SELECT COUNT(*) FROM microlearning_cards WHERE status IN ('pending', 'processing')"
        ).fetchone()[0]

        avg_stability = conn.execute(
            'SELECT AVG(stability_days) FROM knowledge_items WHERE review_count > 0'
        ).fetchone()[0] or 0

        quizzes_completed = conn.execute(
            'SELECT COUNT(*) FROM microlearning_quizzes WHERE review_count > 0'
        ).fetchone()[0]

        # Per-curriculum review counts (30d)
        reviews_by_domain = {}
        for row in conn.execute(
            'SELECT curriculum_domain, COUNT(*) as cnt FROM knowledge_items '
            'WHERE last_reviewed_at >= ? AND review_count > 0 GROUP BY curriculum_domain',
            (day_30_ms,)
        ).fetchall():
            reviews_by_domain[row['curriculum_domain']] = row['cnt']

        # ── Reading progress ────────────────────────────────────────
        books_reading = []
        for row in conn.execute(
            "SELECT id, title, author, current_page, page_count, current_chapter, reading_status "
            "FROM physical_books WHERE reading_status = 'reading' ORDER BY last_interaction_at DESC"
        ).fetchall():
            pct = round(row['current_page'] / row['page_count'] * 100) if row['page_count'] and row['current_page'] else 0
            books_reading.append({
                'id': row['id'],
                'title': row['title'],
                'author': row['author'],
                'current_page': row['current_page'] or 0,
                'page_count': row['page_count'] or 0,
                'current_chapter': row['current_chapter'],
                'progress_pct': pct,
            })

        # Kindle books currently reading (exclude those already in physical_books via kindle_ prefix)
        physical_ids = {b['id'] for b in books_reading}
        for row in conn.execute(
            "SELECT key, title, title_resolved, author, progress_pct "
            "FROM kindle_books WHERE status = 'reading' ORDER BY last_read DESC LIMIT 5"
        ).fetchall():
            # Skip if already listed as physical book (physical books use kindle_ prefix)
            if f"kindle_{row['key']}" in physical_ids:
                continue
            books_reading.append({
                'id': row['key'],
                'title': row['title_resolved'] or row['title'],
                'author': row['author'],
                'current_page': None,
                'page_count': None,
                'progress_pct': round(row['progress_pct'] or 0),
                'kindle': True,
            })

        # ── Voice elicitation stats ─────────────────────────────────
        voice_total = conn.execute(
            "SELECT COUNT(*) FROM voice_transcripts WHERE source = 'elicitation'"
        ).fetchone()[0]

        voice_audio_bytes = conn.execute(
            "SELECT SUM(audio_bytes) FROM voice_transcripts WHERE source = 'elicitation'"
        ).fetchone()[0] or 0
        # Rough estimate: ~16KB/s for compressed audio
        voice_audio_minutes = round(voice_audio_bytes / 16000 / 60, 1) if voice_audio_bytes else 0

        # Recall distribution from LLM results
        # Format: suggested_score = 'knew'|'partly'|'missed', coverage_pct = 0-100
        recall_dist = {'full': 0, 'partial': 0, 'nothing': 0}
        for row in conn.execute(
            "SELECT llm_result FROM voice_transcripts WHERE source = 'elicitation' AND llm_result IS NOT NULL"
        ).fetchall():
            try:
                result = json.loads(row['llm_result'])
                score = result.get('suggested_score', '')
                if score == 'knew':
                    recall_dist['full'] += 1
                elif score == 'partly':
                    recall_dist['partial'] += 1
                else:
                    recall_dist['nothing'] += 1
            except (json.JSONDecodeError, TypeError):
                recall_dist['nothing'] += 1

        voice_cards_triggered = conn.execute(
            "SELECT COUNT(*) FROM voice_transcripts "
            "WHERE source = 'elicitation' AND microlearning_triggered != '[]' AND microlearning_triggered IS NOT NULL"
        ).fetchone()[0]

        # ── Recent activity timeline ────────────────────────────────
        timeline = []

        # Recent reviews (from knowledge_items)
        for row in conn.execute(
            'SELECT ki.curriculum_domain, ki.curriculum_node_id, ki.last_score, ki.last_reviewed_at, '
            'cn.title as node_title, cd.title as domain_title '
            'FROM knowledge_items ki '
            'LEFT JOIN curriculum_nodes cn ON ki.curriculum_node_id = cn.id AND ki.curriculum_domain = cn.domain_id '
            'LEFT JOIN curriculum_domains cd ON ki.curriculum_domain = cd.id '
            'WHERE ki.last_reviewed_at IS NOT NULL '
            'ORDER BY ki.last_reviewed_at DESC LIMIT 20'
        ).fetchall():
            timeline.append({
                'type': 'review',
                'ts': row['last_reviewed_at'],
                'title': row['node_title'] or row['curriculum_node_id'],
                'domain_id': row['curriculum_domain'],
                'domain_title': row['domain_title'] or row['curriculum_domain'],
                'node_id': row['curriculum_node_id'],
                'score': row['last_score'],
            })

        # Recent voice elicitations
        for row in conn.execute(
            "SELECT id, node_id, domain_id, node_title, llm_result, created_at, microlearning_triggered "
            "FROM voice_transcripts WHERE source = 'elicitation' "
            "ORDER BY created_at DESC LIMIT 15"
        ).fetchall():
            recall = 'unknown'
            try:
                result = json.loads(row['llm_result'] or '{}')
                score = result.get('suggested_score', '')
                if score == 'knew':
                    recall = 'full'
                elif score == 'partly':
                    recall = 'partial'
                else:
                    recall = 'nothing'
            except (json.JSONDecodeError, TypeError):
                pass
            cards_triggered = 0
            try:
                cards_triggered = len(json.loads(row['microlearning_triggered'] or '[]'))
            except (json.JSONDecodeError, TypeError):
                pass

            domain_title = row['domain_id']
            if row['domain_id']:
                dt_row = conn.execute(
                    'SELECT title FROM curriculum_domains WHERE id = ?', (row['domain_id'],)
                ).fetchone()
                if dt_row:
                    domain_title = dt_row['title']

            timeline.append({
                'type': 'voice',
                'ts': row['created_at'],
                'title': row['node_title'] or 'Elicitation',
                'domain_id': row['domain_id'],
                'domain_title': domain_title,
                'node_id': row['node_id'],
                'recall': recall,
                'cards_triggered': cards_triggered,
            })

        # Recent microlearning cards generated
        for row in conn.execute(
            'SELECT mc.id, mc.title, mc.query, mc.source_domain, mc.source_node_id, mc.created_at, '
            'cd.title as domain_title '
            'FROM microlearning_cards mc '
            'LEFT JOIN curriculum_domains cd ON mc.source_domain = cd.id '
            'WHERE mc.status = ? ORDER BY mc.created_at DESC LIMIT 10',
            ('completed',)
        ).fetchall():
            timeline.append({
                'type': 'card_generated',
                'ts': row['created_at'],
                'title': row['title'] or row['query'],
                'card_id': row['id'],
                'domain_id': row['source_domain'],
                'domain_title': row['domain_title'] or row['source_domain'],
                'node_id': row['source_node_id'],
            })

        # Recent book activity (captures)
        for row in conn.execute(
            "SELECT bc.book_id, bc.chapter, bc.page_number, bc.created_at, "
            "bc.type as capture_type, pb.title as book_title, pb.author "
            "FROM book_captures bc "
            "JOIN physical_books pb ON bc.book_id = pb.id "
            "ORDER BY bc.created_at DESC LIMIT 10"
        ).fetchall():
            timeline.append({
                'type': 'book_capture',
                'ts': row['created_at'],
                'title': row['chapter'] or row['capture_type'],
                'book_id': row['book_id'],
                'book_title': row['book_title'],
                'author': row['author'],
                'page': row['page_number'],
                'capture_type': row['capture_type'],
            })

        # Sort timeline by timestamp descending
        timeline.sort(key=lambda x: x.get('ts') or 0, reverse=True)

        return {
            'today': {
                'reviewed': reviewed_today,
                'due': due_today,
                'elicitations': elicitations_today,
                'scores': scores_today,
            },
            'knowledge': {
                'curricula': curricula_stats,
                'total_nodes': total_nodes,
                'upgraded_7d': total_upgraded_7d,
            },
            'review': {
                'counts': review_counts,
                'score_dist_30d': score_dist_30d,
                'followups_launched': followups_launched,
                'cards_in_pipeline': cards_in_pipeline,
                'avg_stability_days': round(avg_stability, 1),
                'quizzes_completed': quizzes_completed,
                'by_domain': reviews_by_domain,
            },
            'reading': {
                'books': books_reading,
            },
            'voice': {
                'total': voice_total,
                'audio_minutes': voice_audio_minutes,
                'recall_dist': recall_dist,
                'cards_triggered': voice_cards_triggered,
            },
            'timeline': timeline[:30],
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }
    finally:
        if own:
            conn.close()


def get_book_prescan(book_id: str, conn=None) -> dict:
    """Generate a curriculum-based preview for a book before/during reading.

    Shows:
    - already_known: curriculum nodes covered by this book that the learner already knows
    - will_learn: nodes covered by this book that are new to the learner
    - missing_prerequisites: prerequisites of will_learn nodes that the learner doesn't know
    - cross_book_overlaps: other books that cover some of the same nodes
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        # Get all curriculum mappings for this book
        mappings = conn.execute("""
            SELECT bcm.domain_id, bcm.node_id, bcm.coverage,
                   cn.title as node_title, cn.description as node_description,
                   cn.level, cn.date_start, cn.parent_id,
                   cd.title as domain_title,
                   ks.knowledge, ks.confidence
            FROM book_curriculum_mappings bcm
            JOIN curriculum_nodes cn ON cn.id = bcm.node_id AND cn.domain_id = bcm.domain_id
            JOIN curriculum_domains cd ON cd.id = bcm.domain_id
            LEFT JOIN knowledge_states ks ON ks.domain_id = bcm.domain_id AND ks.node_id = bcm.node_id
            WHERE bcm.book_id = ?
            ORDER BY bcm.domain_id, cn.level, cn.date_start
        """, (book_id,)).fetchall()

        if not mappings:
            return {'book_id': book_id, 'mapped': False, 'already_known': [],
                    'will_learn': [], 'missing_prerequisites': [], 'cross_book_overlaps': []}

        already_known = []
        will_learn = []
        will_learn_ids = []  # (domain_id, node_id) for prerequisite lookup

        for m in mappings:
            node_info = {
                'domain_id': m['domain_id'],
                'domain_title': m['domain_title'],
                'node_id': m['node_id'],
                'node_title': m['node_title'],
                'node_description': m['node_description'][:200],
                'coverage': m['coverage'],
                'level': m['level'],
                'date_start': m['date_start'],
            }
            knowledge = m['knowledge'] or 'unknown'
            if knowledge in ('engaged', 'anchored'):
                node_info['knowledge'] = knowledge
                node_info['confidence'] = m['confidence']
                already_known.append(node_info)
            else:
                node_info['knowledge'] = knowledge
                will_learn.append(node_info)
                will_learn_ids.append((m['domain_id'], m['node_id']))

        # Find missing prerequisites for will_learn nodes
        missing_prerequisites = []
        seen_prereqs = set()
        for domain_id, node_id in will_learn_ids:
            prereq_rows = conn.execute("""
                SELECT cp.prerequisite_id, cn.title, cn.description,
                       ks.knowledge
                FROM curriculum_prerequisites cp
                JOIN curriculum_nodes cn ON cn.id = cp.prerequisite_id AND cn.domain_id = cp.domain_id
                LEFT JOIN knowledge_states ks ON ks.domain_id = cp.domain_id AND ks.node_id = cp.prerequisite_id
                WHERE cp.domain_id = ? AND cp.node_id = ?
                  AND COALESCE(ks.knowledge, 'unknown') IN ('unknown', 'mentioned')
            """, (domain_id, node_id)).fetchall()

            for pr in prereq_rows:
                key = (domain_id, pr['prerequisite_id'])
                if key in seen_prereqs:
                    continue
                seen_prereqs.add(key)
                missing_prerequisites.append({
                    'domain_id': domain_id,
                    'node_id': pr['prerequisite_id'],
                    'node_title': pr['title'],
                    'node_description': pr['description'][:200] if pr['description'] else '',
                    'knowledge': pr['knowledge'] or 'unknown',
                    'needed_by': node_id,
                })

        # Find other books covering overlapping nodes
        mapped_node_pairs = [(m['domain_id'], m['node_id']) for m in mappings]
        cross_book_overlaps = []
        if mapped_node_pairs:
            overlap_rows = conn.execute("""
                SELECT bcm.book_id, pb.title as book_title, COUNT(*) as shared_nodes
                FROM book_curriculum_mappings bcm
                LEFT JOIN physical_books pb ON pb.id = bcm.book_id
                WHERE bcm.book_id != ?
                  AND (bcm.domain_id, bcm.node_id) IN ({})
                GROUP BY bcm.book_id
                HAVING shared_nodes >= 2
                ORDER BY shared_nodes DESC
                LIMIT 5
            """.format(','.join(f"('{d}','{n}')" for d, n in mapped_node_pairs)),
                (book_id,)
            ).fetchall()

            for r in overlap_rows:
                cross_book_overlaps.append({
                    'book_id': r['book_id'],
                    'book_title': r['book_title'] or r['book_id'],
                    'shared_nodes': r['shared_nodes'],
                })

        return {
            'book_id': book_id,
            'mapped': True,
            'already_known': already_known,
            'will_learn': will_learn,
            'missing_prerequisites': missing_prerequisites,
            'cross_book_overlaps': cross_book_overlaps,
            'summary': {
                'total_nodes': len(mappings),
                'known_count': len(already_known),
                'new_count': len(will_learn),
                'missing_prereqs_count': len(missing_prerequisites),
            },
        }
    finally:
        if own:
            conn.close()
