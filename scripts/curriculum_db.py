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
            old_knowledge = existing['knowledge']
            if knowledge:
                new_level = KNOWLEDGE_ORDER.get(knowledge, 0)
                old_level = KNOWLEDGE_ORDER.get(old_knowledge, 0)
                cur_knowledge = knowledge if new_level >= old_level else old_knowledge
            else:
                cur_knowledge = old_knowledge
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
            # Log transition if knowledge level actually changed
            if cur_knowledge != old_knowledge:
                try:
                    conn.execute(
                        '''INSERT INTO knowledge_transitions
                           (node_id, domain_id, from_level, to_level, source, source_id)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (node_id, domain_id, old_knowledge, cur_knowledge,
                         source or 'unknown', None)
                    )
                except Exception:
                    pass  # table may not exist yet on older DBs
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
            # Log initial transition from unknown
            if k != 'unknown':
                try:
                    conn.execute(
                        '''INSERT INTO knowledge_transitions
                           (node_id, domain_id, from_level, to_level, source, source_id)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (node_id, domain_id, 'unknown', k, source or 'unknown', None)
                    )
                except Exception:
                    pass
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
MAX_INTRO_CARDS = 0  # Disabled — rich answer cards now provide entity context


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


def _build_entity_capture_intros(items: list[dict], conn) -> list[dict]:
    """Insert entity-briefing cards before the first review of a fresh
    entity_capture item.

    Fires when ALL of:
    - item.type == 'review' (entity_capture items render as review type)
    - provenance.origin == 'entity_capture'
    - review_count == 0 (never reviewed yet)
    - linked shared_entities row has a meaningful description

    One intro per entity per session, inserted before that entity's first
    review appearance. May prove redundant with the rich_answer once
    observed; if so, gate on capture-age or drop entirely.
    """
    # Find candidate entity_ids (fresh entity_capture items)
    candidates: dict[str, int] = {}  # entity_id → first item index in `items`
    for i, item in enumerate(items):
        if item.get('type') != 'review':
            continue
        prov = item.get('provenance') or {}
        if prov.get('origin') != 'entity_capture':
            continue
        if (item.get('review_count') or 0) != 0:
            continue
        eid = prov.get('entity_id') or item.get('entity_id')
        if not eid or eid in candidates:
            continue
        candidates[eid] = i

    if not candidates:
        return items

    details = _load_entity_details_for_intros(list(candidates.keys()), conn)

    # Build intros only for entities with a non-trivial description
    intros_by_idx: dict[int, list[dict]] = {}
    for eid, idx in candidates.items():
        d = details.get(eid)
        if not d:
            continue
        desc = (d.get('description') or '').strip()
        if len(desc) < 20:
            continue  # No useful briefing possible
        intros_by_idx.setdefault(idx, []).append({
            'type': 'entity_intro',
            'entity_id': eid,
            'entity_name': d['name'],
            'entity_type': d.get('entity_type'),
            'modern_name': d.get('modern_name'),
            'description': desc,
            'latitude': d.get('latitude'),
            'longitude': d.get('longitude'),
            'wikipedia_url': d.get('wikipedia_url'),
            'date_start': d.get('date_start'),
            'date_end': d.get('date_end'),
        })

    if not intros_by_idx:
        return items

    result: list[dict] = []
    for i, item in enumerate(items):
        for intro in intros_by_idx.get(i, []):
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
    for field in ('rich_answer', 'memory_hook', 'question', 'content'):
        text = item.get(field)
        if text and isinstance(text, str):
            spans = annotate_entity_spans(text, entity_index)
            if spans:
                all_spans[field] = spans
    # Annotate individual section texts (microlearning cards with sections)
    sections = item.get('sections')
    if sections and isinstance(sections, list):
        for i, sec in enumerate(sections):
            text = sec.get('text', '')
            if text:
                spans = annotate_entity_spans(text, entity_index)
                if spans:
                    all_spans[f'section_{i}'] = spans
    if all_spans:
        # Merge with existing entity_spans (e.g., microlearning 'content' spans)
        existing = item.get('entity_spans') or {}
        existing.update(all_spans)
        item['entity_spans'] = existing
    return item


def _mix_structural_cards(items: list, conn, domain_filter: str | None,
                          now_ms: int, quick_quizzes: list | None = None) -> list:
    """Mix structural cards + quick quizzes into the review stream.

    Creates session rhythm (E6 hypothesis):
      structural (30s) → quiz (6s) → review (20s) → review → quiz → structural...

    Rules:
    - After each structural card: insert 1-2 quick quizzes
    - Between review/ML items: insert a quiz every 2nd item
    - Never show 3+ quick quizzes in a row
    """
    due_cutoff = now_ms + 24 * 3600 * 1000
    # Query each card type separately to guarantee mix (3 aspect + 2 sequence + 2 synchronic max)
    domain_clause = "AND sc.domain_id LIKE ?" if domain_filter else ""
    domain_params = [f'%{domain_filter}%'] if domain_filter else []
    # Activation gating: only show structural cards for content the user has actually engaged
    # with (read a book about, or dumped into voice capture). A curriculum node exists in the
    # taxonomy does NOT mean the user has studied it. Gap-fill rows (chapter_title contains
    # "Curriculum context — not yet in a book") and self-assessment-only rows are NOT evidence.
    #
    #   aspect + cast  (have node_id) — require ≥1 knowledge_item on the exact
    #                                   (node_id, domain_id) with book or voice source
    #   sequence       — require ≥3 reviewed aspect positions in the domain (existing)
    #                    AND ≥1 domain KI with book or voice source
    #   synchronic     — require ≥1 domain KI with book or voice source (anchor's domain)
    #   causal         — require ≥1 domain KI with book or voice source
    #
    # "book or voice" expressed as a LIKE on the sources JSON — agrees with
    # Python-side classification on all 266 KI at time of audit.
    SEQUENCE_REVIEWED_ASPECT_THRESHOLD = 3

    EVIDENCE_LIKE = """(
        ki.sources LIKE '%"book_id": "%'
        OR ki.sources LIKE '%"source": "voice_capture%'
        OR ki.sources LIKE '%"transcript_id":%'
    )"""

    # TEMP: structural-only mode — show only aspect/sequence cards for focused testing
    STRUCTURAL_ONLY = False

    card_rows = []
    for card_type, limit in [
        ('aspect', 10 if STRUCTURAL_ONLY else 3),
        ('sequence', 5 if STRUCTURAL_ONLY else 2),
        ('synchronic', 5 if STRUCTURAL_ONLY else 2),
        ('cast', 5 if STRUCTURAL_ONLY else 2),
        ('causal', 5 if STRUCTURAL_ONLY else 1),
    ]:
        # Per-node evidence gate for cards that point at a single node.
        # Per-domain evidence gate for cards spanning the whole domain.
        if card_type in ('aspect', 'cast'):
            gate_clause = f"""
            AND EXISTS (
                SELECT 1 FROM knowledge_items ki
                WHERE ki.curriculum_node_id = sc.node_id
                  AND ki.curriculum_domain = sc.domain_id
                  AND {EVIDENCE_LIKE}
            )"""
        else:
            gate_clause = f"""
            AND EXISTS (
                SELECT 1 FROM knowledge_items ki
                WHERE ki.curriculum_domain = sc.domain_id
                  AND {EVIDENCE_LIKE}
            )"""

        if card_type == 'sequence':
            # Sequence also requires enough reviewed aspect positions — inherited from Session 75.
            gate_clause += f"""
            AND (SELECT COUNT(*) FROM structural_positions sp2
                 JOIN structural_cards sc2 ON sc2.id = sp2.card_id
                 WHERE sc2.domain_id = sc.domain_id
                 AND sc2.card_type = 'aspect'
                 AND sp2.review_count > 0) >= {SEQUENCE_REVIEWED_ASPECT_THRESHOLD}"""
        if card_type == 'cast':
            gate_clause += """
            AND EXISTS (SELECT 1 FROM knowledge_items ki2
                        WHERE ki2.curriculum_node_id = sc.node_id
                        AND ki2.curriculum_domain = sc.domain_id
                        AND ki2.review_count > 0)"""

        # Honour the migration `hidden` column so cards already flagged speculative don't surface.
        gate_clause += " AND COALESCE(sc.hidden, 0) = 0"
        # Domain-diverse selection: pick best card per domain, then take top N.
        # Without this, all cards would come from whichever domain was generated first.
        rows = conn.execute(f'''
            SELECT id, card_type, title, description, domain_id, node_id,
                   date_start, date_end, date_anchor, review_count, hooks, domain_title
            FROM (
                SELECT sc.id, sc.card_type, sc.title, sc.description,
                       sc.domain_id, sc.node_id,
                       sc.date_start, sc.date_end, sc.date_anchor, sc.review_count, sc.hooks,
                       cd.title as domain_title,
                       ROW_NUMBER() OVER (
                           PARTITION BY sc.domain_id
                           ORDER BY sc.review_count ASC, sc.due_at ASC
                       ) as rn
                FROM structural_cards sc
                LEFT JOIN curriculum_domains cd ON cd.id = sc.domain_id
                WHERE sc.card_type = ?
                {domain_clause}
                AND EXISTS (
                    SELECT 1 FROM structural_positions sp
                    WHERE sp.card_id = sc.id AND sp.due_at <= ?
                )
                {gate_clause}
            )
            WHERE rn = 1
            ORDER BY review_count ASC, RANDOM()
            LIMIT ?
        ''', [card_type] + domain_params + [due_cutoff, limit]).fetchall()
        card_rows.extend(rows)

    if not card_rows:
        return items

    structural_items = []
    for card_row in card_rows:
        card = dict(card_row)
        card_type = card['card_type']

        # Load positions for this card
        positions = [dict(r) for r in conn.execute('''
            SELECT id, position, fact_id, entity_id, question_text, answer_text,
                   question_variants, hook_type, mnemonic, mnemonic_type,
                   stability_days, due_at, review_count, last_score
            FROM structural_positions
            WHERE card_id = ?
            ORDER BY position
        ''', (card['id'],)).fetchall()]

        # Parse question_variants JSON
        for p in positions:
            try:
                p['question_variants'] = json.loads(p['question_variants'] or '[]')
            except (json.JSONDecodeError, TypeError):
                p['question_variants'] = []

        # Build position data — sequence cards include year info
        pos_list = []
        for p in positions:
            pos_data = {
                'position_id': p['id'],
                'position': p['position'],
                'question_text': p['question_text'],
                'answer_text': p['answer_text'],
                'hook_type': p['hook_type'] or 'IDENTITY',
                'mnemonic': p['mnemonic'],
                'mnemonic_type': p['mnemonic_type'],
                'stability_days': p['stability_days'] or 1.0,
                'due_at': p['due_at'] or 0,
                'review_count': p['review_count'] or 0,
                'last_score': p['last_score'],
            }
            if card_type == 'aspect':
                pos_data['question_variants'] = p['question_variants']
                pos_data['fact_type'] = p['hook_type'] or 'event'
            elif card_type == 'sequence':
                # Extract year data from question_variants JSON
                variants = p['question_variants']
                if isinstance(variants, dict):
                    pos_data['year'] = variants.get('year')
                    pos_data['year_display'] = variants.get('year_display', '')
                    if variants.get('scale_to_next'):
                        pos_data['scale_to_next'] = variants['scale_to_next']
            elif card_type == 'synchronic':
                # Pass through domain/label/connection from question_variants
                pos_data['question_variants'] = p['question_variants']
            elif card_type == 'cast':
                # Cast cards store role/significance/entity_id in question_variants
                pos_data['question_variants'] = p['question_variants']
            elif card_type == 'causal':
                # Causal cards store event/year_display/connection_to_next
                pos_data['question_variants'] = p['question_variants']
            pos_list.append(pos_data)

        item = {
            'type': card_type,
            'card_id': card['id'],
            'title': card['title'],
            'domain_id': card['domain_id'],
            'domain_title': card.get('domain_title', ''),
            'positions': pos_list,
            'provenance': {
                'origin': 'structural',
                'review_count': card['review_count'] or 0,
            },
        }
        if card_type == 'aspect':
            item['node_id'] = card['node_id']
        elif card_type == 'sequence':
            item['description'] = card.get('description', '')
            item['date_start'] = card.get('date_start')
            item['date_end'] = card.get('date_end')
        elif card_type == 'synchronic':
            item['description'] = card.get('description', '')
            item['date_anchor'] = card.get('date_anchor')
        elif card_type == 'cast':
            item['node_id'] = card['node_id']
            item['description'] = card.get('description', '')
        elif card_type == 'causal':
            item['description'] = card.get('description', '')

        structural_items.append(item)

    # Round-robin by type so rare types (sequence/synchronic/cast/causal) appear
    # early in the stream. Without this, the build loop emits all aspect cards
    # first, pushing rarer types past where most sessions end.
    type_order = ['aspect', 'sequence', 'synchronic', 'cast', 'causal']
    by_type = {ct: [] for ct in type_order}
    for it in structural_items:
        by_type.setdefault(it['type'], []).append(it)
    interleaved = []
    while any(by_type[ct] for ct in type_order):
        for ct in type_order:
            if by_type[ct]:
                interleaved.append(by_type[ct].pop(0))
    structural_items = interleaved

    if STRUCTURAL_ONLY:
        return structural_items

    qq_pool = list(quick_quizzes or [])
    qq_idx = 0

    # Front-load structural cards so all 5 types surface in short sessions.
    # Insert a structural after every 2nd review item for the first FRONTLOAD_UNTIL
    # items (5 slots at positions 3,6,9,12,15 — one for each type when paired
    # with the round-robin ordering above). After that, fall back to every-3rd.
    FRONTLOAD_UNTIL = 10
    FRONTLOAD_INTERVAL = 2
    NORMAL_INTERVAL = 3

    # Build rhythm: structural → quiz → review → review → quiz → ...
    merged = []
    struct_idx = 0
    consecutive_quizzes = 0  # guard against 3+ quizzes in a row

    for i, item in enumerate(items):
        merged.append(item)
        consecutive_quizzes = 0
        pos = i + 1

        interval = FRONTLOAD_INTERVAL if pos <= FRONTLOAD_UNTIL else NORMAL_INTERVAL
        # Insert structural card at the current rhythm tick
        if pos % interval == 0 and struct_idx < len(structural_items):
            merged.append(structural_items[struct_idx])
            struct_idx += 1
            consecutive_quizzes = 0

            # After structural card: insert 1-2 quick quizzes (palate cleanser)
            for _ in range(min(2, len(qq_pool) - qq_idx)):
                if consecutive_quizzes >= 2:
                    break
                merged.append(qq_pool[qq_idx])
                qq_idx += 1
                consecutive_quizzes += 1

        # Every 2nd item in the post-frontload region (not already followed by
        # structural): insert quiz. During frontload the rhythm itself already
        # hits every 2nd item, so this branch is only relevant after pos>10.
        elif pos % 2 == 0 and qq_idx < len(qq_pool) and consecutive_quizzes < 2:
            merged.append(qq_pool[qq_idx])
            qq_idx += 1
            consecutive_quizzes += 1

    # Append remaining structural cards (interleaved with remaining quizzes)
    while struct_idx < len(structural_items):
        merged.append(structural_items[struct_idx])
        struct_idx += 1
        # 1 quiz after each remaining structural card
        if qq_idx < len(qq_pool):
            merged.append(qq_pool[qq_idx])
            qq_idx += 1

    # Append remaining quizzes at tail (better than clustering, but still last)
    while qq_idx < len(qq_pool):
        merged.append(qq_pool[qq_idx])
        qq_idx += 1

    return merged


def _recency_boost(created_at_ms: int | float | None, now_ms: int) -> float:
    """Continuous recency decay for unreviewed items (review_count==0).

    Formula: 4.0 / (1.0 + age_days / 7.0) — half-life-like decay with a 7-day
    characteristic time. Values at key ages:
        0d  → 4.00   (fresh capture, strongest push)
        1d  → 3.50
        3d  → 2.80
        7d  → 2.00   (boost roughly halved)
        14d → 1.33
        21d → 1.00
        90d → 0.29
        365d → 0.08
    Never reaches zero — guarantees a fresher unreviewed item always outranks
    an older unreviewed item when other scoring components are equal. Applied
    only before the first review; once FSRS takes over, scheduling handles it.
    """
    if not created_at_ms:
        return 0.0
    age_days = max(0.0, (now_ms - float(created_at_ms)) / 86400000.0)
    return 4.0 / (1.0 + age_days / 7.0)


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

            # Anchored items the user already answered correctly: skip unless overdue
            # and the user is actually struggling (last missed). Voice elicitations and
            # successful reviews both set anchored — no need to keep drilling.
            node_confidence = item.get('node_confidence') or 0.0
            if (node_knowledge == 'anchored' and node_confidence >= 0.5
                    and item['last_score'] == 'knew' and due_at > now_ms):
                continue

            # Knowledge-weighted base score — engaged items (actively learning) get
            # highest priority; anchored items are deprioritized (already well known)
            knowledge_weight = {
                'anchored': 3.0, 'engaged': 8.0, 'mentioned': 4.0,
            }.get(node_knowledge, 2.0)

            # Track score components for provenance display
            schedule_reason = 'not_due'
            overdue_days = 0.0
            recency_boost = 0.0

            if review_count == 0:
                # Never reviewed — high priority, with continuous recency decay
                # so fresher book-reads / gap-fills outrank older unreviewed items.
                recency_boost = _recency_boost(item.get('created_at'), now_ms)
                score = knowledge_weight + 2.0 + random.random() + recency_boost
                schedule_reason = 'never_reviewed'
            elif due_at <= now_ms:
                # Overdue — highest priority
                overdue_days = (now_ms - due_at) / (24 * 3600 * 1000)
                score = knowledge_weight + min(overdue_days * 0.3, 5.0) + 10.0
                if item['last_score'] == 'missed':
                    score += 3.0
                schedule_reason = 'overdue'
            elif due_at <= soon:
                # Due soon (next 24h)
                score = knowledge_weight + 1.0
                schedule_reason = 'due_soon'
            else:
                # Not due yet — include with low priority for infinite river
                # Anchored items not yet due get extra deprioritization
                days_until = (due_at - now_ms) / (24 * 3600 * 1000)
                score = max(0.1, knowledge_weight - days_until * 0.5)
                if node_knowledge == 'anchored':
                    score = max(0.05, score - 3.0)

            # Boost concrete factual questions (date/event/person) over abstract ones
            try:
                cq_data = json.loads(item.get('cached_question') or '{}')
            except (json.JSONDecodeError, TypeError):
                cq_data = {}
            fact_type = cq_data.get('answer_type', '')
            fact_type_adj = 0.0
            if fact_type in ('date', 'event', 'person'):
                score += 2.0  # prefer factual scaffolding
                fact_type_adj = 2.0
            elif fact_type in ('significance', 'connection'):
                score -= 1.0  # defer until facts are solid
                fact_type_adj = -1.0

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

            # Determine origin from sources
            if is_gap_fill:
                origin = 'gap_fill'
            elif sources and any(s.get('chapter_title', '').startswith('Whole book:') for s in sources):
                origin = 'book_whole'
            elif sources and any(s.get('book_id') for s in sources):
                origin = 'book_chapter'
            else:
                origin = 'unknown'

            # Attach provenance to item for later serialization
            item['_provenance'] = {
                'origin': origin,
                'is_gap_fill': is_gap_fill,
                'stream_score': round(score, 2),
                'schedule_reason': schedule_reason,
                'overdue_days': round(overdue_days, 1),
                'knowledge_weight': knowledge_weight,
                'fact_type_adj': fact_type_adj,
                'recency_boost': round(recency_boost, 2),
                'sources': sources,
                'created_at': item.get('created_at'),
                'due_at': due_at,
                'last_reviewed_at': item.get('last_reviewed_at'),
            }

            candidates.append((score, item, is_gap_fill))

        # ── Query knowledge_entities (entity-keyed, no curriculum) ───
        # Entity items come from voice captures about topics outside existing
        # curricula. They have no knowledge_state — shown directly with a
        # fixed knowledge_weight. See research/entity-first-architecture.md.
        try:
            ke_rows = conn.execute(
                '''SELECT id, entity_id, entity_name, entity_type, wikidata_qid,
                          stability_days, due_at, last_reviewed_at, last_score,
                          review_count, cached_question, created_at, sources
                   FROM knowledge_entities
                   WHERE cached_question IS NOT NULL'''
            ).fetchall()
        except Exception as e:
            print(f'[review-stream] knowledge_entities query failed: {e}', flush=True)
            ke_rows = []

        for r in ke_rows:
            item = dict(r)
            review_count = item['review_count'] or 0
            due_at = item['due_at'] or 0
            knowledge_weight = 6.0  # Between engaged (8.0) and mentioned (4.0)
            schedule_reason = 'not_due'
            overdue_days = 0.0
            recency_boost = 0.0

            if review_count == 0:
                # Continuous recency decay: fresh voice captures rank high and
                # fade over days/weeks rather than cutting off at 48h.
                recency_boost = _recency_boost(item.get('created_at'), now_ms)
                score = knowledge_weight + 2.0 + random.random() + recency_boost
                schedule_reason = 'never_reviewed'
            elif due_at <= now_ms:
                overdue_days = (now_ms - due_at) / (24 * 3600 * 1000)
                score = knowledge_weight + min(overdue_days * 0.3, 5.0) + 10.0
                if item['last_score'] == 'missed':
                    score += 3.0
                schedule_reason = 'overdue'
            elif due_at <= soon:
                score = knowledge_weight + 1.0
                schedule_reason = 'due_soon'
            else:
                days_until = (due_at - now_ms) / (24 * 3600 * 1000)
                score = max(0.1, knowledge_weight - days_until * 0.5)

            try:
                cq_data = json.loads(item.get('cached_question') or '{}')
            except (json.JSONDecodeError, TypeError):
                cq_data = {}
            fact_type = cq_data.get('answer_type', '')
            fact_type_adj = 0.0
            if fact_type in ('date', 'event', 'person'):
                score += 2.0
                fact_type_adj = 2.0
            elif fact_type in ('significance', 'connection'):
                score -= 1.0
                fact_type_adj = -1.0

            # Parse sources (voice captures) for About-this-card provenance.
            # Each entry: {source, capture_id, source_text, added_at}
            try:
                ke_sources = json.loads(item.get('sources') or '[]')
                if not isinstance(ke_sources, list):
                    ke_sources = []
            except (json.JSONDecodeError, TypeError):
                ke_sources = []

            # Pseudo-fields so the existing card builder treats this like
            # a review item but with entity framing
            ent_type = (item.get('entity_type') or 'entity').title()
            item['curriculum_domain'] = 'entity'
            item['curriculum_node_id'] = item.get('entity_id') or item['id']
            item['node_title'] = item.get('entity_name') or ''
            item['node_description'] = ''
            item['domain_title'] = ent_type
            item['node_knowledge'] = 'engaged'
            item['node_confidence'] = 0.5
            item['node_level'] = 2
            item['node_date_start'] = None
            item['triggered_follow_ups'] = '[]'
            item['sources'] = json.dumps(ke_sources)

            item['_provenance'] = {
                'origin': 'entity_capture',
                'is_gap_fill': False,
                'stream_score': round(score, 2),
                'schedule_reason': schedule_reason,
                'overdue_days': round(overdue_days, 1),
                'knowledge_weight': knowledge_weight,
                'fact_type_adj': fact_type_adj,
                'recency_boost': round(recency_boost, 2),
                'sources': ke_sources,
                'created_at': item.get('created_at'),
                'due_at': due_at,
                'last_reviewed_at': item.get('last_reviewed_at'),
                'entity_id': item.get('entity_id'),
                'wikidata_qid': item.get('wikidata_qid'),
            }

            candidates.append((score, item, False))

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
                if domain_id == 'entity':
                    # Entity-keyed items store their own key_facts on the
                    # knowledge_entities row — use those as related_facts.
                    try:
                        kf_row = conn.execute(
                            'SELECT key_facts FROM knowledge_entities WHERE id=?',
                            (item['id'],)).fetchone()
                        if kf_row and kf_row['key_facts']:
                            node_key_facts[(domain_id, node_id)] = json.loads(kf_row['key_facts'])
                    except Exception:
                        pass
                else:
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

            # Existing quizzes for this node (multi-cue + manually created)
            existing_quizzes = []
            existing_quiz_questions = set()
            if node_id and domain_id:
                try:
                    eq_rows = conn.execute('''
                        SELECT mq.id, mq.question, mq.answer, mq.fact_id,
                               mq.status, mq.last_score, mq.review_count
                        FROM microlearning_quizzes mq
                        JOIN microlearning_cards mc ON mc.id = mq.card_id
                        WHERE mc.source_node_id = ? AND mc.source_domain = ?
                        ORDER BY mq.fact_id, mq.created_at
                    ''', (node_id, domain_id)).fetchall()
                    for eq in eq_rows:
                        existing_quizzes.append({
                            'id': eq['id'],
                            'question': eq['question'],
                            'fact_id': eq['fact_id'] or '',
                            'status': eq['status'],
                            'last_score': eq['last_score'],
                            'review_count': eq['review_count'] or 0,
                        })
                        if eq['question']:
                            existing_quiz_questions.add(eq['question'].lower().strip())
                except Exception:
                    pass

            # Build quiz_suggestions live: key_facts not yet covered by
            # knowledge_items or existing quizzes
            quiz_suggestions = []
            if kfs and node_id and domain_id:
                # Find which fact questions already have knowledge_items
                existing_ki_questions = set()
                try:
                    ki_rows = conn.execute(
                        'SELECT cached_question FROM knowledge_items '
                        'WHERE curriculum_node_id=? AND curriculum_domain=?',
                        (node_id, domain_id)).fetchall()
                    for ki_row in ki_rows:
                        ki_cq = _parse_json_safe(ki_row['cached_question'], {})
                        if ki_cq and ki_cq.get('question'):
                            existing_ki_questions.add(ki_cq['question'].lower().strip())
                except Exception:
                    pass

                # Merge both exclusion sets
                excluded_questions = existing_ki_questions | existing_quiz_questions

                for f in kfs:
                    if len(quiz_suggestions) >= 3:
                        break
                    fq = (f.get('question') or '').strip()
                    fa = (f.get('answer') or '').strip()
                    if not fq or not fa:
                        continue
                    if f.get('id') == current_fact_id:
                        continue
                    if fq.lower().strip() in excluded_questions:
                        continue
                    quiz_suggestions.append({
                        'question': fq,
                        'answer': fa,
                        'fact_id': f.get('id', ''),
                        'type': f.get('type', 'fact'),
                    })

            # Remove related_facts that already appear in quiz_suggestions
            qs_questions = {s['question'].lower().strip() for s in quiz_suggestions}
            related_facts = [f for f in related_facts
                             if f['question'].lower().strip() not in qs_questions]

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
                'quiz_suggestions': quiz_suggestions,
                'existing_quizzes': existing_quizzes,
                'provenance': item.get('_provenance', {}),
                # Entity-keyed items carry their entity identity for optional
                # client rendering (entity-first architecture, Phase 1).
                'entity_id': item.get('entity_id', ''),
                'wikidata_qid': item.get('wikidata_qid', ''),
            }
            items.append(card)

        # ── Mix in microlearning ─────────────────────────────────────────
        quick_quiz_pool = []  # filled below; used by _mix_structural_cards
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
            # Session 90: flagged_inaccurate cards drop out immediately.
            new_card_rows = conn.execute('''
                SELECT mc.* FROM microlearning_cards mc
                WHERE mc.status = 'completed'
                  AND COALESCE(mc.flagged_inaccurate, 0) = 0
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
                    "SELECT id, question, answer, fact_id, rich_answer, status "
                    "FROM microlearning_quizzes "
                    "WHERE card_id=? AND status='active' ORDER BY rowid",
                    (ml['id'],)).fetchall()
                quizzes = [{'id': q['id'], 'question': q['question'],
                            'answer': q['answer'], 'fact_id': q['fact_id'] or '',
                            'rich_answer': q['rich_answer'] or ''} for q in quiz_rows]

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
                    'provenance': {
                        'origin': ml.get('source_type') or 'unknown',
                        'source_item_id': ml.get('source_item_id') or '',
                        'source_node_id': ml.get('source_node_id') or '',
                        'generation_depth': ml.get('generation_depth') or 0,
                        'created_at': ml.get('created_at'),
                    },
                }
                new_ml.append(card)

            # 2. Due individual quizzes from previously-seen cards
            due_quiz_rows = conn.execute('''
                SELECT mq.*, mq.fact_id, mq.rich_answer as quiz_rich_answer,
                       mc.content, mc.query as card_query,
                       mc.title as card_title, mc.sections as card_sections,
                       mc.entities, mc.follow_up_queries as card_follow_ups,
                       mc.triggered_follow_ups as card_triggered_follow_ups,
                       mc.source_domain, mc.source_type, mc.source_item_id,
                       mc.source_node_id, mc.generation_depth,
                       mc.created_at as card_created_at
                FROM microlearning_quizzes mq
                JOIN microlearning_cards mc ON mc.id = mq.card_id
                WHERE mq.status = 'active' AND mq.review_count > 0
                  AND mq.due_at <= ?
                  AND COALESCE(mc.flagged_inaccurate, 0) = 0
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
                    'rich_answer': q.get('quiz_rich_answer') or q['answer'],
                    'fact_id': q.get('fact_id') or '',
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
                    'provenance': {
                        'origin': q.get('source_type') or 'unknown',
                        'source_item_id': q.get('source_item_id') or '',
                        'source_node_id': q.get('source_node_id') or '',
                        'generation_depth': q.get('generation_depth') or 0,
                        'created_at': q.get('card_created_at'),
                    },
                })

            # ── Priority-based ML interleaving ──────────────────────
            # Split new ML cards by source_type for different interleave ratios:
            # - voice_wondering / user_request / correction: HIGH priority (1 per 3 SR cards)
            # - follow_up / entity_research / legacy: LOW priority (1 per 7 SR cards)
            high_ml = []  # voice + user_request + correction
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
                if st in ('voice_wondering', 'user_request', 'correction'):
                    high_ml.append(card)
                else:
                    low_ml.append(card)

            # Merge: SR items first, then interleave ML cards
            # High-priority ML (voice/user): every 3rd SR card
            # Low-priority ML (follow-up only): every 7th SR card
            # Due quizzes (seen_ml) are handled later by _mix_structural_cards
            # for proper structural→quiz→review rhythm
            merged = []
            hi_idx = 0
            lo_idx = 0

            for i, item in enumerate(items):
                merged.append(item)
                pos = i + 1
                # High-priority ML at 1:3
                if pos % 3 == 0 and hi_idx < len(high_ml):
                    merged.append(high_ml[hi_idx])
                    hi_idx += 1
                # Low-priority ML at 1:7
                if pos % 7 == 0 and lo_idx < len(low_ml):
                    merged.append(low_ml[lo_idx])
                    lo_idx += 1

            # Append any remaining ML cards at the tail (not front-loaded)
            while hi_idx < len(high_ml):
                merged.append(high_ml[hi_idx])
                hi_idx += 1
            while lo_idx < len(low_ml):
                merged.append(low_ml[lo_idx])
                lo_idx += 1

            items = merged
            # Quick quiz pool: due individual quizzes for structural interleaving
            quick_quiz_pool = seen_ml
        except Exception as e:
            print(f'[review-stream] microlearning query failed: {e}', flush=True)
            import traceback; traceback.print_exc()

        # ── Mix in structural (aspect) cards + quick quizzes ────────────
        try:
            items = _mix_structural_cards(items, conn, domain_filter, now_ms,
                                          quick_quizzes=quick_quiz_pool)
        except Exception as e:
            print(f'[review-stream] structural card mixing failed: {e}', flush=True)
            import traceback; traceback.print_exc()

        # ── Entity annotations ───────────────────────────────────────────
        entity_index = _load_entity_index(conn)
        if entity_index:
            items = [_annotate_item_entities(item, entity_index) for item in items]

        # Insert entity intro cards for unknown entities
        entity_knowledge = _load_entity_knowledge(conn)
        items = _build_entity_intro_items(items, entity_knowledge, conn)

        # Insert entity intro cards for freshly-captured entity_capture items
        # (review_count=0). Briefs the user on the entity's identity before the
        # first quiz question. Skipped when the shared_entities row has no
        # useful description — rich_answer still covers the gap post-grade.
        items = _build_entity_capture_intros(items, conn)

        # Nexus cards disabled — detection works (entities spanning 3+ curricula)
        # but cards lack synthesized content. Needs LLM-generated connection
        # insights before re-enabling. See _insert_nexus_cards().
        # items = _insert_nexus_cards(items, conn)

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

        # ── Knowledge profile stats ────────────────────────────────
        kp = {}
        try:
            kp['total_chunks'] = conn.execute('SELECT COUNT(*) FROM transcript_chunks').fetchone()[0]
            kp['chunks_by_type'] = {}
            for row in conn.execute('SELECT chunk_type, COUNT(*) as cnt FROM transcript_chunks GROUP BY chunk_type'):
                kp['chunks_by_type'][row['chunk_type']] = row['cnt']
            kp['total_node_links'] = conn.execute('SELECT COUNT(*) FROM chunk_node_links').fetchone()[0]
            kp['cross_node_links'] = conn.execute('SELECT COUNT(*) FROM chunk_node_links WHERE relevance < 1.0').fetchone()[0]
            kp['total_entity_links'] = conn.execute('SELECT COUNT(*) FROM chunk_entity_links').fetchone()[0]
            kp['unique_entities'] = conn.execute('SELECT COUNT(DISTINCT entity_name) FROM chunk_entity_links').fetchone()[0]
            kp['nodes_with_voice'] = conn.execute('SELECT COUNT(DISTINCT node_id) FROM chunk_node_links').fetchone()[0]

            # Domain portraits
            kp['portraits'] = []
            try:
                for row in conn.execute('''
                    SELECT dks.domain_id, dks.chunk_count, dks.node_count, dks.entity_count,
                           dks.version, dks.updated_at, cd.title as domain_title
                    FROM domain_knowledge_summaries dks
                    LEFT JOIN curriculum_domains cd ON cd.id = dks.domain_id
                    ORDER BY dks.chunk_count DESC
                ''').fetchall():
                    kp['portraits'].append(dict(row))
            except Exception:
                pass
        except Exception:
            pass  # tables might not exist yet

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
            'knowledge_profile': kp,
            'timeline': timeline[:30],
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }
    finally:
        if own:
            conn.close()


def get_native_stats(conn=None) -> dict:
    """Build statistics optimised for the native Stats tab.

    Returns structural card progress per domain, knowledge level distribution,
    activity heatmap (last 8 weeks), review counts by card type, and today's summary.
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        now_ms = int(time.time() * 1000)
        today_start_ms = now_ms - (now_ms % (24 * 60 * 60 * 1000))
        end_today_ms = today_start_ms + 24 * 60 * 60 * 1000

        # ── Today's summary ────────────────────────────────────────
        reviewed_today = conn.execute(
            'SELECT COUNT(*) FROM knowledge_items WHERE last_reviewed_at >= ?',
            (today_start_ms,)
        ).fetchone()[0]
        reviewed_today += conn.execute(
            'SELECT COUNT(*) FROM microlearning_cards WHERE last_reviewed_at >= ?',
            (today_start_ms,)
        ).fetchone()[0]
        # Structural positions reviewed today
        reviewed_today += conn.execute(
            'SELECT COUNT(*) FROM structural_positions WHERE last_reviewed_at >= ?',
            (today_start_ms,)
        ).fetchone()[0]

        due_today = conn.execute(
            'SELECT COUNT(*) FROM knowledge_items WHERE due_at <= ?',
            (end_today_ms,)
        ).fetchone()[0]

        # ── Structural card progress per domain ────────────────────
        structural_progress = []
        rows = conn.execute("""
            SELECT sc.domain_id, cd.title as domain_title,
                   COUNT(*) as total,
                   SUM(CASE WHEN sp.review_count > 0 THEN 1 ELSE 0 END) as reviewed
            FROM structural_positions sp
            JOIN structural_cards sc ON sc.id = sp.card_id
            LEFT JOIN curriculum_domains cd ON sc.domain_id = cd.id
            GROUP BY sc.domain_id
            ORDER BY reviewed DESC, total DESC
        """).fetchall()
        for r in rows:
            structural_progress.append({
                'domain_id': r['domain_id'],
                'domain_title': r['domain_title'] or r['domain_id'],
                'total': r['total'],
                'reviewed': r['reviewed'],
            })

        # Per card-type breakdown (for the card type chart)
        card_type_counts = {}
        for r in conn.execute("""
            SELECT sc.card_type, COUNT(*) as total,
                   SUM(CASE WHEN sp.review_count > 0 THEN 1 ELSE 0 END) as reviewed
            FROM structural_positions sp
            JOIN structural_cards sc ON sc.id = sp.card_id
            GROUP BY sc.card_type
        """).fetchall():
            card_type_counts[r['card_type']] = {
                'total': r['total'], 'reviewed': r['reviewed'],
            }

        # ── Knowledge level distribution per domain ────────────────
        knowledge_levels = []
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
            if node_count == 0:
                continue
            # Only include domains with any non-unknown knowledge
            if dist['mentioned'] + dist['engaged'] + dist['anchored'] == 0:
                continue
            knowledge_levels.append({
                'domain_id': domain_id,
                'title': meta.get('title', domain_id),
                'node_count': node_count,
                'distribution': dist,
            })
        # Sort by total known (non-unknown) descending
        knowledge_levels.sort(
            key=lambda d: d['distribution']['anchored'] + d['distribution']['engaged'] + d['distribution']['mentioned'],
            reverse=True,
        )

        # ── Activity heatmap (last 56 days / 8 weeks) ─────────────
        heatmap = {}
        for r in conn.execute("""
            SELECT date(created_at) as day, COUNT(*) as cnt
            FROM interaction_log
            WHERE created_at >= date('now', '-56 days')
            GROUP BY date(created_at)
            ORDER BY day
        """).fetchall():
            heatmap[r['day']] = r['cnt']

        # ── Review counts by card type (last 30 days) ─────────────
        review_by_type = {}
        for r in conn.execute("""
            SELECT COALESCE(card_type, 'unknown') as ct, COUNT(*) as cnt
            FROM interaction_log
            WHERE event IN ('review_result', 'review_answer', 'structural_grade', 'review_quiz_result')
              AND created_at >= date('now', '-30 days')
            GROUP BY card_type
        """).fetchall():
            review_by_type[r['ct']] = r['cnt']

        # Also count structural grading events with their card sub-types
        for r in conn.execute("""
            SELECT json_extract(extra, '$.card_type') as ct, COUNT(*) as cnt
            FROM interaction_log
            WHERE event = 'structural_grade'
              AND created_at >= date('now', '-30 days')
              AND extra IS NOT NULL
            GROUP BY ct
        """).fetchall():
            if r['ct']:
                review_by_type[f"structural_{r['ct']}"] = r['cnt']

        # ── Score distribution (all time) ──────────────────────────
        scores = {'knew': 0, 'partly': 0, 'missed': 0}
        for tbl in ('knowledge_items', 'microlearning_cards'):
            for r in conn.execute(
                f'SELECT last_score, COUNT(*) as cnt FROM {tbl} '
                'WHERE last_score IS NOT NULL GROUP BY last_score'
            ).fetchall():
                if r['last_score'] in scores:
                    scores[r['last_score']] += r['cnt']

        # ── Total item counts ──────────────────────────────────────
        ki_total = conn.execute('SELECT COUNT(*) FROM knowledge_items').fetchone()[0]
        ml_total = conn.execute(
            "SELECT COUNT(*) FROM microlearning_cards WHERE status = 'completed'"
        ).fetchone()[0]
        quiz_total = conn.execute('SELECT COUNT(*) FROM microlearning_quizzes').fetchone()[0]
        struct_total = conn.execute('SELECT COUNT(*) FROM structural_positions').fetchone()[0]

        return {
            'today': {
                'reviewed': reviewed_today,
                'due': due_today,
            },
            'structural_progress': structural_progress,
            'card_type_counts': card_type_counts,
            'knowledge_levels': knowledge_levels,
            'heatmap': heatmap,
            'review_by_type': review_by_type,
            'scores': scores,
            'totals': {
                'knowledge_items': ki_total,
                'microlearning_cards': ml_total,
                'quizzes': quiz_total,
                'structural_positions': struct_total,
            },
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


# ═════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE GROWTH TRACKING (Tier 1 — Passive)
# ═════════════════════════════════════════════════════════════════════════════


def backfill_knowledge_transitions(conn=None) -> int:
    """Seed knowledge_transitions from existing knowledge_states.

    Only runs if the table is empty (first time). Uses last_assessed timestamps
    so the growth chart reflects when knowledge was actually acquired.
    Returns number of transitions inserted.
    """
    own = conn is None
    if own:
        conn = get_connection()
    try:
        existing = conn.execute(
            'SELECT COUNT(*) FROM knowledge_transitions'
        ).fetchone()[0]
        if existing > 0:
            return 0

        rows = conn.execute(
            "SELECT domain_id, node_id, knowledge, last_assessed, source_summary "
            "FROM knowledge_states WHERE knowledge != 'unknown'"
        ).fetchall()

        count = 0
        KNOWLEDGE_ORDER = {'unknown': 0, 'mentioned': 1, 'engaged': 2, 'anchored': 3}
        for row in rows:
            ts = row['last_assessed']
            # Convert ISO timestamp to unix epoch
            try:
                if ts:
                    dt = datetime.fromisoformat(ts)
                    epoch = int(dt.timestamp())
                else:
                    epoch = int(time.time())
            except (ValueError, TypeError):
                epoch = int(time.time())

            sources = row['source_summary']
            if isinstance(sources, str):
                try:
                    sources = json.loads(sources)
                except (json.JSONDecodeError, TypeError):
                    sources = []
            source_name = sources[0] if sources else 'backfill'

            level = row['knowledge']
            level_idx = KNOWLEDGE_ORDER.get(level, 0)

            # Create transitions for each step: unknown→mentioned→engaged→anchored
            levels = ['unknown', 'mentioned', 'engaged', 'anchored']
            for i in range(1, level_idx + 1):
                conn.execute(
                    '''INSERT INTO knowledge_transitions
                       (node_id, domain_id, from_level, to_level, source, source_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (row['node_id'], row['domain_id'], levels[i - 1], levels[i],
                     source_name, None, epoch)
                )
                count += 1

        if own:
            conn.commit()
        return count
    finally:
        if own:
            conn.close()


def compute_network_metrics(domain_id: str, conn=None) -> dict:
    """Compute learner vs expert network similarity for a domain.

    Returns node_coverage, edge_overlap (Goldsmith C metric), density,
    and raw counts. Uses curriculum prerequisite edges as the expert graph.
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        curriculum = load_curriculum(domain_id, conn=conn)
        if not curriculum:
            return {}

        states = {}
        for r in conn.execute(
            "SELECT node_id, knowledge FROM knowledge_states WHERE domain_id = ?",
            (domain_id,)
        ).fetchall():
            states[r['node_id']] = r['knowledge']

        nodes = curriculum.get('nodes', [])
        nodes_total = len(nodes)
        nodes_known = 0
        expert_edges = set()
        learner_edges = set()

        for node in nodes:
            nid = node['id']
            known = states.get(nid, 'unknown') != 'unknown'
            if known:
                nodes_known += 1
            for prereq in node.get('prerequisites', []):
                expert_edges.add((prereq, nid))
                if known and states.get(prereq, 'unknown') != 'unknown':
                    learner_edges.add((prereq, nid))

        edges_total = len(expert_edges)
        edges_known = len(learner_edges)
        edge_overlap = edges_known / edges_total if edges_total > 0 else 0.0
        node_coverage = nodes_known / nodes_total if nodes_total > 0 else 0.0

        # Density: actual edges between known nodes / possible edges
        if nodes_known > 1:
            possible = nodes_known * (nodes_known - 1)
            density = edges_known / possible if possible > 0 else 0.0
        else:
            density = 0.0

        return {
            'domain_id': domain_id,
            'node_coverage': round(node_coverage, 4),
            'edge_overlap': round(edge_overlap, 4),
            'density': round(density, 4),
            'nodes_known': nodes_known,
            'nodes_total': nodes_total,
            'edges_known': edges_known,
            'edges_total': edges_total,
        }
    finally:
        if own:
            conn.close()


def snapshot_network_metrics(conn=None) -> list[dict]:
    """Compute and store network metrics for all domains. Returns the metrics."""
    own = conn is None
    if own:
        conn = get_connection()
    try:
        results = []
        for meta in list_curricula(conn=conn):
            domain_id = meta['id']
            metrics = compute_network_metrics(domain_id, conn=conn)
            if not metrics:
                continue
            conn.execute(
                '''INSERT INTO network_metrics_log
                   (domain_id, node_coverage, edge_overlap, density,
                    nodes_known, nodes_total, edges_known, edges_total)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (domain_id, metrics['node_coverage'], metrics['edge_overlap'],
                 metrics['density'], metrics['nodes_known'], metrics['nodes_total'],
                 metrics['edges_known'], metrics['edges_total'])
            )
            results.append(metrics)
        if own:
            conn.commit()
        return results
    finally:
        if own:
            conn.close()


def get_knowledge_growth_data(conn=None) -> dict:
    """Build all data for the knowledge growth visualization page.

    Returns:
        - transitions: cumulative node counts at each level over time per domain
        - network_metrics: time series of edge_overlap, node_coverage, density per domain
        - review_performance: weekly score distributions
        - stability_trends: average stability per domain over time
        - current: live-computed current metrics per domain
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        # ── Backfill transitions if needed (first call after deploy) ──
        try:
            count = conn.execute('SELECT COUNT(*) FROM knowledge_transitions').fetchone()[0]
            if count == 0:
                # Need write access for backfill — use separate connection
                wconn = get_connection()
                try:
                    backfill_knowledge_transitions(conn=wconn)
                finally:
                    wconn.close()
        except Exception:
            pass

        # ── 1. Knowledge transitions timeline ──
        transitions = []
        try:
            rows = conn.execute(
                '''SELECT domain_id, to_level, created_at
                   FROM knowledge_transitions
                   ORDER BY created_at ASC'''
            ).fetchall()
            transitions = [
                {'domain_id': r['domain_id'], 'to_level': r['to_level'],
                 'created_at': r['created_at']}
                for r in rows
            ]
        except Exception:
            pass

        # ── 2. Network metrics history ──
        network_history = []
        try:
            rows = conn.execute(
                '''SELECT domain_id, node_coverage, edge_overlap, density,
                          nodes_known, nodes_total, edges_known, edges_total, computed_at
                   FROM network_metrics_log
                   ORDER BY computed_at ASC'''
            ).fetchall()
            network_history = [dict(r) for r in rows]
        except Exception:
            pass

        # ── 3. Review performance (weekly score distributions) ──
        review_performance = []
        try:
            # Use interaction_log for grading events (post-session-60 data)
            rows = conn.execute(
                """SELECT
                    CAST(strftime('%s', created_at) AS INTEGER) / 604800 * 604800 as week_start,
                    score,
                    COUNT(*) as cnt
                FROM interaction_log
                WHERE event IN ('grade_review', 'grade_ml', 'grade_quiz')
                    AND score IS NOT NULL
                GROUP BY week_start, score
                ORDER BY week_start ASC"""
            ).fetchall()
            review_performance = [
                {'week_start': r[0], 'score': r[1], 'count': r[2]}
                for r in rows
            ]
        except Exception:
            pass

        # Fallback: use knowledge_items last_score if no interaction_log data
        if not review_performance:
            try:
                rows = conn.execute(
                    """SELECT
                        last_reviewed_at / 604800000 * 604800 as week_start,
                        last_score,
                        COUNT(*) as cnt
                    FROM knowledge_items
                    WHERE last_score IS NOT NULL AND last_reviewed_at IS NOT NULL
                    GROUP BY week_start, last_score
                    ORDER BY week_start ASC"""
                ).fetchall()
                review_performance = [
                    {'week_start': r[0], 'score': r[1], 'count': r[2]}
                    for r in rows
                ]
            except Exception:
                pass

        # ── 4. Stability trends per domain ──
        stability_trends = []
        try:
            rows = conn.execute(
                """SELECT ki.curriculum_domain,
                    ki.last_reviewed_at / 604800000 * 604800 as week_start,
                    AVG(ki.stability_days) as avg_stability,
                    COUNT(*) as item_count
                FROM knowledge_items ki
                WHERE ki.last_reviewed_at IS NOT NULL AND ki.stability_days > 0
                GROUP BY ki.curriculum_domain, week_start
                ORDER BY week_start ASC"""
            ).fetchall()
            stability_trends = [
                {'domain_id': r[0], 'week_start': r[1],
                 'avg_stability': round(r[2], 2), 'item_count': r[3]}
                for r in rows
            ]
        except Exception:
            pass

        # ── 5. Current metrics (live-computed) ──
        current = []
        for meta in list_curricula(conn=conn):
            domain_id = meta['id']
            metrics = compute_network_metrics(domain_id, conn=conn)
            if metrics:
                metrics['title'] = meta['title']
                # Add knowledge distribution
                dist = {'unknown': 0, 'mentioned': 0, 'engaged': 0, 'anchored': 0}
                try:
                    nodes = conn.execute(
                        '''SELECT cn.id, COALESCE(ks.knowledge, 'unknown') as knowledge
                           FROM curriculum_nodes cn
                           LEFT JOIN knowledge_states ks
                               ON cn.id = ks.node_id AND cn.domain_id = ks.domain_id
                           WHERE cn.domain_id = ?''',
                        (domain_id,)
                    ).fetchall()
                    for n in nodes:
                        dist[n['knowledge']] = dist.get(n['knowledge'], 0) + 1
                except Exception:
                    pass
                metrics['distribution'] = dist
                current.append(metrics)

        # ── 6. Domain metadata for labels ──
        domains = {}
        for meta in list_curricula(conn=conn):
            domains[meta['id']] = meta['title']

        return {
            'transitions': transitions,
            'network_history': network_history,
            'review_performance': review_performance,
            'stability_trends': stability_trends,
            'current': current,
            'domains': domains,
        }
    finally:
        if own:
            conn.close()
