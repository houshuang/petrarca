"""Canonical SQLite tables for the bounded reading-study pilot."""
SCHEMA = '''
CREATE TABLE IF NOT EXISTS study_focus (
 id INTEGER PRIMARY KEY CHECK(id=1), study_id TEXT, active INTEGER NOT NULL DEFAULT 0,
 activated_at INTEGER, prior_counts TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS study_items (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL, version TEXT NOT NULL,
 kind TEXT NOT NULL, payload TEXT NOT NULL, ordinal INTEGER NOT NULL,
 introduced_at INTEGER, suspended INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS study_positions (
 id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES study_items(id), testable INTEGER NOT NULL DEFAULT 1,
 stability_days REAL NOT NULL DEFAULT 1, due_at INTEGER NOT NULL DEFAULT 0,
 last_reviewed_at INTEGER, last_score TEXT, review_count INTEGER NOT NULL DEFAULT 0,
 fsrs_card_json TEXT, cached_question TEXT
);
CREATE TABLE IF NOT EXISTS study_runs (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL, created_at INTEGER NOT NULL,
 mode TEXT NOT NULL, snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_events (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES study_runs(id),
 item_id TEXT NOT NULL, event TEXT NOT NULL, created_at INTEGER NOT NULL,
 payload TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS study_events_item_time ON study_events(item_id,created_at);
CREATE TABLE IF NOT EXISTS study_audio (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES study_runs(id),
 item_id TEXT NOT NULL, audio_path TEXT NOT NULL, sha256 TEXT NOT NULL,
 created_at INTEGER NOT NULL, input_mode TEXT NOT NULL DEFAULT 'audio',
 transcript TEXT, response_kind TEXT NOT NULL DEFAULT 'recall',
 transcription_status TEXT NOT NULL DEFAULT 'pending',
 transcription_updated_at INTEGER NOT NULL DEFAULT 0,
 UNIQUE(run_id,item_id,response_kind,sha256)
);
CREATE TABLE IF NOT EXISTS study_transcriptions (
 id TEXT PRIMARY KEY, audio_id TEXT NOT NULL REFERENCES study_audio(id),
 created_at INTEGER NOT NULL, metadata TEXT NOT NULL, transcript TEXT, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_sources (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_revisions (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL, created_at INTEGER NOT NULL,
 code_commit TEXT NOT NULL, design_version TEXT NOT NULL, payload TEXT NOT NULL
);
'''

# Additive tables: existing audio and practice snapshots are never rewritten.
SCHEMA += """
CREATE TABLE IF NOT EXISTS study_audio_attempts (
 id TEXT PRIMARY KEY, audio_id TEXT NOT NULL REFERENCES study_audio(id),
 run_id TEXT NOT NULL, item_id TEXT NOT NULL, response_kind TEXT NOT NULL,
 sha256 TEXT NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS study_assessments (
 run_id TEXT PRIMARY KEY REFERENCES study_runs(id), occasion TEXT NOT NULL,
 volume INTEGER NOT NULL, coverage TEXT NOT NULL, help_state TEXT NOT NULL,
 protocol_version TEXT NOT NULL, created_at INTEGER NOT NULL
);
"""

SCHEMA += """
CREATE TABLE IF NOT EXISTS study_intake (
 source_id TEXT PRIMARY KEY, audio_sha256 TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL, source TEXT NOT NULL, draft TEXT,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS study_intake_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL REFERENCES study_intake(source_id),
 state TEXT NOT NULL, created_at INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_monthly_samples (
 month TEXT PRIMARY KEY, created_at INTEGER NOT NULL, payload TEXT NOT NULL
);
"""

# Original recording -> one bounded, reviewed explanation -> optional targets.
# These records do not enter scheduling until a target is selected explicitly.
SCHEMA += """
CREATE TABLE IF NOT EXISTS study_reading_intents (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL, source_id TEXT NOT NULL,
 audio_sha256 TEXT NOT NULL, transcript_sha256 TEXT NOT NULL, source_quote TEXT NOT NULL,
 source_start INTEGER NOT NULL, source_end INTEGER NOT NULL,
 question TEXT NOT NULL, basis TEXT NOT NULL CHECK(basis IN ('explicit','inferred')),
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS study_reading_briefs (
 id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES study_reading_intents(id),
 payload TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS study_reading_active_intent
 ON study_reading_briefs(intent_id) WHERE active=1;
CREATE TABLE IF NOT EXISTS study_reading_targets (
 id TEXT PRIMARY KEY, payload TEXT NOT NULL, content_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_reading_brief_targets (
 brief_id TEXT NOT NULL REFERENCES study_reading_briefs(id),
 target_id TEXT NOT NULL REFERENCES study_reading_targets(id),
 PRIMARY KEY(brief_id,target_id)
);
CREATE TABLE IF NOT EXISTS study_reading_selections (
 target_id TEXT PRIMARY KEY REFERENCES study_reading_targets(id),
 item_id TEXT NOT NULL UNIQUE REFERENCES study_items(id),
 selected_at INTEGER NOT NULL
);
"""
