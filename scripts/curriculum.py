"""
Curriculum generation, graph utilities, and elicitation.

Generates hierarchical curricula for humanities domains, maps books against them,
and runs adaptive "20 Questions" elicitation sessions.

Runtime knowledge state reads/writes are in curriculum_db.py (SQLite-backed).
"""

import json
import os
import math
import random
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from gemini_llm import call_llm
from curriculum_db import load_curriculum, list_curricula, load_knowledge_states, update_knowledge
from db import get_connection


def _call_opus(prompt: str, max_tokens: int = 32768, timeout: int = 1200) -> str | None:
    """Call Claude Opus for high-quality generation.

    1. Anthropic SDK if ANTHROPIC_* key set (servers, API credits).
    2. `claude -p` CLI with **API keys stripped from the child env** so the CLI uses
       Claude Code / Max subscription auth instead of billing the same exhausted API key.
    3. If ``PETRARCA_CURRICULUM_FALLBACK_MODEL`` is set (e.g. ``gpt-4o-mini``), ``call_llm`` as last resort when SDK and CLI both fail.
    """
    anthropic_key = os.environ.get('ANTHROPIC_KEY') or os.environ.get('ANTHROPIC_API_KEY')

    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key, timeout=600.0)
            with client.messages.stream(
                model='claude-opus-4-6',
                max_tokens=max_tokens,
                messages=[{'role': 'user', 'content': prompt}],
            ) as stream:
                return stream.get_final_text()
        except Exception as e:
            print(f'[curriculum] Anthropic SDK failed: {e}', flush=True)

    # Fallback: claude -p CLI — strip ANTHROPIC_* from env so CLI uses Max/subscription, not the API key wallet.
    if shutil.which('claude'):
        try:
            cmd = ['claude', '-p', '--tools', '', '--output-format', 'text',
                   '--model', 'opus', '--no-session-persistence']
            _strip = ('ANTHROPIC_API_KEY', 'ANTHROPIC_KEY', 'ANTHROPIC_AUTH_TOKEN')
            cli_env = {k: v for k, v in os.environ.items() if k not in _strip}
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=cli_env,
            )
            if proc.returncode == 0 and proc.stdout and proc.stdout.strip():
                print('[curriculum] claude CLI (subscription path) succeeded', flush=True)
                return proc.stdout.strip()
            out = (proc.stdout or '').strip()
            err = (proc.stderr or '').strip()
            combo = (out + '\n' + err).strip()[:1200]
            print(
                f'[curriculum] claude CLI: rc={proc.returncode} output={combo!r}',
                flush=True,
            )
        except Exception as e:
            print(f'[curriculum] claude CLI failed: {e}', flush=True)
    else:
        print('[curriculum] claude CLI not found on PATH', flush=True)

    fb = (os.environ.get('PETRARCA_CURRICULUM_FALLBACK_MODEL') or '').strip().lower()
    if fb and fb not in ('none', 'off', 'false', ''):
        try:
            raw = call_llm(
                prompt, model=fb, max_tokens=16384, response_mime_type='application/json',
            )
            if raw and str(raw).strip():
                print(
                    f'[curriculum] Fallback LLM ({fb}) — lower quality than Opus',
                    flush=True,
                )
                return str(raw).strip()
        except Exception as e:
            print(f'[curriculum] Fallback LLM failed: {e}', flush=True)

    return None

DATA_DIR = Path(os.environ.get('CURRICULUM_DIR', '/opt/petrarca/data/curricula'))
PHYSICAL_BOOKS_PATH = Path(os.environ.get('PHYSICAL_BOOKS_PATH', '/opt/petrarca/data/physical_books.json'))
SCRIPT_DIR = Path(__file__).resolve().parent
BOOK_RESEARCH_DIR = SCRIPT_DIR / "data" / "book_research"

# Ensure dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────

def make_node_id(domain_id: str, title: str) -> str:
    """Generate a stable node ID from domain + title."""
    slug = title.lower().strip()
    slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
    slug = '_'.join(slug.split()[:6])
    return f"{domain_id[:10]}_{slug}"


def make_domain_id(title: str) -> str:
    """Generate a domain ID from title."""
    slug = title.lower().strip()
    slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
    slug = '_'.join(slug.split()[:8])
    return slug


# ─────────────────────────────────────────────
# Curriculum generation
# ─────────────────────────────────────────────

CURRICULUM_GENERATION_PROMPT = """You are an expert curriculum designer for university-level humanities education.

Generate a hierarchical curriculum for an introductory course on: {domain}

STRUCTURE RULES:
- Maximum 4 levels deep: Area (level 1) → Topic (level 2) → Concept (level 3) → Detail (level 4, use sparingly)
- Aim for 50-80 leaf nodes total
- Each area should have 3-7 topics
- Topics can have 0-5 concepts (not every topic needs sub-concepts)
- Balance breadth across the domain — don't over-represent any single area

TITLE RULES:
- Level 1 (Area) titles can be thematic — they are organizational containers
- Level 2-3 titles MUST name specific people, works, events, places, or dates — not generic themes
  BAD: "Pioneering Painters", "Merchant Wealth and Banking Families", "Cultural Exchange"
  GOOD: "Masaccio and the Brancacci Chapel", "The Medici Bank and Florentine Politics", "Poggio Bracciolini at the Council of Constance (1414-1418)"
- Each title should be concrete enough that a student can say "I know about this specific thing" or "I don't"

FOR EACH NODE, provide:
- "title": Specific name following the title rules above
- "description": 2-3 sentences describing what "knowing this" means. Include specific names, dates, and works — not just thematic summaries.
  BAD: "You understand the role of banking in Renaissance culture and how wealth influenced artistic production."
  GOOD: "You know that Cosimo de' Medici founded the Platonic Academy by giving Marsilio Ficino a villa at Careggi in 1462, and that Ficino's Latin translations of Plato (completed 1484) became the standard European text for two centuries."
- "parent": Title of parent node (null for top-level areas)
- "level": 1 for Area, 2 for Topic, 3 for Concept, 4 for Detail
- "prerequisites": List of titles of nodes that should be known before this one (can be empty). Only include direct prerequisites, not transitive ones.
- "obscurity": 1-5 (1 = widely known by anyone with passing interest, 5 = specialist knowledge)
- "bloom_floor": The minimum level of understanding expected: "recognize" (know it exists), "explain" (understand the basics), or "analyze" (can discuss significance and connections)
- "date_start": integer — start year of the topic's time period. Negative for BCE (e.g., 734 BC = -734, 330 AD = 330). Area nodes should span the full range of their children.
- "date_end": integer — end year. Be as precise as the content allows. For undatable topics, use null.

GUIDELINES:
- Cover the major areas a well-designed introductory course would include
- Include political, social, cultural, intellectual, and economic dimensions
- Don't just list events chronologically — organize by theme and significance
- Prerequisites should reflect genuine intellectual dependencies: you can't understand Botticelli's mythological paintings without knowing about Ficino's Platonic Academy
- Obscurity ratings should reflect what an educated non-specialist would know vs. what requires specific study

Output as a JSON array of node objects. No markdown, just the JSON array."""


def generate_curriculum(domain: str, depth: str = "introductory", model: str = "opus") -> dict | None:
    """Generate a curriculum for a domain. Returns the full curriculum dict or None.

    Always uses Claude Opus by default — Gemini Flash produces poor quality curricula
    (vague titles, shallow descriptions). Use model='gemini-2.5-flash' only for testing.
    """
    prompt = CURRICULUM_GENERATION_PROMPT.format(domain=domain)

    if depth == "intermediate":
        prompt += "\n\nThis is an INTERMEDIATE level curriculum. Aim for 150-200 nodes with more specific detail."
    elif depth == "advanced":
        prompt += "\n\nThis is an ADVANCED level curriculum. Aim for 250-300+ nodes with specialist detail."

    if model == 'opus' or model.startswith('claude'):
        raw = _call_opus(prompt)
    else:
        # OpenAI chat completions cap completion tokens (e.g. 16k); avoid 32k here.
        raw = call_llm(prompt, model=model, max_tokens=16384,
                       response_mime_type="application/json")
    if not raw:
        return None

    # Strip markdown fences if present (Opus sometimes wraps JSON in ```json ... ```)
    raw = raw.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw.strip())
    # Extract JSON array if embedded in prose
    m = re.search(r'\[[\s\S]*\]', raw)
    if m:
        raw = m.group()

    try:
        nodes_raw = json.loads(raw)
    except json.JSONDecodeError:
        print(f"Failed to parse curriculum JSON: {raw[:200]}...", flush=True)
        return None

    if not isinstance(nodes_raw, list):
        print(f"Curriculum output is not a list: {type(nodes_raw)}", flush=True)
        return None

    domain_id = make_domain_id(domain)

    # Build nodes with IDs and resolve parent/prerequisite references
    title_to_id: dict[str, str] = {}
    nodes = []

    for raw_node in nodes_raw:
        title = raw_node.get("title", "").strip()
        if not title:
            continue
        node_id = make_node_id(domain_id, title)
        title_to_id[title] = node_id

        node_dict = {
            "id": node_id,
            "title": title,
            "description": raw_node.get("description", ""),
            "parent_title": raw_node.get("parent"),
            "parent_id": None,  # resolved below
            "level": raw_node.get("level", 1),
            "prerequisite_titles": raw_node.get("prerequisites", []),
            "prerequisites": [],  # resolved below
            "obscurity": raw_node.get("obscurity", 3),
            "bloom_floor": raw_node.get("bloom_floor", "recognize"),
        }
        if raw_node.get("date_start") is not None:
            node_dict["date_start"] = int(raw_node["date_start"])
        if raw_node.get("date_end") is not None:
            node_dict["date_end"] = int(raw_node["date_end"])
        nodes.append(node_dict)

    # Resolve references
    for node in nodes:
        parent_title = node.pop("parent_title", None)
        if parent_title and parent_title in title_to_id:
            node["parent_id"] = title_to_id[parent_title]

        prereq_titles = node.pop("prerequisite_titles", [])
        node["prerequisites"] = [
            title_to_id[t] for t in prereq_titles if t in title_to_id
        ]

    curriculum = {
        "id": domain_id,
        "title": domain,
        "description": f"Introductory curriculum for {domain}",
        "depth": depth,
        "generated_at": datetime.now().isoformat(),
        "version": 1,
        "node_count": len(nodes),
        "nodes": nodes,
    }

    # Save JSON
    path = DATA_DIR / f"{domain_id}.json"
    with open(path, 'w') as f:
        json.dump(curriculum, f, indent=2)

    # Insert into SQLite
    try:
        conn = get_connection()
        existing = conn.execute('SELECT id FROM curriculum_domains WHERE id = ?', (domain_id,)).fetchone()
        if not existing:
            conn.execute(
                'INSERT INTO curriculum_domains (id, title, description, depth, generated_at, node_count) '
                'VALUES (?,?,?,?,?,?)',
                (domain_id, domain, f"Introductory curriculum for {domain}",
                 depth, curriculum['generated_at'], len(nodes))
            )
        for node in nodes:
            conn.execute(
                'INSERT OR IGNORE INTO curriculum_nodes '
                '(id, domain_id, title, description, parent_id, level, obscurity, bloom_floor, date_start, date_end) '
                'VALUES (?,?,?,?,?,?,?,?,?,?)',
                (node['id'], domain_id, node['title'], node.get('description', ''),
                 node.get('parent_id'), node.get('level', 1),
                 node.get('obscurity', 3), node.get('bloom_floor', 'recognize'),
                 node.get('date_start'), node.get('date_end'))
            )
            for prereq_id in node.get('prerequisites', []):
                conn.execute(
                    'INSERT OR IGNORE INTO curriculum_prerequisites (domain_id, node_id, prerequisite_id, strength) '
                    'VALUES (?,?,?,?)',
                    (domain_id, node['id'], prereq_id, 1.0)
                )
        conn.commit()
        conn.close()
        print(f"[curriculum] Inserted into SQLite: {domain_id} ({len(nodes)} nodes)", flush=True)
    except Exception as e:
        print(f"[curriculum] SQLite insert failed (JSON saved): {e}", flush=True)

    print(f"Generated curriculum '{domain}': {len(nodes)} nodes, saved to {path}", flush=True)
    return curriculum



# load_curriculum() and list_curricula() imported from curriculum_db (SQLite-backed)


# ─────────────────────────────────────────────
# Book-to-curriculum mapping
# ─────────────────────────────────────────────

BOOK_MAPPING_PROMPT = """You are mapping a book's content against a curriculum to determine which topics the book covers.

BOOK:
Title: {title}
Author: {author}
Topics: {topics}
Thesis: {thesis}
Key terms: {key_terms}

CHAPTERS WITH CONTENT:
{chapters}

CURRICULUM NODES (the topics we want to map against):
{curriculum_nodes}

For each curriculum node that this book covers, output a JSON object with:
- "node_title": exact title from the curriculum
- "coverage": "surface" (mentions it briefly), "moderate" (covers it meaningfully), or "deep" (substantial coverage)
- "evidence": Brief explanation of why you think this book covers this topic, referencing specific chapters where possible

Only include nodes the book actually covers — don't guess. If uncertain, use "surface" coverage.

Output as a JSON array. No markdown, just the JSON array."""


def _load_book(book_id: str) -> dict | None:
    """Load a book by ID. Tries SQLite first, falls back to JSON."""
    try:
        from db import get_connection, BOOK_JSON_FIELDS
        conn = get_connection(readonly=True)
        row = conn.execute('SELECT * FROM physical_books WHERE id = ?', (book_id,)).fetchone()
        conn.close()
        if row:
            book = dict(row)
            for f in BOOK_JSON_FIELDS:
                if isinstance(book.get(f), str):
                    try:
                        book[f] = json.loads(book[f])
                    except (json.JSONDecodeError, TypeError):
                        pass
            return book
    except Exception:
        pass

    # Fallback: JSON file
    if PHYSICAL_BOOKS_PATH.exists():
        with open(PHYSICAL_BOOKS_PATH) as f:
            books_data = json.load(f)
        for b in books_data.get("books", []):
            if b.get("id") == book_id:
                return b
    return None


def _load_book_research(book_id: str) -> dict | None:
    """Load book research data (thesis, chapter summaries, claims, key terms)."""
    research_path = BOOK_RESEARCH_DIR / f"{book_id}.json"
    if research_path.exists():
        with open(research_path) as f:
            return json.load(f)
    return None


def _format_chapters_with_research(book: dict, research: dict | None) -> str:
    """Format chapter listing, enriched with research data when available."""
    chapters = book.get("chapters", [])
    if not chapters:
        return "No chapters available"

    chapter_research = research.get("chapter_research", {}) if research else {}
    lines = []
    for ch in chapters:
        num = ch.get("number", "?")
        title = ch.get("title", "?")
        cr = chapter_research.get(str(num), {})
        if cr:
            summary = cr.get("summary", "")
            claims = cr.get("claims", [])
            terms = cr.get("key_terms", [])
            line = f"Ch {num}: {title}"
            if summary:
                line += f"\n  Summary: {summary}"
            if claims:
                line += f"\n  Key claims: {'; '.join(claims[:4])}"
            if terms:
                line += f"\n  Terms: {', '.join(terms[:5])}"
            lines.append(line)
        else:
            lines.append(f"Ch {num}: {title}")

    return "\n".join(lines)


def map_book_to_curriculum(book_id: str, domain_id: str) -> list[dict] | None:
    """Map a book's content against a curriculum. Returns list of mappings."""
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return None

    book = _load_book(book_id)
    if not book:
        return None

    # Format curriculum nodes for the prompt
    node_lines = []
    title_to_id = {}
    for node in curriculum["nodes"]:
        indent = "  " * (node["level"] - 1)
        node_lines.append(f"{indent}- {node['title']}: {node['description'][:100]}")
        title_to_id[node["title"]] = node["id"]

    # Load book research (thesis, chapter summaries, claims)
    research = _load_book_research(book_id)
    thesis = research.get("thesis", "") if research else ""
    key_terms = ", ".join(
        t.get("term", "") for t in (research.get("key_terms", []) if research else [])[:20]
    )

    # Format chapters enriched with research data
    chapters_text = _format_chapters_with_research(book, research)

    prompt = BOOK_MAPPING_PROMPT.format(
        title=book.get("title", "Unknown"),
        author=book.get("author", "Unknown"),
        topics=", ".join(book.get("topics", [])),
        chapters=chapters_text,
        thesis=thesis or "Not available",
        key_terms=key_terms or "Not available",
        curriculum_nodes="\n".join(node_lines),
    )

    raw = call_llm(prompt, model="gemini-2.5-flash", max_tokens=8192,
                   response_mime_type="application/json")
    if not raw:
        return None

    try:
        mappings_raw = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(mappings_raw, list):
        return None

    # Resolve titles to IDs and update knowledge states
    mappings = []
    book_significance = book.get("significance", "read")
    confidence_map = {
        ("essential", "deep"): 0.9,
        ("essential", "moderate"): 0.8,
        ("essential", "surface"): 0.6,
        ("read", "deep"): 0.8,
        ("read", "moderate"): 0.65,
        ("read", "surface"): 0.45,
        ("skimmed", "deep"): 0.6,
        ("skimmed", "moderate"): 0.4,
        ("skimmed", "surface"): 0.25,
    }

    for m in mappings_raw:
        node_title = m.get("node_title", "")
        if node_title not in title_to_id:
            continue
        node_id = title_to_id[node_title]
        coverage = m.get("coverage", "surface")
        confidence = confidence_map.get((book_significance, coverage), 0.5)

        mappings.append({
            "node_id": node_id,
            "node_title": node_title,
            "coverage": coverage,
            "evidence": m.get("evidence", ""),
            "book_id": book_id,
            "confidence": confidence,
        })

        # Update knowledge state
        update_knowledge(
            domain_id, node_id,
            knowledge="mentioned",
            confidence=confidence,
            source=f"book:{book_id}",
        )

    # Save mappings
    mappings_path = DATA_DIR / f"mappings_{domain_id}_{book_id}.json"
    with open(mappings_path, 'w') as f:
        json.dump(mappings, f, indent=2)

    print(f"Mapped book '{book.get('title')}' → {len(mappings)} curriculum nodes", flush=True)
    return mappings


def get_book_curriculum_context(book_id: str) -> dict:
    """Get all curriculum context for a book: mappings, knowledge states, cross-book connections.

    Returns a dict ready to send to the client with everything needed to render
    curriculum-aware book features.
    """
    # Find all mapping files for this book
    domains = []
    for path in DATA_DIR.glob(f"mappings_*_{book_id}.json"):
        with open(path) as f:
            mappings = json.load(f)
        # Extract domain_id from filename: mappings_{domain_id}_{book_id}.json
        stem = path.stem  # mappings_domain_id_book_id
        domain_id = stem.replace("mappings_", "").replace(f"_{book_id}", "")
        curriculum = load_curriculum(domain_id)
        if not curriculum:
            continue
        states = load_knowledge_states(domain_id)

        # Annotate mappings with knowledge state and node description
        node_map = {n["id"]: n for n in curriculum["nodes"]}
        annotated = []
        for m in mappings:
            node = node_map.get(m["node_id"], {})
            state = states.get(m["node_id"], {})
            annotated.append({
                "node_id": m["node_id"],
                "node_title": m["node_title"],
                "coverage": m["coverage"],
                "evidence": m.get("evidence", ""),
                "knowledge": state.get("knowledge", "unknown"),
                "interest": state.get("interest", "none"),
                "confidence": state.get("confidence", 0.0),
                "description": node.get("description", ""),
            })

        # Find other books mapping to the same domain
        cross_books = []
        for other_path in DATA_DIR.glob(f"mappings_{domain_id}_*.json"):
            other_book_id = other_path.stem.replace(f"mappings_{domain_id}_", "")
            if other_book_id == book_id:
                continue
            with open(other_path) as f:
                other_mappings = json.load(f)
            # Find overlapping nodes
            my_node_ids = {m["node_id"] for m in mappings}
            for om in other_mappings:
                if om["node_id"] in my_node_ids:
                    cross_books.append({
                        "node_id": om["node_id"],
                        "node_title": om["node_title"],
                        "other_book_id": other_book_id,
                        "other_coverage": om["coverage"],
                    })

        # Resolve other book titles
        books_data = {}
        if PHYSICAL_BOOKS_PATH.exists():
            with open(PHYSICAL_BOOKS_PATH) as f:
                books_data = json.load(f)
        book_titles = {b["id"]: b.get("title", "Unknown") for b in books_data.get("books", [])}
        for cb in cross_books:
            cb["other_book_title"] = book_titles.get(cb["other_book_id"], cb["other_book_id"])

        domains.append({
            "domain_id": domain_id,
            "domain_title": curriculum.get("title", domain_id),
            "node_count": len(curriculum["nodes"]),
            "mappings": annotated,
            "cross_book_connections": cross_books,
        })

    return {"domains": domains}


# ─────────────────────────────────────────────
# Gap analysis
# ─────────────────────────────────────────────

def get_coverage_report(domain_id: str) -> dict | None:
    """Generate a coverage report for a curriculum domain."""
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return None

    states = load_knowledge_states(domain_id)
    nodes = curriculum["nodes"]

    # Categorize nodes
    known = []
    mentioned = []
    engaged = []
    anchored = []
    unknown = []
    curious = []
    core_interest = []

    for node in nodes:
        state = states.get(node["id"], {})
        knowledge = state.get("knowledge", "unknown")
        interest = state.get("interest", "none")

        node_summary = {
            "id": node["id"],
            "title": node["title"],
            "level": node["level"],
            "knowledge": knowledge,
            "interest": interest,
            "confidence": state.get("confidence", 0.0),
            "sources": state.get("sources", []),
        }

        if knowledge == "anchored":
            anchored.append(node_summary)
        elif knowledge == "engaged":
            engaged.append(node_summary)
        elif knowledge == "mentioned":
            mentioned.append(node_summary)
        else:
            unknown.append(node_summary)

        if interest == "curious":
            curious.append(node_summary)
        elif interest == "core":
            core_interest.append(node_summary)

    # Find "ready to learn" gaps: unknown nodes whose prerequisites are all known
    ready_to_learn = []
    known_ids = {n["id"] for n in anchored + engaged + mentioned}
    for node in nodes:
        state = states.get(node["id"], {})
        if state.get("knowledge", "unknown") != "unknown":
            continue
        prereqs = node.get("prerequisites", [])
        if all(p in known_ids for p in prereqs):
            ready_to_learn.append({
                "id": node["id"],
                "title": node["title"],
                "level": node["level"],
                "prerequisites_met": True,
            })

    total = len(nodes)
    covered = len(anchored) + len(engaged) + len(mentioned)

    return {
        "domain_id": domain_id,
        "title": curriculum["title"],
        "total_nodes": total,
        "covered_nodes": covered,
        "coverage_percent": round(100 * covered / total) if total > 0 else 0,
        "by_state": {
            "anchored": len(anchored),
            "engaged": len(engaged),
            "mentioned": len(mentioned),
            "unknown": len(unknown),
        },
        "anchored": anchored,
        "engaged": engaged,
        "mentioned": mentioned,
        "unknown": unknown,
        "curious": curious,
        "core_interest": core_interest,
        "ready_to_learn": ready_to_learn[:20],
    }


# ─────────────────────────────────────────────
# Entity tagging & index
# ─────────────────────────────────────────────

_ENTITY_TAG_PROMPT = """Extract structured entities from these curriculum nodes.
For each node return: persons (named historical individuals), places (cities, regions, empires, islands),
events (named battles, conquests, treaties, councils), and time_span [start_year, end_year] as integers
(negative = BCE). Use existing date_start/date_end if provided and reasonable; infer from context otherwise.
Omit fields that are empty rather than returning empty arrays.

Nodes (JSON):
{nodes_json}

Return a JSON array with one object per node, in the same order:
[{{"id":"...","persons":[],"places":[],"events":[],"time_span":[-480,-480]}}, ...]
Only output JSON, no prose."""


def tag_curriculum_entities(domain_id: str, force: bool = False) -> int:
    """Tag all nodes in a curriculum with persons/places/events/time_span.

    Skips nodes that already have an 'entities' field unless force=True.
    Uses Gemini Flash in batches of 12 nodes. Returns count of nodes tagged.
    """
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return 0

    nodes = curriculum['nodes']
    to_tag = [n for n in nodes if force or 'entities' not in n]
    if not to_tag:
        return 0

    tagged = 0
    batch_size = 12

    for i in range(0, len(to_tag), batch_size):
        batch = to_tag[i:i + batch_size]
        batch_input = [
            {
                'id': n['id'],
                'title': n['title'],
                'description': n.get('description', '')[:300],
                'date_start': n.get('date_start'),
                'date_end': n.get('date_end'),
            }
            for n in batch
        ]
        prompt = _ENTITY_TAG_PROMPT.format(nodes_json=json.dumps(batch_input, indent=2))
        raw = call_llm(prompt, max_tokens=4096, response_mime_type='application/json')
        if not raw:
            continue

        try:
            text = raw.strip()
            if text.startswith('```'):
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'\s*```$', '', text.strip())
            m = re.search(r'\[[\s\S]*\]', text)
            results = json.loads(m.group() if m else text)
        except Exception as e:
            print(f'[curriculum] entity tag parse error: {e}', flush=True)
            continue

        result_by_id = {r['id']: r for r in results if isinstance(r, dict)}
        for node in batch:
            r = result_by_id.get(node['id'], {})
            entities = {}
            if r.get('persons'):
                entities['persons'] = r['persons']
            if r.get('places'):
                entities['places'] = r['places']
            if r.get('events'):
                entities['events'] = r['events']
            # time_span: prefer existing date_start/date_end, fall back to LLM
            ts = node.get('date_start'), node.get('date_end')
            if ts[0] is not None:
                entities['time_span'] = [ts[0], ts[1] if ts[1] is not None else ts[0]]
            elif r.get('time_span') and len(r['time_span']) == 2:
                entities['time_span'] = r['time_span']
            node['entities'] = entities
            tagged += 1

    # Save updated curriculum
    path = DATA_DIR / f'{domain_id}.json'
    with open(path, 'w') as f:
        json.dump(curriculum, f, indent=2)

    print(f'[curriculum] Tagged {tagged} nodes in {domain_id}', flush=True)
    return tagged


_PLACE_HIERARCHY_PROMPT = """Build a place hierarchy for these historical place names.
For each place, assign:
- "parent": the broader polity/region it belongs to (e.g. Athens → Ancient Greece, Syracuse → Sicily)
- "type": one of "city", "city-state", "island", "region", "empire", "caliphate", "kingdom", "peninsula"

Use historically accurate groupings, not modern countries (e.g. use "Ancient Greece" not "Greece",
"Byzantine Empire" not "Turkey"). Top-level nodes (Sicily, Ancient Greece, Byzantine Empire, etc.)
should have parent "Mediterranean" or "Middle East" as appropriate.

Places: {places_json}

Return JSON object: {{"Athens": {{"parent": "Ancient Greece", "type": "city"}}, ...}}
Only output JSON."""


def build_place_hierarchy(places: list[str]) -> dict:
    """Ask Opus to build a parent hierarchy for a list of place names."""
    if not places:
        return {}
    prompt = _PLACE_HIERARCHY_PROMPT.format(places_json=json.dumps(sorted(set(places))))
    raw = _call_opus(prompt, max_tokens=4096)
    if not raw:
        return {}
    try:
        text = raw.strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text.strip())
        m = re.search(r'\{[\s\S]*\}', text)
        return json.loads(m.group() if m else text)
    except Exception as e:
        print(f'[curriculum] place hierarchy parse error: {e}', flush=True)
        return {}


def build_entity_index() -> dict:
    """Build an inverted index over all entity-tagged curriculum nodes.

    Returns:
        {
          nodes: [...all nodes with entities],
          persons_index: {name: [node_id, ...]},
          places_index: {name: [node_id, ...]},
          events_index: {name: [node_id, ...]},
          place_hierarchy: {place: {parent, type}},
          curricula: [...],
        }
    Saves to DATA_DIR/entity_index.json and returns the dict.
    """
    curricula_list = list_curricula()
    all_nodes = []
    curricula_meta = []
    persons_idx: dict[str, list] = {}
    places_idx: dict[str, list] = {}
    events_idx: dict[str, list] = {}
    all_places: list[str] = []

    # Build a lookup of entity data from JSON files (entity tags live in JSON, not SQLite)
    _json_entities: dict[str, dict[str, dict]] = {}  # domain_id -> node_id -> entities
    for json_path in DATA_DIR.glob('*.json'):
        try:
            raw = json.loads(json_path.read_text())
            if not isinstance(raw, dict) or 'id' not in raw or 'nodes' not in raw:
                continue
            did = raw['id']
            _json_entities[did] = {}
            for n in raw.get('nodes', []):
                if 'entities' in n:
                    _json_entities[did][n['id']] = n['entities']
        except Exception:
            continue

    for meta in curricula_list:
        domain_id = meta['id']
        curriculum = load_curriculum(domain_id)
        if not curriculum:
            continue
        states = load_knowledge_states(domain_id)
        short_name = domain_id.split('_')[0]
        curricula_meta.append({
            'id': domain_id,
            'short_name': short_name,
            'title': curriculum.get('title', domain_id),
        })

        json_ents = _json_entities.get(domain_id, {})
        for node in curriculum.get('nodes', []):
            state = states.get(node['id'], {})
            # Merge: prefer JSON entity data (tags written there), fall back to SQLite node data
            entities = json_ents.get(node['id'], node.get('entities', {}))

            flat = {
                'id': node['id'],
                'title': node['title'],
                'description': node.get('description', '')[:300],
                'curriculum': domain_id,
                'level': node.get('level', 2),
                'time_span': entities.get('time_span') or (
                    [node['date_start'], node.get('date_end', node['date_start'])]
                    if node.get('date_start') is not None else None
                ),
                'entities': entities,
                'knowledge': state.get('knowledge', 'unknown'),
                'interest': state.get('interest', 'none'),
                'review_count': 0,
            }
            all_nodes.append(flat)

            nid = node['id']
            for person in entities.get('persons', []):
                persons_idx.setdefault(person, []).append(nid)
            for place in entities.get('places', []):
                places_idx.setdefault(place, []).append(nid)
                all_places.append(place)
            for event in entities.get('events', []):
                events_idx.setdefault(event, []).append(nid)

    # Build / load place hierarchy
    hierarchy_path = DATA_DIR / 'place_hierarchy.json'
    if hierarchy_path.exists():
        place_hierarchy = json.loads(hierarchy_path.read_text())
        # Add any new places not yet in hierarchy
        new_places = [p for p in set(all_places) if p not in place_hierarchy]
        if new_places:
            new_hier = build_place_hierarchy(new_places)
            place_hierarchy.update(new_hier)
            hierarchy_path.write_text(json.dumps(place_hierarchy, indent=2))
    else:
        place_hierarchy = build_place_hierarchy(list(set(all_places)))
        hierarchy_path.write_text(json.dumps(place_hierarchy, indent=2))

    # Expand places_index: if you look up "Ancient Greece", also return nodes tagged
    # with child places (Athens, Sparta, etc.)
    def get_children(parent: str) -> list[str]:
        return [p for p, v in place_hierarchy.items() if v.get('parent') == parent]

    expanded_places_idx: dict[str, list] = {}
    for place, node_ids in places_idx.items():
        expanded_places_idx[place] = list(node_ids)
    # Add parent-level entries
    for place, meta in place_hierarchy.items():
        parent = meta.get('parent')
        if parent and place in places_idx:
            expanded_places_idx.setdefault(parent, [])
            for nid in places_idx[place]:
                if nid not in expanded_places_idx[parent]:
                    expanded_places_idx[parent].append(nid)

    # Build name → entity_id mapping from shared_entities
    name_to_entity_id: dict[str, str] = {}
    try:
        from db import get_connection
        conn = get_connection(readonly=True)
        rows = conn.execute('SELECT entity_id, name FROM shared_entities').fetchall()
        for r in rows:
            name_to_entity_id[r['name']] = r['entity_id']
        conn.close()
    except Exception:
        pass

    index = {
        'nodes': all_nodes,
        'persons_index': persons_idx,
        'places_index': expanded_places_idx,
        'events_index': events_idx,
        'place_hierarchy': place_hierarchy,
        'curricula': curricula_meta,
        'name_to_entity_id': name_to_entity_id,
    }

    index_path = DATA_DIR / 'entity_index.json'
    index_path.write_text(json.dumps(index))
    print(f'[curriculum] Entity index: {len(all_nodes)} nodes, '
          f'{len(persons_idx)} persons, {len(expanded_places_idx)} places, '
          f'{len(events_idx)} events', flush=True)
    return index


def get_entity_index() -> dict:
    """Load entity index from cache, or build if missing."""
    path = DATA_DIR / 'entity_index.json'
    if path.exists():
        return json.loads(path.read_text())
    return build_entity_index()


# ─────────────────────────────────────────────
# Curriculum graph data
# ─────────────────────────────────────────────

def get_curriculum_graph_data(conn=None) -> dict:
    """Build combined graph data across all curricula for visualization.

    Returns nodes (curriculum nodes + entity nexus nodes), directed links
    (prerequisites, hierarchy, entity connections), book mappings per node,
    and review counts per node if a DB connection is provided.
    """
    nodes = []
    links = []
    curricula_meta = {}
    node_id_set = set()  # deduplicate

    # Load review counts from knowledge_items if DB available
    review_counts = {}
    if conn:
        try:
            rows = conn.execute(
                'SELECT curriculum_node_id, review_count, stability_days, due_at FROM knowledge_items'
            ).fetchall()
            for row in rows:
                review_counts[row[0]] = {
                    'review_count': row[1],
                    'stability_days': row[2],
                    'due_at': row[3],
                }
        except Exception:
            pass

    for meta in list_curricula():
        domain_id = meta['id']
        curriculum = load_curriculum(domain_id)
        if not curriculum:
            continue

        states = load_knowledge_states(domain_id)
        short_name = domain_id.split('_')[0]  # 'sicily', 'ancient', 'roman', ...
        curricula_meta[domain_id] = {
            'id': domain_id,
            'short_name': short_name,
            'title': curriculum.get('title', domain_id),
            'node_count': len(curriculum.get('nodes', [])),
        }

        for node in curriculum.get('nodes', []):
            node_id = node['id']
            if node_id in node_id_set:
                continue
            node_id_set.add(node_id)

            state = states.get(node_id, {})
            ri = review_counts.get(node_id, {})
            import time as _time
            now = int(_time.time())

            graph_node = {
                'id': node_id,
                'title': node['title'],
                'description': node.get('description', '')[:400],
                'curriculum': domain_id,
                'level': node.get('level', 2),
                'parent_id': node.get('parent_id'),
                'prerequisites': node.get('prerequisites', []),
                'knowledge': state.get('knowledge', 'unknown'),
                'interest': state.get('interest', 'none'),
                'confidence': state.get('confidence', 0.0),
                'date_start': node.get('date_start'),
                'date_end': node.get('date_end'),
                'obscurity': node.get('obscurity', 2),
                'review_count': ri.get('review_count', 0),
                'stability_days': ri.get('stability_days', 0),
                'due_soon': ri.get('due_at', 0) > 0 and ri.get('due_at', 0) <= now + 86400,
                'books': [],
            }
            nodes.append(graph_node)

            # Prerequisite links
            for prereq_id in node.get('prerequisites', []):
                links.append({'source': prereq_id, 'target': node_id, 'type': 'prerequisite'})

            # Hierarchy link
            if node.get('parent_id'):
                links.append({'source': node['parent_id'], 'target': node_id, 'type': 'hierarchy'})

    # Index nodes for annotation
    node_index = {n['id']: n for n in nodes}

    # Book mappings: scan mappings_*.json files
    for mf in sorted(DATA_DIR.glob('mappings_*.json')):
        try:
            data = json.loads(mf.read_text())
            book_id = data.get('book_id', mf.stem)
            book_title = data.get('book_title', book_id)
            for mapping in data.get('mappings', []):
                for nid in mapping.get('node_ids', []):
                    if nid in node_index:
                        book_entry = {'id': book_id, 'title': book_title}
                        existing = node_index[nid]['books']
                        if not any(b['id'] == book_id for b in existing):
                            existing.append(book_entry)
        except Exception:
            continue

    # Cross-curriculum entity nodes
    entities_path = DATA_DIR / 'cross_curriculum_entities.json'
    entities = []
    if entities_path.exists():
        try:
            entities = json.loads(entities_path.read_text())
        except Exception:
            pass

    for entity in entities:
        entity_node_id = f"entity:{entity['entity_name']}"
        curricula_covered = list({ref['curriculum'] for ref in entity.get('nodes', [])})
        nodes.append({
            'id': entity_node_id,
            'title': entity['entity_name'],
            'description': f"{entity.get('entity_type', 'entity').title()} — appears in {len(entity.get('nodes', []))} curriculum nodes across {len(curricula_covered)} curricula",
            'curriculum': None,
            'is_entity': True,
            'entity_type': entity.get('entity_type'),
            'date_range': entity.get('date_range'),
            'level': 0,
            'knowledge': 'unknown',
            'interest': 'none',
            'curricula_covered': curricula_covered,
        })
        for ref in entity.get('nodes', []):
            nid = ref.get('node_id')
            if nid:
                links.append({
                    'source': entity_node_id,
                    'target': nid,
                    'type': 'entity',
                    'lens': ref.get('lens', ''),
                })

    # Remove links pointing to unknown nodes
    known_ids = {n['id'] for n in nodes}
    links = [l for l in links if l['source'] in known_ids and l['target'] in known_ids]

    return {
        'nodes': nodes,
        'links': links,
        'curricula': list(curricula_meta.values()),
        'entities': entities,
    }


# ─────────────────────────────────────────────
# 20 Questions knowledge elicitation
# ─────────────────────────────────────────────

def _entropy(probs: list[float]) -> float:
    """Shannon entropy of a probability distribution."""
    return -sum(p * math.log2(p) for p in probs if p > 0)


def _information_gain(p_knows: float) -> float:
    """Expected information gain from asking about a node with P(knows)=p_knows.
    Maximum when p_knows = 0.5 (maximum uncertainty)."""
    if p_knows <= 0 or p_knows >= 1:
        return 0.0
    return _entropy([p_knows, 1 - p_knows])


ELICITATION_QUESTION_PROMPT = """You are helping someone map what they know about {domain}.
This is NOT a test — it's a friendly conversation to understand their existing knowledge.

Based on the conversation so far and what we know about their knowledge, generate the next question.

CURRENT KNOWLEDGE MAP:
{knowledge_summary}

TARGET NODE TO PROBE:
Title: {node_title}
Description: {node_description}
Level: {level_desc}

QUESTION TYPE: {question_type}

CONVERSATION HISTORY:
{history}

GUIDELINES:
- Frame as curiosity, not examination
- If this is a recognition question, a simple "Have you encountered..." or "Are you familiar with..." works
- If this is a comparison question, compare two topics the user might know about at different levels
- If this is a scoping question, ask about specific aspects (when, where, who, significance)
- Keep it conversational and natural
- Include a brief (2-sentence) "card flip" summary of the topic that will be shown after the user answers

Output JSON with:
- "question": The question to ask
- "card_summary": 2-3 sentence summary of this topic (shown after user answers, like flipping a card)
- "follow_up_if_yes": A brief follow-up question to probe depth (optional)"""


def start_elicitation(domain_id: str) -> dict | None:
    """Start a new 20Q elicitation session for a curriculum domain."""
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return None

    states = load_knowledge_states(domain_id)

    # Calculate initial beliefs based on existing knowledge
    beliefs = {}
    for node in curriculum["nodes"]:
        state = states.get(node["id"], {})
        knowledge = state.get("knowledge", "unknown")

        if knowledge == "anchored":
            beliefs[node["id"]] = 0.95
        elif knowledge == "engaged":
            beliefs[node["id"]] = 0.85
        elif knowledge == "mentioned":
            beliefs[node["id"]] = state.get("confidence", 0.6)
        else:
            # Prior based on obscurity: common topics more likely known
            obscurity = node.get("obscurity", 3)
            beliefs[node["id"]] = max(0.05, 0.5 - obscurity * 0.08)

    session = {
        "id": f"elicit_{domain_id}_{int(time.time())}",
        "domain_id": domain_id,
        "started_at": datetime.now().isoformat(),
        "beliefs": beliefs,
        "history": [],
        "questions_asked": 0,
        "nodes_assessed": [],
    }

    # Generate first question (modifies session in-place: adds history, increments counter)
    result = _generate_next_question(session, curriculum)

    # Save session AFTER question generation so state is persisted
    session_path = DATA_DIR / f"{session['id']}.json"
    with open(session_path, 'w') as f:
        json.dump(session, f, indent=2)

    return result


def continue_elicitation(session_id: str, response: dict) -> dict | None:
    """Continue an elicitation session with user's response.

    response: {
        "familiarity": "unknown" | "heard_of" | "know_basics" | "could_explain" | "know_deeply",
        "interest": "none" | "curious" | "core" (optional),
        "revised": bool (optional — user revised after seeing card flip)
    }
    """
    session_path = DATA_DIR / f"{session_id}.json"
    if not session_path.exists():
        return None

    with open(session_path) as f:
        session = json.load(f)

    curriculum = load_curriculum(session["domain_id"])
    if not curriculum:
        return None

    # Process the response
    if session["history"]:
        last_q = session["history"][-1]
        node_id = last_q["node_id"]
        familiarity = response.get("familiarity", "unknown")
        interest = response.get("interest", "none")

        # Map familiarity to knowledge state and belief
        familiarity_to_knowledge = {
            "unknown": ("unknown", 0.05),
            "heard_of": ("mentioned", 0.4),
            "know_basics": ("mentioned", 0.7),
            "could_explain": ("engaged", 0.85),
            "know_deeply": ("anchored", 0.95),
        }
        knowledge, belief = familiarity_to_knowledge.get(familiarity, ("unknown", 0.05))

        # Update belief for this node
        session["beliefs"][node_id] = belief

        # Propagate through prerequisites
        nodes_by_id = {n["id"]: n for n in curriculum["nodes"]}
        node = nodes_by_id.get(node_id)

        if node and familiarity in ("unknown", "heard_of"):
            # If doesn't know this, likely doesn't know children either
            for n in curriculum["nodes"]:
                if node_id in n.get("prerequisites", []):
                    current = session["beliefs"].get(n["id"], 0.3)
                    session["beliefs"][n["id"]] = min(current, 0.2)

        if node and familiarity in ("could_explain", "know_deeply"):
            # If knows this well, likely knows prerequisites
            for prereq_id in node.get("prerequisites", []):
                current = session["beliefs"].get(prereq_id, 0.3)
                session["beliefs"][prereq_id] = max(current, 0.8)

        # Record in history
        last_q["response"] = {
            "familiarity": familiarity,
            "interest": interest,
            "belief_after": belief,
        }
        session["nodes_assessed"].append(node_id)

        # Update persistent knowledge state
        update_knowledge(
            session["domain_id"], node_id,
            knowledge=knowledge,
            interest=interest if interest != "none" else None,
            confidence=belief,
            source="elicitation",
        )

    # Check if we should stop
    if session["questions_asked"] >= 30:
        session["status"] = "complete"
        with open(session_path, 'w') as f:
            json.dump(session, f, indent=2)
        return {
            "status": "complete",
            "message": "Assessment complete! Here's your knowledge map.",
            "coverage": get_coverage_report(session["domain_id"]),
        }

    # Generate next question
    result = _generate_next_question(session, curriculum)

    # Save session
    with open(session_path, 'w') as f:
        json.dump(session, f, indent=2)

    return result


def _generate_next_question(session: dict, curriculum: dict) -> dict:
    """Select and generate the next question."""
    beliefs = session["beliefs"]
    assessed = set(session.get("nodes_assessed", []))

    # Find node with highest information gain (closest to P=0.5)
    candidates = []
    for node in curriculum["nodes"]:
        if node["id"] in assessed:
            continue
        p = beliefs.get(node["id"], 0.3)
        ig = _information_gain(p)
        candidates.append((ig, p, node))

    if not candidates:
        return {
            "status": "complete",
            "message": "All topics assessed!",
            "coverage": get_coverage_report(session["domain_id"]),
        }

    # Sort by information gain (descending), take top candidate
    candidates.sort(key=lambda x: x[0], reverse=True)
    _, p_knows, target_node = candidates[0]

    # Choose question type based on context
    q_num = session["questions_asked"]
    if q_num < 3:
        question_type = "recognition"  # Start broad
    elif q_num % 4 == 0 and len(candidates) >= 2:
        question_type = "comparison"  # Mix in comparisons
    elif p_knows > 0.6:
        question_type = "scoping"  # They probably know it — probe depth
    else:
        question_type = "recognition"

    # Build knowledge summary for LLM context
    known_titles = []
    unknown_titles = []
    for node in curriculum["nodes"]:
        nid = node["id"]
        if nid in assessed:
            state = beliefs.get(nid, 0.3)
            if state > 0.5:
                known_titles.append(node["title"])
            else:
                unknown_titles.append(node["title"])

    knowledge_summary = ""
    if known_titles:
        knowledge_summary += f"KNOWS: {', '.join(known_titles[:15])}\n"
    if unknown_titles:
        knowledge_summary += f"DOESN'T KNOW: {', '.join(unknown_titles[:10])}\n"
    if not known_titles and not unknown_titles:
        knowledge_summary = "This is the first question — we don't know anything yet."

    level_desc = {1: "broad area", 2: "specific topic", 3: "detailed concept", 4: "specific detail"}.get(
        target_node.get("level", 2), "topic")

    history_text = ""
    for h in session.get("history", [])[-5:]:
        resp = h.get("response", {})
        fam = resp.get("familiarity", "?")
        history_text += f"Q: {h.get('question', '?')}\nA: {fam}\n\n"
    if not history_text:
        history_text = "No questions asked yet."

    prompt = ELICITATION_QUESTION_PROMPT.format(
        domain=curriculum["title"],
        knowledge_summary=knowledge_summary,
        node_title=target_node["title"],
        node_description=target_node.get("description", ""),
        level_desc=level_desc,
        question_type=question_type,
        history=history_text,
    )

    raw = call_llm(prompt, model="gemini-2.5-flash", max_tokens=1024,
                   response_mime_type="application/json")

    question_text = f"Are you familiar with {target_node['title']}?"
    card_summary = target_node.get("description", "")
    follow_up = None

    if raw:
        try:
            q_data = json.loads(raw)
            question_text = q_data.get("question", question_text)
            card_summary = q_data.get("card_summary", card_summary)
            follow_up = q_data.get("follow_up_if_yes")
        except json.JSONDecodeError:
            pass

    # Record in history
    entry = {
        "question_number": session["questions_asked"] + 1,
        "node_id": target_node["id"],
        "node_title": target_node["title"],
        "question": question_text,
        "card_summary": card_summary,
        "follow_up": follow_up,
        "question_type": question_type,
        "p_knows_before": beliefs.get(target_node["id"], 0.3),
        "information_gain": _information_gain(beliefs.get(target_node["id"], 0.3)),
    }
    session["history"].append(entry)
    session["questions_asked"] += 1

    # Calculate remaining entropy
    remaining_uncertain = sum(
        1 for nid, p in beliefs.items()
        if nid not in assessed and 0.2 < p < 0.8
    )

    return {
        "status": "in_progress",
        "session_id": session["id"],
        "question_number": entry["question_number"],
        "total_nodes": len(curriculum["nodes"]),
        "assessed_so_far": len(assessed),
        "remaining_uncertain": remaining_uncertain,
        "question": question_text,
        "card_summary": card_summary,
        "follow_up": follow_up,
        "question_type": question_type,
        "node_title": target_node["title"],
        "familiarity_options": [
            {"value": "unknown", "label": "Never heard of it"},
            {"value": "heard_of", "label": "I've heard the name"},
            {"value": "know_basics", "label": "I know the basics"},
            {"value": "could_explain", "label": "I could explain it"},
            {"value": "know_deeply", "label": "I know this in depth"},
        ],
        "interest_options": [
            {"value": "none", "label": "Not particularly interested"},
            {"value": "curious", "label": "I'd like to know more"},
            {"value": "core", "label": "Deeply interesting to me"},
        ],
    }
