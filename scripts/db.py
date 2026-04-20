"""
Petrarca SQLite database — connection helper + schema.

Usage:
    from db import get_connection, init_db

    init_db()  # creates tables if not exist

    conn = get_connection()
    conn.execute("INSERT INTO projects (...) VALUES (?, ?)", (id, name))
    conn.commit()
    conn.close()

Connection-per-request pattern: each handler opens/commits/closes its own
connection. WAL mode (via limbic.amygdala.connect) makes this safe and cheap with
ThreadingHTTPServer.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, '/opt/limbic')
from limbic.amygdala import connect

DB_PATH = Path(os.environ.get('PETRARCA_DB', '/opt/petrarca/data/petrarca.db'))


def get_connection(readonly: bool = False):
    """Get a new database connection with WAL, 64MB cache, FK enforcement."""
    return connect(DB_PATH, readonly=readonly)


SCHEMA = """
-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_notes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    text TEXT DEFAULT '',
    audio_file TEXT,
    source TEXT,
    voice_routing TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_notes_project ON project_notes(project_id);

-- Physical books
CREATE TABLE IF NOT EXISTS physical_books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    cover_image_uri TEXT,
    cover_url TEXT,
    isbn TEXT,
    publisher TEXT,
    year INTEGER,
    page_count INTEGER,
    language TEXT DEFAULT 'en',
    topics TEXT DEFAULT '[]',
    chapters TEXT DEFAULT '[]',
    current_chapter TEXT,
    current_page INTEGER,
    reading_status TEXT DEFAULT 'reading',
    significance TEXT,
    added_at INTEGER NOT NULL,
    last_interaction_at INTEGER NOT NULL,
    metadata_source TEXT,
    processing_status TEXT,
    kindle_asin TEXT,
    kindle_book_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_books_reading_status ON physical_books(reading_status);

CREATE TABLE IF NOT EXISTS book_captures (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES physical_books(id),
    type TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    audio_uri TEXT,
    transcript TEXT,
    transcription_status TEXT,
    photo_uri TEXT,
    ocr_text TEXT,
    ocr_status TEXT,
    text TEXT,
    page_number INTEGER,
    chapter TEXT,
    extracted_ideas TEXT DEFAULT '[]',
    topics TEXT DEFAULT '[]',
    key_passage TEXT,
    elaborative_question TEXT,
    server_id TEXT,
    upload_status TEXT DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_captures_book ON book_captures(book_id);

-- Kindle books (replaces kindle_library.json)
CREATE TABLE IF NOT EXISTS kindle_books (
    key TEXT PRIMARY KEY,
    asin TEXT,
    book_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    title_resolved TEXT,
    author TEXT NOT NULL DEFAULT '',
    cover_url TEXT,
    progress_pct REAL DEFAULT 0,
    current_position INTEGER DEFAULT 0,
    max_position INTEGER DEFAULT 0,
    progress_text TEXT,
    progress_updated TEXT,
    first_seen TEXT,
    last_seen TEXT,
    status TEXT NOT NULL DEFAULT 'unreviewed',
    category TEXT,
    added_to_petrarca INTEGER DEFAULT 0,
    finished_date TEXT,
    last_read TEXT,
    purchase_date TEXT,
    language TEXT DEFAULT '',
    publisher TEXT DEFAULT '',
    is_sideloaded INTEGER DEFAULT 0,
    epub_path TEXT,
    source TEXT DEFAULT 'kindle_mac'
);
CREATE INDEX IF NOT EXISTS idx_kindle_books_asin ON kindle_books(asin);
CREATE INDEX IF NOT EXISTS idx_kindle_books_status ON kindle_books(status);
CREATE INDEX IF NOT EXISTS idx_kindle_books_category ON kindle_books(category);

-- Available EPUBs on server (for matching to kindle_books)
CREATE TABLE IF NOT EXISTS available_epubs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    server_path TEXT NOT NULL,
    title TEXT,
    author TEXT,
    size_bytes INTEGER,
    kindle_book_key TEXT,
    uploaded_at TEXT,
    UNIQUE(server_path)
);

-- ===== Content Pipeline Tables (replaces JSON files) =====

-- Articles (replaces articles.json)
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    date TEXT DEFAULT '',
    content_markdown TEXT DEFAULT '',
    one_line_summary TEXT DEFAULT '',
    full_summary TEXT DEFAULT '',
    key_claims TEXT DEFAULT '[]',
    topics TEXT DEFAULT '[]',
    interest_topics TEXT DEFAULT '[]',
    novelty_claims TEXT DEFAULT '[]',
    entities TEXT DEFAULT '[]',
    estimated_read_minutes INTEGER DEFAULT 0,
    content_type TEXT DEFAULT 'unknown',
    word_count INTEGER DEFAULT 0,
    sources TEXT DEFAULT '[]',
    fetch_method TEXT,
    exploration_tag TEXT,
    parent_id TEXT,
    exploration_tier TEXT,
    exploration_order INTEGER,
    ingested_at TEXT,
    similar_articles TEXT,
    follow_up_questions TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Article sections
CREATE TABLE IF NOT EXISTS article_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    section_index INTEGER NOT NULL,
    heading TEXT DEFAULT '',
    content TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    key_claims TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_article_sections_article ON article_sections(article_id);

-- Atomic claims (composite PK: same claim ID can appear in multiple articles)
CREATE TABLE IF NOT EXISTS atomic_claims (
    id TEXT NOT NULL,
    article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    normalized_text TEXT NOT NULL DEFAULT '',
    original_text TEXT DEFAULT '',
    claim_type TEXT DEFAULT 'factual',
    source_paragraphs TEXT DEFAULT '[]',
    topics TEXT DEFAULT '[]',
    PRIMARY KEY (article_id, id)
);
CREATE INDEX IF NOT EXISTS idx_claims_article ON atomic_claims(article_id);
CREATE INDEX IF NOT EXISTS idx_claims_id ON atomic_claims(id);

-- Claim similarity pairs (from build_knowledge_index.py)
CREATE TABLE IF NOT EXISTS claim_similarities (
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    score REAL NOT NULL,
    PRIMARY KEY (claim_a, claim_b)
);
CREATE INDEX IF NOT EXISTS idx_claimsim_a ON claim_similarities(claim_a);
CREATE INDEX IF NOT EXISTS idx_claimsim_b ON claim_similarities(claim_b);

-- NLI verdicts for ambiguous pairs
CREATE TABLE IF NOT EXISTS nli_verdicts (
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    verdict TEXT NOT NULL,
    PRIMARY KEY (claim_a, claim_b)
);

-- Article-level similarity pairs
CREATE TABLE IF NOT EXISTS article_similarities (
    article_a TEXT NOT NULL,
    article_b TEXT NOT NULL,
    score REAL NOT NULL,
    PRIMARY KEY (article_a, article_b)
);
CREATE INDEX IF NOT EXISTS idx_artsim_a ON article_similarities(article_a);
CREATE INDEX IF NOT EXISTS idx_artsim_b ON article_similarities(article_b);

-- Article novelty matrix (per target-read pair)
CREATE TABLE IF NOT EXISTS article_novelty_matrix (
    target_article_id TEXT NOT NULL,
    read_article_id TEXT NOT NULL,
    new_count INTEGER NOT NULL DEFAULT 0,
    extends_count INTEGER NOT NULL DEFAULT 0,
    known_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (target_article_id, read_article_id)
);

-- Paragraph-to-claim mapping
CREATE TABLE IF NOT EXISTS paragraph_claim_map (
    article_id TEXT NOT NULL,
    paragraph_index INTEGER NOT NULL,
    claim_id TEXT NOT NULL,
    PRIMARY KEY (article_id, paragraph_index, claim_id)
);

-- Article-to-curriculum node links
CREATE TABLE IF NOT EXISTS article_curriculum_nodes (
    article_id TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    node_title TEXT DEFAULT '',
    claim_count INTEGER DEFAULT 0,
    avg_similarity REAL DEFAULT 0,
    max_similarity REAL DEFAULT 0,
    PRIMARY KEY (article_id, domain_id, node_id)
);

-- Delta reports per topic
CREATE TABLE IF NOT EXISTS delta_reports (
    topic TEXT PRIMARY KEY,
    summary TEXT DEFAULT '',
    claim_count INTEGER DEFAULT 0,
    article_count INTEGER DEFAULT 0,
    top_claims TEXT DEFAULT '[]',
    subtopics TEXT
);

-- Concept clusters
CREATE TABLE IF NOT EXISTS concept_clusters (
    cluster_id INTEGER PRIMARY KEY,
    label TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    articles TEXT DEFAULT '[]',
    core_article_ids TEXT DEFAULT '[]',
    peripheral_article_ids TEXT DEFAULT '[]',
    top_topics TEXT DEFAULT '[]',
    total_unique_claims INTEGER DEFAULT 0,
    total_shared_claims INTEGER DEFAULT 0,
    key_shared_claims TEXT DEFAULT '[]',
    internal_edges INTEGER DEFAULT 0,
    avg_edge_weight REAL DEFAULT 0
);

-- Near-duplicate article pairs
CREATE TABLE IF NOT EXISTS near_duplicates (
    article_a TEXT NOT NULL,
    article_b TEXT NOT NULL,
    title_a TEXT DEFAULT '',
    title_b TEXT DEFAULT '',
    known_claims INTEGER DEFAULT 0,
    total_claims_a INTEGER DEFAULT 0,
    overlap_ratio REAL DEFAULT 0,
    PRIMARY KEY (article_a, article_b)
);

-- Syntheses
CREATE TABLE IF NOT EXISTS syntheses (
    cluster_id TEXT PRIMARY KEY,
    label TEXT DEFAULT '',
    synthesis_markdown TEXT DEFAULT '',
    article_ids TEXT DEFAULT '[]',
    article_coverage TEXT DEFAULT '{}',
    claims_covered TEXT DEFAULT '[]',
    unique_per_article TEXT DEFAULT '{}',
    follow_up_questions TEXT DEFAULT '[]',
    tensions TEXT DEFAULT '[]',
    generated_at TEXT DEFAULT '',
    total_articles INTEGER DEFAULT 0,
    total_claims_covered INTEGER DEFAULT 0,
    total_claims_in_cluster INTEGER DEFAULT 0
);

-- Pipeline metadata (version, hashes, timestamps)
CREATE TABLE IF NOT EXISTS pipeline_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Cluster metadata (parameters, stats — one row per pipeline run)
CREATE TABLE IF NOT EXISTS cluster_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Knowledge Review Items (spaced retrieval practice)
CREATE TABLE IF NOT EXISTS review_items (
  id TEXT PRIMARY KEY,
  item_type TEXT NOT NULL DEFAULT 'book_chapter',  -- book_chapter | exploration | voice_followup
  curriculum_domain TEXT,
  curriculum_node_id TEXT,
  curriculum_node_title TEXT,
  source_book_id TEXT,
  source_chapter_number INTEGER,
  source_chapter_title TEXT,
  source_article_id TEXT,
  source_text TEXT NOT NULL DEFAULT '',
  temporal_hook TEXT DEFAULT '',
  lens TEXT,                          -- CAUSAL | COMPARATIVE | SIGNIFICANCE | TEMPORAL | PATTERN | CONSEQUENCE
  parent_item_id TEXT,                -- for follow-up chains
  stability_days REAL NOT NULL DEFAULT 1.0,
  due_at INTEGER NOT NULL,            -- unix ms timestamp
  last_reviewed_at INTEGER,
  last_score TEXT,                    -- knew | partly | missed
  review_count INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  cached_question TEXT                -- JSON: pre-generated question, cleared after answer
);

-- Node-centric knowledge items — one row per curriculum node, sources array accumulates all books/chapters
-- LEGACY: superseded by knowledge_states for curriculum tracking; kept for existing book-chapter review
CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    curriculum_node_id TEXT NOT NULL,
    curriculum_domain TEXT NOT NULL,
    stability_days REAL NOT NULL DEFAULT 1.0,
    due_at INTEGER NOT NULL DEFAULT 0,
    last_reviewed_at INTEGER,
    last_score TEXT,
    review_count INTEGER NOT NULL DEFAULT 0,
    sources TEXT NOT NULL DEFAULT '[]',
    question_history TEXT NOT NULL DEFAULT '[]',
    created_at INTEGER NOT NULL,
    cached_question TEXT,
    UNIQUE(curriculum_domain, curriculum_node_id)
);

-- Entity-keyed knowledge items — parallel to knowledge_items but anchored on
-- entities (people, places, events) instead of curriculum nodes. Used when
-- voice captures can't route to existing curricula. Same FSRS scheduling,
-- same key_facts schema, same cached_question flow. See
-- research/entity-first-architecture.md.
CREATE TABLE IF NOT EXISTS knowledge_entities (
    id TEXT PRIMARY KEY,                    -- 'ent:{slug}'
    entity_id TEXT,                         -- FK shared_entities (nullable until resolved)
    entity_name TEXT NOT NULL,
    entity_type TEXT,                       -- person/place/event/concept
    wikidata_qid TEXT,
    key_facts TEXT NOT NULL DEFAULT '[]',   -- JSON: same schema as curriculum_nodes.key_facts
    sources TEXT NOT NULL DEFAULT '[]',     -- JSON: [{source, capture_id, source_text, added_at}]
    stability_days REAL NOT NULL DEFAULT 1.0,
    due_at INTEGER NOT NULL DEFAULT 0,
    last_reviewed_at INTEGER,
    last_score TEXT,
    review_count INTEGER NOT NULL DEFAULT 0,
    cached_question TEXT,
    question_history TEXT NOT NULL DEFAULT '[]',
    fsrs_card_json TEXT,
    -- Phase 2: cached Wikidata structured properties (P22, P26, P39, P580, etc.)
    -- Populated lazily by _fetch_wikidata_props() when entity has a QID.
    -- JSON shape: {"fetched_at": unix_ts, "props": {"P22": [{"qid":..., "label":...}, ...], ...}}
    wikidata_props_json TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ke_entity ON knowledge_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_ke_due ON knowledge_entities(due_at);
CREATE INDEX IF NOT EXISTS idx_ke_qid ON knowledge_entities(wikidata_qid);

-- ===== Curriculum System (replaces JSON files in data/curricula/) =====

-- Curriculum domains (e.g. "Sicily: History, Culture, and Legacy")
CREATE TABLE IF NOT EXISTS curriculum_domains (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    depth TEXT DEFAULT 'introductory',
    generated_at TEXT,
    generated_by TEXT,
    node_count INTEGER DEFAULT 0
);

-- Curriculum nodes — the actual knowledge structure
CREATE TABLE IF NOT EXISTS curriculum_nodes (
    id TEXT NOT NULL,
    domain_id TEXT NOT NULL REFERENCES curriculum_domains(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id TEXT,
    level INTEGER NOT NULL DEFAULT 1,
    obscurity INTEGER DEFAULT 2,
    bloom_floor TEXT DEFAULT 'recognize',
    knowledge_type TEXT DEFAULT 'core',
    date_start INTEGER,
    date_end INTEGER,
    PRIMARY KEY (domain_id, id)
);
CREATE INDEX IF NOT EXISTS idx_cn_domain ON curriculum_nodes(domain_id);
CREATE INDEX IF NOT EXISTS idx_cn_parent ON curriculum_nodes(domain_id, parent_id);

-- Prerequisite edges (DAG within a domain)
CREATE TABLE IF NOT EXISTS curriculum_prerequisites (
    domain_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    prerequisite_id TEXT NOT NULL,
    strength TEXT DEFAULT 'hard',
    PRIMARY KEY (domain_id, node_id, prerequisite_id),
    FOREIGN KEY (domain_id, node_id) REFERENCES curriculum_nodes(domain_id, id),
    FOREIGN KEY (domain_id, prerequisite_id) REFERENCES curriculum_nodes(domain_id, id)
);

-- Knowledge state per node — SINGLE source of truth for "what do I know"
CREATE TABLE IF NOT EXISTS knowledge_states (
    domain_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    knowledge TEXT NOT NULL DEFAULT 'unknown',
    interest TEXT DEFAULT 'none',
    confidence REAL DEFAULT 0.0,
    highest_layer INTEGER DEFAULT 0,
    source_summary TEXT DEFAULT '[]',
    last_assessed TEXT,
    last_evidence TEXT,
    PRIMARY KEY (domain_id, node_id),
    FOREIGN KEY (domain_id, node_id) REFERENCES curriculum_nodes(domain_id, id)
);
CREATE INDEX IF NOT EXISTS idx_ks_knowledge ON knowledge_states(knowledge);

-- Book-to-curriculum mappings
CREATE TABLE IF NOT EXISTS book_curriculum_mappings (
    book_id TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    coverage TEXT DEFAULT 'surface',
    inferred_from TEXT DEFAULT 'llm_inference',
    PRIMARY KEY (book_id, domain_id, node_id),
    FOREIGN KEY (domain_id, node_id) REFERENCES curriculum_nodes(domain_id, id)
);
CREATE INDEX IF NOT EXISTS idx_bcm_book ON book_curriculum_mappings(book_id);
CREATE INDEX IF NOT EXISTS idx_bcm_node ON book_curriculum_mappings(domain_id, node_id);

-- Timeline entries per domain
CREATE TABLE IF NOT EXISTS timeline_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    label TEXT NOT NULL,
    detail TEXT DEFAULT '',
    node_id TEXT,
    FOREIGN KEY (domain_id, node_id) REFERENCES curriculum_nodes(domain_id, id)
);
CREATE INDEX IF NOT EXISTS idx_tl_domain ON timeline_entries(domain_id);
CREATE INDEX IF NOT EXISTS idx_tl_year ON timeline_entries(year);

-- Cross-curriculum shared entities
-- Columns added over time via ALTER TABLE on the live DB (description,
-- entity_type, modern_name, wikipedia_url, latitude, longitude, aliases,
-- date_start, date_end, wikidata_qid). New installs get them all here.
CREATE TABLE IF NOT EXISTS shared_entities (
    entity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    dates TEXT,
    location TEXT,
    nexus_score INTEGER DEFAULT 1,
    description TEXT,
    entity_type TEXT,
    modern_name TEXT,
    wikipedia_url TEXT,
    latitude REAL,
    longitude REAL,
    aliases TEXT DEFAULT '[]',
    date_start INTEGER,
    date_end INTEGER,
    wikidata_qid TEXT
);
-- Unique where non-null: multiple NULLs allowed, but each QID at most once.
CREATE UNIQUE INDEX IF NOT EXISTS idx_shared_entities_qid
    ON shared_entities(wikidata_qid) WHERE wikidata_qid IS NOT NULL;

CREATE TABLE IF NOT EXISTS entity_curriculum_links (
    entity_id TEXT NOT NULL REFERENCES shared_entities(entity_id),
    domain_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    lens_title TEXT,
    lens_emphasis TEXT,
    PRIMARY KEY (entity_id, domain_id, node_id)
);

-- Append-only audit log of Wikidata resolution attempts. Every resolver
-- decision writes a row here with full candidate set + reasoning, even when
-- ambiguous. Re-resolving the same mention writes a new row; the old row's
-- superseded_by is updated to point at it. History is preserved.
CREATE TABLE IF NOT EXISTS entity_resolutions (
    id TEXT PRIMARY KEY,
    entity_id TEXT,                 -- shared_entities row this resolution is for (NULL if ad-hoc mention)
    capture_id TEXT,                -- voice_transcripts.id, or 'backfill:<batch_id>'
    mention_text TEXT NOT NULL,     -- raw string looked up
    context_excerpt TEXT,           -- description / surrounding text passed to resolver
    type_hint TEXT,                 -- person | place | event | work | other
    date_hint_start INTEGER,        -- year, nullable
    date_hint_end INTEGER,          -- year, nullable
    candidate_qids TEXT,            -- JSON array of {qid, label, description, total, scores, dates, external_ids}
    chosen_qid TEXT,                -- set iff status=resolved | kb_hit
    confidence REAL NOT NULL,
    status TEXT NOT NULL,           -- resolved | ambiguous | no_match | kb_hit | needs_review
    resolver_model TEXT,            -- 'deterministic-0.1' | 'sonnet-4-6' | 'opus-4-6'
    reasoning TEXT,
    cost_usd REAL DEFAULT 0,
    created_at INTEGER NOT NULL,
    superseded_by TEXT              -- id of newer resolution, if any
);
CREATE INDEX IF NOT EXISTS idx_entity_resolutions_entity ON entity_resolutions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_resolutions_capture ON entity_resolutions(capture_id);
CREATE INDEX IF NOT EXISTS idx_entity_resolutions_status ON entity_resolutions(status);
CREATE INDEX IF NOT EXISTS idx_entity_resolutions_chosen ON entity_resolutions(chosen_qid);

-- External ID fan-out at resolution time: when we resolve an entity to a
-- QID, Wikidata exposes VIAF (P214), GND (P227), GeoNames (P1566), Pleiades
-- (P1584), Getty TGN (P1667), MusicBrainz (P434), Getty ULAN (P245), BnF
-- (P268), LCCN (P244). Storing them lets downstream enrichment hit specialist
-- sources as a cache lookup rather than another API roundtrip.
CREATE TABLE IF NOT EXISTS entity_external_ids (
    entity_id TEXT NOT NULL REFERENCES shared_entities(entity_id),
    property_id TEXT NOT NULL,      -- e.g. 'P214' (VIAF)
    value TEXT NOT NULL,            -- the external ID itself
    source TEXT DEFAULT 'wikidata', -- where we got it (usually 'wikidata')
    PRIMARY KEY (entity_id, property_id, value)
);
CREATE INDEX IF NOT EXISTS idx_entity_ext_ids_prop ON entity_external_ids(property_id, value);

-- User notes about entities: free-text "what I know" per entity
CREATE TABLE IF NOT EXISTS entity_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_en_entity ON entity_notes(entity_id);

-- Microlearning cards: research-driven short-form content in the review stream
CREATE TABLE IF NOT EXISTS microlearning_cards (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    source_item_id TEXT,                -- knowledge_item that spawned this
    source_node_id TEXT,
    source_domain TEXT,
    content TEXT NOT NULL,              -- 3-4 paragraph answer
    question TEXT,                      -- assessment question about the content
    answer_guidance TEXT,
    follow_up_queries TEXT DEFAULT '[]', -- JSON array of 3 next queries
    curriculum_nodes TEXT DEFAULT '[]',  -- JSON array of linked node_ids
    entities TEXT DEFAULT '[]',          -- JSON array of entity references
    entity_spans TEXT DEFAULT '{}',      -- JSON: {field: [{start,end,entity_id,name,entity_type}]}
    status TEXT DEFAULT 'pending',       -- pending, processing, completed, failed
    stability_days REAL DEFAULT 1.0,
    due_at INTEGER DEFAULT 0,
    last_reviewed_at INTEGER,
    review_count INTEGER DEFAULT 0,
    last_score TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ml_status ON microlearning_cards(status);
CREATE INDEX IF NOT EXISTS idx_ml_due ON microlearning_cards(due_at);

-- Individual quiz questions from microlearning cards, independently scheduled
CREATE TABLE IF NOT EXISTS microlearning_quizzes (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL REFERENCES microlearning_cards(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    fact_id TEXT,                         -- links all cue-questions for the same key_fact
    rich_answer TEXT,                     -- shared detail card content for all cues of a fact
    status TEXT DEFAULT 'active',         -- active, dismissed
    stability_days REAL DEFAULT 1.0,
    due_at INTEGER DEFAULT 0,
    last_reviewed_at INTEGER,
    review_count INTEGER DEFAULT 0,
    last_score TEXT,
    fsrs_card_json TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mlq_card ON microlearning_quizzes(card_id);
CREATE INDEX IF NOT EXISTS idx_mlq_due ON microlearning_quizzes(due_at);
CREATE INDEX IF NOT EXISTS idx_mlq_status ON microlearning_quizzes(status);

-- Voice transcript log: every voice interaction persisted for analysis
CREATE TABLE IF NOT EXISTS voice_transcripts (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,              -- 'elicitation' | 'review_memo' | 'feedback' | 'book_note'
    node_id TEXT,
    domain_id TEXT,
    node_title TEXT,
    transcript TEXT NOT NULL,
    audio_bytes INTEGER,
    llm_result TEXT,                   -- full JSON from LLM analysis
    microlearning_triggered TEXT DEFAULT '[]',
    created_at INTEGER NOT NULL,
    input_mode TEXT                    -- 'audio' | 'text_json' | 'test' | NULL (pre-migration)
);
CREATE INDEX IF NOT EXISTS idx_vt_source ON voice_transcripts(source);
CREATE INDEX IF NOT EXISTS idx_vt_created ON voice_transcripts(created_at);

-- Transcript chunks: embedded pieces of voice transcripts for knowledge profile
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id TEXT PRIMARY KEY,
    transcript_id TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_type TEXT NOT NULL,  -- 'raw_speech', 'captured_fact', 'interesting', 'wondering', 'feedback'
    embedding BLOB,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tc_transcript ON transcript_chunks(transcript_id);
CREATE INDEX IF NOT EXISTS idx_tc_type ON transcript_chunks(chunk_type);

CREATE TABLE IF NOT EXISTS chunk_node_links (
    chunk_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    relevance REAL DEFAULT 1.0,
    PRIMARY KEY (chunk_id, node_id)
);
CREATE INDEX IF NOT EXISTS idx_cnl_node ON chunk_node_links(node_id, domain_id);

CREATE TABLE IF NOT EXISTS chunk_entity_links (
    chunk_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    relevance REAL DEFAULT 1.0,
    PRIMARY KEY (chunk_id, entity_name)
);
CREATE INDEX IF NOT EXISTS idx_cel_entity ON chunk_entity_links(entity_name);

-- ===== Knowledge Growth Tracking =====

-- Knowledge transitions: event log of every level change
CREATE TABLE IF NOT EXISTS knowledge_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    from_level TEXT NOT NULL,
    to_level TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown',
    source_id TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_kt_domain ON knowledge_transitions(domain_id);
CREATE INDEX IF NOT EXISTS idx_kt_created ON knowledge_transitions(created_at);

-- Network metrics log: periodic snapshots of graph-level metrics per domain
CREATE TABLE IF NOT EXISTS network_metrics_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id TEXT NOT NULL,
    node_coverage REAL NOT NULL,
    edge_overlap REAL NOT NULL,
    density REAL NOT NULL,
    nodes_known INTEGER NOT NULL,
    nodes_total INTEGER NOT NULL,
    edges_known INTEGER NOT NULL DEFAULT 0,
    edges_total INTEGER NOT NULL DEFAULT 0,
    computed_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_nml_domain ON network_metrics_log(domain_id);
CREATE INDEX IF NOT EXISTS idx_nml_computed ON network_metrics_log(computed_at);

-- Knowledge sweeps: periodic domain-wide voice recall assessments
CREATE TABLE IF NOT EXISTS knowledge_sweeps (
    id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL,
    sweep_type TEXT NOT NULL DEFAULT 'guided',  -- guided | freeform | connection | feynman
    phase1_transcript TEXT,          -- combined Phase 1 (era-by-era) transcript
    phase2_transcript TEXT,          -- Phase 2 (gap probing) transcript
    phase1_eras TEXT DEFAULT '[]',   -- JSON: [{era, transcript, duration_s}]

    -- Raw metrics (Phase 1 only — spontaneous recall)
    p1_nodes_mentioned INTEGER NOT NULL DEFAULT 0,
    p1_facts_correct INTEGER NOT NULL DEFAULT 0,
    p1_facts_stated INTEGER NOT NULL DEFAULT 0,
    p1_connections INTEGER NOT NULL DEFAULT 0,

    -- Raw metrics (Phase 1 + Phase 2 combined)
    total_nodes_mentioned INTEGER NOT NULL DEFAULT 0,
    total_facts_correct INTEGER NOT NULL DEFAULT 0,
    total_facts_stated INTEGER NOT NULL DEFAULT 0,
    total_connections INTEGER NOT NULL DEFAULT 0,
    nodes_total INTEGER NOT NULL DEFAULT 0,
    connections_possible INTEGER NOT NULL DEFAULT 0,

    -- Derived scores (0.0-1.0)
    p1_coverage REAL NOT NULL DEFAULT 0.0,
    p1_accuracy REAL NOT NULL DEFAULT 0.0,
    total_coverage REAL NOT NULL DEFAULT 0.0,
    total_accuracy REAL NOT NULL DEFAULT 0.0,
    connectivity_score REAL NOT NULL DEFAULT 0.0,
    organization_score REAL NOT NULL DEFAULT 0.0,
    composite_score REAL NOT NULL DEFAULT 0.0,

    -- Detailed LLM results (JSON)
    scoring_result TEXT DEFAULT '{}',  -- full LLM scoring output

    -- Delta tracking (vs previous sweep of same domain)
    previous_sweep_id TEXT,
    delta_coverage REAL,
    delta_composite REAL,

    -- System vs self comparison
    system_coverage REAL,  -- what system thought coverage was before sweep

    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_ks_domain ON knowledge_sweeps(domain_id);
CREATE INDEX IF NOT EXISTS idx_ks_created ON knowledge_sweeps(created_at);
"""

MIGRATIONS = [
    # Add cached_question column if not present (idempotent)
    "ALTER TABLE review_items ADD COLUMN cached_question TEXT",
    # physical_books: add missing fields from JSON sync
    "ALTER TABLE physical_books ADD COLUMN finished_date TEXT",
    "ALTER TABLE physical_books ADD COLUMN category TEXT",
    "ALTER TABLE physical_books ADD COLUMN progress_percent REAL",
    # Entity context system: enrich shared_entities for tappable review card entities
    "ALTER TABLE shared_entities ADD COLUMN description TEXT",
    "ALTER TABLE shared_entities ADD COLUMN entity_type TEXT",
    "ALTER TABLE shared_entities ADD COLUMN modern_name TEXT",
    "ALTER TABLE shared_entities ADD COLUMN wikipedia_url TEXT",
    "ALTER TABLE shared_entities ADD COLUMN latitude REAL",
    "ALTER TABLE shared_entities ADD COLUMN longitude REAL",
    "ALTER TABLE shared_entities ADD COLUMN aliases TEXT DEFAULT '[]'",
    "ALTER TABLE shared_entities ADD COLUMN date_start INTEGER",
    "ALTER TABLE shared_entities ADD COLUMN date_end INTEGER",
    # key_facts: structured testable facts per curriculum node
    "ALTER TABLE curriculum_nodes ADD COLUMN key_facts TEXT DEFAULT '[]'",
    # Durable tracking of triggered follow-up queries
    "ALTER TABLE knowledge_items ADD COLUMN triggered_follow_ups TEXT DEFAULT '[]'",
    "ALTER TABLE microlearning_cards ADD COLUMN triggered_follow_ups TEXT DEFAULT '[]'",
    # Card title (with dates) for prominent display
    "ALTER TABLE microlearning_cards ADD COLUMN title TEXT",
    # Structured sections for formatted display
    "ALTER TABLE microlearning_cards ADD COLUMN sections TEXT DEFAULT '[]'",
    # Kindle books new columns (added when kindle_books table already existed)
    "ALTER TABLE kindle_books ADD COLUMN progress_pct REAL DEFAULT 0",
    "ALTER TABLE kindle_books ADD COLUMN current_position INTEGER DEFAULT 0",
    "ALTER TABLE kindle_books ADD COLUMN max_position INTEGER DEFAULT 0",
    "ALTER TABLE kindle_books ADD COLUMN progress_text TEXT",
    "ALTER TABLE kindle_books ADD COLUMN progress_updated TEXT",
    "ALTER TABLE kindle_books ADD COLUMN language TEXT DEFAULT ''",
    "ALTER TABLE kindle_books ADD COLUMN publisher TEXT DEFAULT ''",
    "ALTER TABLE kindle_books ADD COLUMN is_sideloaded INTEGER DEFAULT 0",
    "ALTER TABLE kindle_books ADD COLUMN epub_path TEXT",
    "ALTER TABLE kindle_books ADD COLUMN source TEXT DEFAULT 'kindle_mac'",
    # ML card source tracking: voice_wondering, follow_up, entity_research, user_request
    "ALTER TABLE microlearning_cards ADD COLUMN source_type TEXT DEFAULT 'follow_up'",
    # Generation depth: 0 = root (from review/voice), 1+ = child of ML card
    "ALTER TABLE microlearning_cards ADD COLUMN generation_depth INTEGER DEFAULT 0",
    # Domain knowledge summaries — synthesized learner knowledge portraits
    "CREATE TABLE IF NOT EXISTS domain_knowledge_summaries (id TEXT PRIMARY KEY, domain_id TEXT NOT NULL UNIQUE, summary TEXT NOT NULL, chunk_count INTEGER DEFAULT 0, node_count INTEGER DEFAULT 0, entity_count INTEGER DEFAULT 0, version INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')))",
    # FSRS-6 card state storage (py-fsrs Card serialized as JSON)
    "ALTER TABLE knowledge_items ADD COLUMN fsrs_card_json TEXT",
    "ALTER TABLE review_items ADD COLUMN fsrs_card_json TEXT",
    "ALTER TABLE microlearning_cards ADD COLUMN fsrs_card_json TEXT",
    "ALTER TABLE microlearning_quizzes ADD COLUMN fsrs_card_json TEXT",
    # Interaction logging table — dual-layer with JSONL (replaces broken log_server.py:8091)
    """CREATE TABLE IF NOT EXISTS interaction_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,
        item_id TEXT,
        item_type TEXT,
        score TEXT,
        session_id TEXT,
        response_ms INTEGER,
        card_type TEXT,
        domain TEXT,
        node_id TEXT,
        node_title TEXT,
        extra TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_il_event ON interaction_log(event)",
    "CREATE INDEX IF NOT EXISTS idx_il_item ON interaction_log(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_il_created ON interaction_log(created_at)",
    # Knowledge sweeps: periodic domain-wide voice recall assessments
    """CREATE TABLE IF NOT EXISTS knowledge_sweeps (
        id TEXT PRIMARY KEY,
        domain_id TEXT NOT NULL,
        sweep_type TEXT NOT NULL DEFAULT 'guided',
        phase1_transcript TEXT,
        phase2_transcript TEXT,
        phase1_eras TEXT DEFAULT '[]',
        p1_nodes_mentioned INTEGER NOT NULL DEFAULT 0,
        p1_facts_correct INTEGER NOT NULL DEFAULT 0,
        p1_facts_stated INTEGER NOT NULL DEFAULT 0,
        p1_connections INTEGER NOT NULL DEFAULT 0,
        total_nodes_mentioned INTEGER NOT NULL DEFAULT 0,
        total_facts_correct INTEGER NOT NULL DEFAULT 0,
        total_facts_stated INTEGER NOT NULL DEFAULT 0,
        total_connections INTEGER NOT NULL DEFAULT 0,
        nodes_total INTEGER NOT NULL DEFAULT 0,
        connections_possible INTEGER NOT NULL DEFAULT 0,
        p1_coverage REAL NOT NULL DEFAULT 0.0,
        p1_accuracy REAL NOT NULL DEFAULT 0.0,
        total_coverage REAL NOT NULL DEFAULT 0.0,
        total_accuracy REAL NOT NULL DEFAULT 0.0,
        connectivity_score REAL NOT NULL DEFAULT 0.0,
        organization_score REAL NOT NULL DEFAULT 0.0,
        composite_score REAL NOT NULL DEFAULT 0.0,
        scoring_result TEXT DEFAULT '{}',
        previous_sweep_id TEXT,
        delta_coverage REAL,
        delta_composite REAL,
        system_coverage REAL,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ks_domain ON knowledge_sweeps(domain_id)",
    "CREATE INDEX IF NOT EXISTS idx_ks_created ON knowledge_sweeps(created_at)",
    # Multi-cue quiz support: fact_id + rich_answer for shared detail cards
    "ALTER TABLE microlearning_quizzes ADD COLUMN fact_id TEXT",
    "ALTER TABLE microlearning_quizzes ADD COLUMN rich_answer TEXT",
    "CREATE INDEX IF NOT EXISTS idx_mlq_fact ON microlearning_quizzes(fact_id)",
    # Entity-keyed knowledge items (Phase 1 of entity-first architecture)
    """CREATE TABLE IF NOT EXISTS knowledge_entities (
        id TEXT PRIMARY KEY,
        entity_id TEXT,
        entity_name TEXT NOT NULL,
        entity_type TEXT,
        wikidata_qid TEXT,
        key_facts TEXT NOT NULL DEFAULT '[]',
        sources TEXT NOT NULL DEFAULT '[]',
        stability_days REAL NOT NULL DEFAULT 1.0,
        due_at INTEGER NOT NULL DEFAULT 0,
        last_reviewed_at INTEGER,
        last_score TEXT,
        review_count INTEGER NOT NULL DEFAULT 0,
        cached_question TEXT,
        question_history TEXT NOT NULL DEFAULT '[]',
        fsrs_card_json TEXT,
        created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ke_entity ON knowledge_entities(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_ke_due ON knowledge_entities(due_at)",
    "CREATE INDEX IF NOT EXISTS idx_ke_qid ON knowledge_entities(wikidata_qid)",
    # Phase 2: cached Wikidata structured properties for enrichment
    "ALTER TABLE knowledge_entities ADD COLUMN wikidata_props_json TEXT",
    # Voice-driven structural card suggestions
    """CREATE TABLE IF NOT EXISTS suggested_cards (
        id TEXT PRIMARY KEY,
        card_type TEXT NOT NULL,
        source_transcript_ids TEXT NOT NULL DEFAULT '[]',
        entities TEXT NOT NULL DEFAULT '[]',
        domain_ids TEXT NOT NULL DEFAULT '[]',
        rationale TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sc_status ON suggested_cards(status)",
    "CREATE INDEX IF NOT EXISTS idx_sc_type ON suggested_cards(card_type)",
]


def init_db():
    """Create all tables if they don't exist, apply migrations."""
    conn = get_connection()
    conn.executescript(SCHEMA)
    for migration in MIGRATIONS:
        try:
            conn.execute(migration)
        except Exception:
            pass  # column already exists
    conn.commit()
    conn.close()
    print(f'[db] Initialized database at {DB_PATH}', flush=True)


# --- JSON field sets for articles ---

ARTICLE_JSON_FIELDS = {
    'key_claims', 'topics', 'interest_topics', 'novelty_claims',
    'entities', 'sources', 'follow_up_questions', 'similar_articles',
}

ARTICLE_OPTIONAL_FIELDS = [
    'fetch_method', 'exploration_tag', 'parent_id',
    'exploration_tier', 'exploration_order', 'ingested_at',
    'similar_articles',
]


# --- Pipeline sync helpers ---

def sync_articles(articles: list[dict], conn=None):
    """Write articles list to SQLite (articles + sections + claims). One transaction."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("DELETE FROM atomic_claims")
    conn.execute("DELETE FROM article_sections")
    conn.execute("DELETE FROM articles")

    for a in articles:
        values = {
            'id': a['id'],
            'title': a.get('title', ''),
            'author': a.get('author', ''),
            'source_url': a.get('source_url', ''),
            'hostname': a.get('hostname', ''),
            'date': a.get('date', ''),
            'content_markdown': a.get('content_markdown', ''),
            'one_line_summary': a.get('one_line_summary', ''),
            'full_summary': a.get('full_summary', ''),
            'estimated_read_minutes': a.get('estimated_read_minutes', 0),
            'content_type': a.get('content_type', 'unknown'),
            'word_count': a.get('word_count', 0),
        }

        for field in ARTICLE_JSON_FIELDS:
            if field in a:
                values[field] = json.dumps(a[field], ensure_ascii=False)
            elif field in ('similar_articles', 'entities', 'follow_up_questions',
                           'interest_topics', 'novelty_claims'):
                # Truly optional — store NULL if absent so export skips them
                values[field] = None
            else:
                values[field] = '[]'

        for field in ARTICLE_OPTIONAL_FIELDS:
            if field in ARTICLE_JSON_FIELDS:
                continue
            values[field] = a.get(field)

        cols = ', '.join(values.keys())
        placeholders = ', '.join(['?'] * len(values))
        conn.execute(f"INSERT INTO articles ({cols}) VALUES ({placeholders})", list(values.values()))

        for si, sec in enumerate(a.get('sections', [])):
            conn.execute(
                "INSERT INTO article_sections (article_id, section_index, heading, content, summary, key_claims) VALUES (?, ?, ?, ?, ?, ?)",
                (a['id'], si, sec.get('heading', ''), sec.get('content', ''),
                 sec.get('summary', ''), json.dumps(sec.get('key_claims', []), ensure_ascii=False)),
            )

        for claim in a.get('atomic_claims', []):
            conn.execute(
                "INSERT INTO atomic_claims (id, article_id, normalized_text, original_text, claim_type, source_paragraphs, topics) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (claim['id'], a['id'], claim.get('normalized_text', ''),
                 claim.get('original_text', ''), claim.get('claim_type', 'factual'),
                 json.dumps(claim.get('source_paragraphs', [])),
                 json.dumps(claim.get('topics', []), ensure_ascii=False)),
            )

    conn.commit()
    if own_conn:
        conn.close()
    return len(articles)


def sync_knowledge_index(ki_data: dict, conn=None):
    """Write knowledge index data to SQLite tables. One transaction."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    # Pipeline meta
    conn.execute("DELETE FROM pipeline_meta WHERE key LIKE 'knowledge_index_%'")
    for key in ('version', 'generated_at'):
        if key in ki_data:
            conn.execute("INSERT INTO pipeline_meta (key, value) VALUES (?, ?)",
                         (f"knowledge_index_{key}", str(ki_data[key])))
    if ki_data.get('stats'):
        conn.execute("INSERT INTO pipeline_meta (key, value) VALUES (?, ?)",
                     ("knowledge_index_stats", json.dumps(ki_data['stats'])))

    # Claim similarities
    conn.execute("DELETE FROM claim_similarities")
    sims = ki_data.get('similarities', [])
    if sims:
        conn.executemany(
            "INSERT INTO claim_similarities (claim_a, claim_b, score) VALUES (?, ?, ?)",
            [(p['a'], p['b'], p['score']) for p in sims])

    # NLI verdicts
    conn.execute("DELETE FROM nli_verdicts")
    verdicts = ki_data.get('nli_verdicts', {})
    if verdicts:
        rows = []
        for key, verdict in verdicts.items():
            parts = key.split('::')
            if len(parts) == 2:
                rows.append((parts[0], parts[1], verdict))
        conn.executemany("INSERT INTO nli_verdicts (claim_a, claim_b, verdict) VALUES (?, ?, ?)", rows)

    # Article similarities
    conn.execute("DELETE FROM article_similarities")
    asims = ki_data.get('article_similarities', [])
    if asims:
        conn.executemany(
            "INSERT INTO article_similarities (article_a, article_b, score) VALUES (?, ?, ?)",
            [(p['a'], p['b'], p['score']) for p in asims])

    # Article novelty matrix
    conn.execute("DELETE FROM article_novelty_matrix")
    anm = ki_data.get('article_novelty_matrix', {})
    rows = []
    for target_id, read_map in anm.items():
        for read_id, counts in read_map.items():
            rows.append((target_id, read_id, counts['new'], counts['extends'], counts['known']))
    if rows:
        conn.executemany(
            "INSERT INTO article_novelty_matrix (target_article_id, read_article_id, new_count, extends_count, known_count) VALUES (?, ?, ?, ?, ?)",
            rows)

    # Paragraph claim map
    conn.execute("DELETE FROM paragraph_claim_map")
    pmap = ki_data.get('paragraph_map', {})
    rows = []
    for article_id, para_map in pmap.items():
        for para_idx_str, claim_ids in para_map.items():
            for claim_id in claim_ids:
                rows.append((article_id, int(para_idx_str), claim_id))
    if rows:
        conn.executemany(
            "INSERT INTO paragraph_claim_map (article_id, paragraph_index, claim_id) VALUES (?, ?, ?)",
            rows)

    # Article curriculum nodes
    conn.execute("DELETE FROM article_curriculum_nodes")
    acn = ki_data.get('article_curriculum_nodes', {})
    rows = []
    for article_id, nodes in acn.items():
        for node in nodes:
            rows.append((article_id, node.get('domain_id', node.get('curriculum', '')),
                         node['node_id'], node.get('node_title', ''),
                         node.get('claim_count', 0), node.get('avg_similarity', 0),
                         node.get('max_similarity', 0)))
    if rows:
        conn.executemany(
            "INSERT INTO article_curriculum_nodes (article_id, domain_id, node_id, node_title, claim_count, avg_similarity, max_similarity) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows)

    # Delta reports
    conn.execute("DELETE FROM delta_reports")
    for topic, report in ki_data.get('delta_reports', {}).items():
        conn.execute(
            "INSERT INTO delta_reports (topic, summary, claim_count, article_count, top_claims, subtopics) VALUES (?, ?, ?, ?, ?, ?)",
            (topic, report.get('summary', ''), report.get('claim_count', 0),
             report.get('article_count', 0),
             json.dumps(report.get('top_claims', []), ensure_ascii=False),
             json.dumps(report.get('subtopics'), ensure_ascii=False) if report.get('subtopics') else None))

    conn.commit()
    if own_conn:
        conn.close()


def sync_clusters(clusters_data: dict, conn=None):
    """Write concept clusters to SQLite. One transaction."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("DELETE FROM cluster_meta")
    for key in ('version', 'generated_at'):
        if key in clusters_data:
            conn.execute("INSERT INTO cluster_meta (key, value) VALUES (?, ?)",
                         (key, str(clusters_data[key])))
    if clusters_data.get('parameters'):
        conn.execute("INSERT INTO cluster_meta (key, value) VALUES (?, ?)",
                     ('parameters', json.dumps(clusters_data['parameters'])))
    if clusters_data.get('stats'):
        conn.execute("INSERT INTO cluster_meta (key, value) VALUES (?, ?)",
                     ('stats', json.dumps(clusters_data['stats'])))

    conn.execute("DELETE FROM concept_clusters")
    for c in clusters_data.get('clusters', []):
        conn.execute(
            """INSERT INTO concept_clusters
               (cluster_id, label, size, articles, core_article_ids, peripheral_article_ids,
                top_topics, total_unique_claims, total_shared_claims, key_shared_claims,
                internal_edges, avg_edge_weight) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (c['cluster_id'], c.get('label', ''), c.get('size', 0),
             json.dumps(c.get('articles', []), ensure_ascii=False),
             json.dumps(c.get('core_article_ids', []), ensure_ascii=False),
             json.dumps(c.get('peripheral_article_ids', []), ensure_ascii=False),
             json.dumps(c.get('top_topics', []), ensure_ascii=False),
             c.get('total_unique_claims', 0), c.get('total_shared_claims', 0),
             json.dumps(c.get('key_shared_claims', []), ensure_ascii=False),
             c.get('internal_edges', 0), c.get('avg_edge_weight', 0)))

    conn.execute("DELETE FROM near_duplicates")
    for nd in clusters_data.get('near_duplicates', []):
        conn.execute(
            "INSERT INTO near_duplicates (article_a, article_b, title_a, title_b, known_claims, total_claims_a, overlap_ratio) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nd['article_a'], nd['article_b'], nd.get('title_a', ''),
             nd.get('title_b', ''), nd.get('known_claims', 0),
             nd.get('total_claims_a', 0), nd.get('overlap_ratio', 0)))

    conn.commit()
    if own_conn:
        conn.close()


def sync_syntheses(syntheses_data: dict, conn=None):
    """Write syntheses to SQLite. One transaction."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    conn.execute("DELETE FROM pipeline_meta WHERE key LIKE 'syntheses_%'")
    if isinstance(syntheses_data, dict):
        for key in ('version', 'generated_at'):
            if key in syntheses_data:
                conn.execute("INSERT OR REPLACE INTO pipeline_meta (key, value) VALUES (?, ?)",
                             (f"syntheses_{key}", str(syntheses_data[key])))
        if syntheses_data.get('stats'):
            conn.execute("INSERT OR REPLACE INTO pipeline_meta (key, value) VALUES (?, ?)",
                         ("syntheses_stats", json.dumps(syntheses_data['stats'])))

    synths = syntheses_data.get('syntheses', []) if isinstance(syntheses_data, dict) else syntheses_data

    conn.execute("DELETE FROM syntheses")
    for s in synths:
        conn.execute(
            """INSERT INTO syntheses
               (cluster_id, label, synthesis_markdown, article_ids, article_coverage,
                claims_covered, unique_per_article, follow_up_questions, tensions,
                generated_at, total_articles, total_claims_covered, total_claims_in_cluster)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(s['cluster_id']), s.get('label', ''), s.get('synthesis_markdown', ''),
             json.dumps(s.get('article_ids', []), ensure_ascii=False),
             json.dumps(s.get('article_coverage', {}), ensure_ascii=False),
             json.dumps(s.get('claims_covered', []), ensure_ascii=False),
             json.dumps(s.get('unique_per_article', {}), ensure_ascii=False),
             json.dumps(s.get('follow_up_questions', []), ensure_ascii=False),
             json.dumps(s.get('tensions', []), ensure_ascii=False),
             s.get('generated_at', ''),
             s.get('total_articles', 0), s.get('total_claims_covered', 0),
             s.get('total_claims_in_cluster', 0)))

    conn.commit()
    if own_conn:
        conn.close()


# --- Book sync helpers (replaces physical_books.json) ---

BOOK_FIELDS = [
    'id', 'title', 'author', 'cover_image_uri', 'cover_url', 'isbn', 'publisher',
    'year', 'page_count', 'language', 'topics', 'chapters', 'current_chapter',
    'current_page', 'reading_status', 'significance', 'added_at', 'last_interaction_at',
    'metadata_source', 'processing_status', 'kindle_asin', 'kindle_book_id',
    'finished_date', 'category', 'progress_percent',
]

BOOK_JSON_FIELDS = {'topics', 'chapters'}

CAPTURE_FIELDS = [
    'id', 'book_id', 'type', 'created_at', 'audio_uri', 'transcript',
    'transcription_status', 'photo_uri', 'ocr_text', 'ocr_status', 'text',
    'page_number', 'chapter', 'extracted_ideas', 'topics', 'key_passage',
    'elaborative_question', 'server_id', 'upload_status',
]

CAPTURE_JSON_FIELDS = {'extracted_ideas', 'topics'}


def upsert_books(books: list[dict], conn=None):
    """Upsert books into physical_books table. Client wins for same ID."""
    own = conn is None
    if own:
        conn = get_connection()
    for book in books:
        values = {}
        for f in BOOK_FIELDS:
            v = book.get(f)
            if f in BOOK_JSON_FIELDS and isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            values[f] = v
        if not values.get('id'):
            continue
        cols = ', '.join(values.keys())
        placeholders = ', '.join(['?'] * len(values))
        updates = ', '.join(f'{k}=excluded.{k}' for k in values if k != 'id')
        conn.execute(
            f'INSERT INTO physical_books ({cols}) VALUES ({placeholders}) '
            f'ON CONFLICT(id) DO UPDATE SET {updates}',
            list(values.values())
        )
    if own:
        conn.commit()
        conn.close()
    return len(books)


def upsert_captures(captures: list[dict], conn=None):
    """Upsert captures into book_captures table. Client wins for same ID."""
    own = conn is None
    if own:
        conn = get_connection()
    for cap in captures:
        values = {}
        for f in CAPTURE_FIELDS:
            v = cap.get(f)
            if f in CAPTURE_JSON_FIELDS and isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            values[f] = v
        if not values.get('id'):
            continue
        cols = ', '.join(values.keys())
        placeholders = ', '.join(['?'] * len(values))
        updates = ', '.join(f'{k}=excluded.{k}' for k in values if k != 'id')
        conn.execute(
            f'INSERT INTO book_captures ({cols}) VALUES ({placeholders}) '
            f'ON CONFLICT(id) DO UPDATE SET {updates}',
            list(values.values())
        )
    if own:
        conn.commit()
        conn.close()
    return len(captures)


def load_all_books_and_captures(conn=None) -> dict:
    """Load all books and captures from SQLite. Returns {books: [...], captures: [...]}."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        books = []
        for row in conn.execute('SELECT * FROM physical_books ORDER BY last_interaction_at DESC').fetchall():
            book = dict(row)
            for f in BOOK_JSON_FIELDS:
                if isinstance(book.get(f), str):
                    try:
                        book[f] = json.loads(book[f])
                    except (json.JSONDecodeError, TypeError):
                        pass
            books.append(book)

        captures = []
        for row in conn.execute('SELECT * FROM book_captures ORDER BY created_at DESC').fetchall():
            cap = dict(row)
            for f in CAPTURE_JSON_FIELDS:
                if isinstance(cap.get(f), str):
                    try:
                        cap[f] = json.loads(cap[f])
                    except (json.JSONDecodeError, TypeError):
                        pass
            captures.append(cap)

        return {'books': books, 'captures': captures}
    finally:
        if own:
            conn.close()


# --- Kindle books helpers (replaces kindle_library.json) ---

KINDLE_BOOK_FIELDS = [
    'key', 'asin', 'book_id', 'title', 'title_resolved', 'author', 'cover_url',
    'progress_pct', 'current_position', 'max_position', 'progress_text',
    'progress_updated', 'first_seen', 'last_seen', 'status', 'category',
    'added_to_petrarca', 'finished_date', 'last_read', 'purchase_date',
    'language', 'publisher', 'is_sideloaded', 'epub_path', 'source',
]

KINDLE_BOOL_FIELDS = {'added_to_petrarca', 'is_sideloaded'}


def upsert_kindle_books(books: list[dict], conn=None):
    """Upsert kindle books. Each dict must have 'key'. Preserves curation fields on update."""
    own = conn is None
    if own:
        conn = get_connection()
    for book in books:
        values = {}
        for f in KINDLE_BOOK_FIELDS:
            v = book.get(f)
            if f in KINDLE_BOOL_FIELDS:
                v = int(bool(v)) if v is not None else 0
            values[f] = v
        if not values.get('key'):
            continue
        cols = ', '.join(values.keys())
        placeholders = ', '.join(['?'] * len(values))
        updates = ', '.join(f'{k}=excluded.{k}' for k in values if k != 'key')
        conn.execute(
            f'INSERT INTO kindle_books ({cols}) VALUES ({placeholders}) '
            f'ON CONFLICT(key) DO UPDATE SET {updates}',
            list(values.values())
        )
    if own:
        conn.commit()
        conn.close()
    return len(books)


def get_kindle_book(key: str, conn=None) -> dict | None:
    """Get a single kindle book by key."""
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        row = conn.execute('SELECT * FROM kindle_books WHERE key = ?', (key,)).fetchone()
        if not row:
            return None
        book = dict(row)
        for f in KINDLE_BOOL_FIELDS:
            book[f] = bool(book.get(f))
        return book
    finally:
        if own:
            conn.close()


def get_kindle_books(conn=None, search=None, status=None, category=None,
                     tracked=None, sort='last_seen', order='desc',
                     limit=50, offset=0) -> tuple[list[dict], int]:
    """Query kindle books with filtering/sorting/pagination.

    Returns (books, total_count).
    """
    own = conn is None
    if own:
        conn = get_connection(readonly=True)
    try:
        where = []
        params = []

        if search:
            where.append(
                "(title LIKE ? OR title_resolved LIKE ? OR author LIKE ?)"
            )
            pattern = f'%{search}%'
            params.extend([pattern, pattern, pattern])

        if status:
            statuses = [s.strip() for s in status.split(',')]
            placeholders = ','.join(['?'] * len(statuses))
            where.append(f'status IN ({placeholders})')
            params.extend(statuses)

        if category:
            cats = [c.strip() for c in category.split(',')]
            placeholders = ','.join(['?'] * len(cats))
            where.append(f'category IN ({placeholders})')
            params.extend(cats)

        if tracked == 'true':
            where.append('added_to_petrarca = 1')
        elif tracked == 'false':
            where.append('added_to_petrarca = 0')

        where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''

        # Sort
        sort_map = {
            'recent': 'last_seen', 'last_seen': 'last_seen',
            'title': 'COALESCE(title_resolved, title)',
            'author': 'author',
            'progress': 'progress_pct',
            'purchase_date': 'purchase_date',
        }
        sort_col = sort_map.get(sort, 'last_seen')
        order_dir = 'ASC' if order == 'asc' else 'DESC'

        # Total count
        total = conn.execute(
            f'SELECT COUNT(*) FROM kindle_books{where_sql}', params
        ).fetchone()[0]

        # Fetch page
        rows = conn.execute(
            f'SELECT * FROM kindle_books{where_sql} '
            f'ORDER BY {sort_col} {order_dir} NULLS LAST '
            f'LIMIT ? OFFSET ?',
            params + [limit, offset]
        ).fetchall()

        books = []
        for row in rows:
            book = dict(row)
            for f in KINDLE_BOOL_FIELDS:
                book[f] = bool(book.get(f))
            book['title_display'] = book.get('title_resolved') or book.get('title', '')
            books.append(book)

        return books, total
    finally:
        if own:
            conn.close()


def migrate_kindle_json_to_sqlite():
    """One-time migration: kindle_library.json → kindle_books table."""
    kindle_path = Path(os.environ.get('KINDLE_DATA_PATH', '/opt/petrarca/data/kindle_library.json'))
    if not kindle_path.exists():
        print('[db] No kindle_library.json found, skipping kindle migration', flush=True)
        return

    data = json.loads(kindle_path.read_text())
    books_dict = data.get('books', {})
    if not books_dict:
        print('[db] kindle_library.json has no books, skipping', flush=True)
        return

    conn = get_connection()
    existing = conn.execute('SELECT COUNT(*) FROM kindle_books').fetchone()[0]
    if existing > 0:
        print(f'[db] kindle_books already has {existing} rows, skipping migration', flush=True)
        conn.close()
        return

    count = 0
    for key, book in books_dict.items():
        progress = book.get('progress', {}) or {}
        row = {
            'key': key,
            'asin': book.get('asin', ''),
            'book_id': book.get('book_id', ''),
            'title': book.get('title', ''),
            'title_resolved': book.get('title_resolved'),
            'author': book.get('author', ''),
            'cover_url': book.get('cover_url'),
            'progress_pct': progress.get('pct') or progress.get('percent') or 0,
            'current_position': progress.get('current_position') or 0,
            'max_position': progress.get('max_position') or 0,
            'progress_text': progress.get('text', ''),
            'progress_updated': progress.get('updated', ''),
            'first_seen': book.get('first_seen', ''),
            'last_seen': book.get('last_seen', ''),
            'status': book.get('status', 'unreviewed'),
            'category': book.get('category'),
            'added_to_petrarca': int(bool(book.get('added_to_petrarca', False))),
            'finished_date': book.get('finished_date'),
            'last_read': book.get('last_read'),
            'purchase_date': book.get('purchase_date'),
            'language': book.get('language', ''),
            'publisher': book.get('publisher', ''),
            'is_sideloaded': int(bool(book.get('is_sideloaded', False))),
            'epub_path': book.get('epub_path'),
            'source': 'kindle_mac',
        }
        cols = ', '.join(row.keys())
        placeholders = ', '.join(['?'] * len(row))
        conn.execute(
            f'INSERT OR IGNORE INTO kindle_books ({cols}) VALUES ({placeholders})',
            list(row.values())
        )
        count += 1

    conn.commit()
    conn.close()
    print(f'[db] Migrated {count} kindle books from JSON → SQLite', flush=True)


def migrate_books_json_to_sqlite():
    """One-time migration: physical_books.json → SQLite tables."""
    books_path = Path(os.environ.get('PHYSICAL_BOOKS_PATH', '/opt/petrarca/data/physical_books.json'))
    if not books_path.exists():
        print('[db] No physical_books.json found, skipping', flush=True)
        return

    data = json.loads(books_path.read_text())
    books = data.get('books', [])
    captures = data.get('captures', [])

    conn = get_connection()
    book_count = upsert_books(books, conn)
    cap_count = upsert_captures(captures, conn)
    conn.commit()
    conn.close()
    print(f'[db] Migrated {book_count} books, {cap_count} captures from JSON → SQLite', flush=True)


# --- Migration helpers ---

def migrate_projects():
    """Migrate projects.json → projects + project_notes tables."""
    projects_path = Path(os.environ.get('PROJECTS_PATH', '/opt/petrarca/data/projects.json'))
    if not projects_path.exists():
        print('[db] No projects.json found, skipping', flush=True)
        return

    data = json.loads(projects_path.read_text())
    conn = get_connection()

    for p in data.get('projects', []):
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, description, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (p['id'], p['name'], p.get('description', ''), p.get('status', 'active'), p['created_at']),
        )

    for n in data.get('notes', []):
        conn.execute(
            "INSERT OR IGNORE INTO project_notes (id, project_id, text, audio_file, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (n['id'], n['project_id'], n.get('text', ''), n.get('audio_file'),
             json.dumps(n.get('source')) if n.get('source') else None, n['created_at']),
        )

    conn.commit()
    proj_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    note_count = conn.execute("SELECT COUNT(*) FROM project_notes").fetchone()[0]
    conn.close()

    print(f'[db] Migrated {proj_count} projects, {note_count} notes', flush=True)


def migrate_review_items_to_knowledge_items(conn) -> int:
    """Collapse review_items (one per book×chapter×node) into knowledge_items (one per node).

    For each distinct (curriculum_domain, curriculum_node_id) pair in review_items, picks
    the best scheduling state (max stability, max review_count) and accumulates all
    book/chapter sources into a JSON array.  Uses INSERT OR IGNORE so running twice is safe.
    Returns count of rows inserted.
    """
    import json as _json

    groups = conn.execute('''
        SELECT curriculum_domain, curriculum_node_id,
               MAX(stability_days) as stability_days,
               MAX(due_at) as due_at,
               MAX(review_count) as review_count,
               MIN(created_at) as created_at,
               last_score
        FROM review_items
        WHERE curriculum_node_id IS NOT NULL AND curriculum_domain IS NOT NULL
        GROUP BY curriculum_domain, curriculum_node_id
    ''').fetchall()

    count = 0
    for g in groups:
        item_id = f"{g['curriculum_domain']}:{g['curriculum_node_id']}"

        rows = conn.execute('''
            SELECT source_book_id, source_chapter_number, source_chapter_title,
                   source_text, lens, temporal_hook, created_at
            FROM review_items
            WHERE curriculum_domain=? AND curriculum_node_id=?
        ''', (g['curriculum_domain'], g['curriculum_node_id'])).fetchall()

        sources = []
        seen = set()
        for r in rows:
            key = (r['source_book_id'], r['source_chapter_number'])
            if key not in seen:
                seen.add(key)
                sources.append({
                    'book_id': r['source_book_id'],
                    'chapter_number': r['source_chapter_number'],
                    'chapter_title': r['source_chapter_title'],
                    'source_text': r['source_text'] or '',
                    'lens': r['lens'] or 'SIGNIFICANCE',
                    'temporal_hook': r['temporal_hook'] or '',
                    'added_at': r['created_at'],
                })

        try:
            conn.execute('''
                INSERT OR IGNORE INTO knowledge_items
                (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                 last_score, review_count, sources, question_history, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            ''', (
                item_id, g['curriculum_node_id'], g['curriculum_domain'],
                g['stability_days'], g['due_at'], g['last_score'],
                g['review_count'], _json.dumps(sources), '[]', g['created_at'],
            ))
            count += 1
        except Exception as e:
            print(f'[migrate] skip {item_id}: {e}', flush=True)

    conn.commit()
    return count


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python db.py [init|migrate <type>]')
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'init':
        init_db()
    elif cmd == 'migrate':
        init_db()
        data_type = sys.argv[2] if len(sys.argv) > 2 else 'all'
        if data_type in ('projects', 'all'):
            migrate_projects()
        if data_type in ('knowledge_items', 'all'):
            conn = get_connection()
            n = migrate_review_items_to_knowledge_items(conn)
            conn.close()
            print(f'[db] Migrated {n} knowledge_items from review_items', flush=True)
        if data_type in ('books', 'all'):
            migrate_books_json_to_sqlite()
        if data_type in ('kindle', 'all'):
            migrate_kindle_json_to_sqlite()
    else:
        print(f'Unknown command: {cmd}')
