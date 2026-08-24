"""Focused tests for authored-only, channel-neutral resurfacing.

All tests use an in-memory SQLite fixture.  They never touch production data or
call an embedding/LLM service.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest


SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import commonplace_engine as companion


SCHEMA = """
CREATE TABLE voice_transcripts (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    node_id TEXT,
    domain_id TEXT,
    node_title TEXT,
    transcript TEXT NOT NULL,
    audio_bytes INTEGER,
    llm_result TEXT,
    microlearning_triggered TEXT DEFAULT '[]',
    created_at INTEGER NOT NULL,
    input_mode TEXT
);
CREATE TABLE transcript_chunks (
    id TEXT PRIMARY KEY,
    transcript_id TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    embedding BLOB
);
CREATE TABLE commonplace_events (
    id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    query_source TEXT NOT NULL DEFAULT 'manual',
    audio_bytes INTEGER DEFAULT 0,
    echo_chunk_ids TEXT NOT NULL DEFAULT '[]',
    echo_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE resurfacing_runs (
    id TEXT PRIMARY KEY,
    run_key TEXT UNIQUE NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('daily','pull')),
    local_date TEXT,
    timezone TEXT NOT NULL DEFAULT 'Europe/Oslo',
    context_hash TEXT,
    algorithm_version TEXT NOT NULL,
    seed TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER
);
CREATE TABLE resurfacing_run_items (
    run_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_subkey TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    score REAL NOT NULL,
    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id,position),
    UNIQUE(run_id,item_id)
);
CREATE TABLE resurfacing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    item_id TEXT,
    channel TEXT NOT NULL DEFAULT 'web',
    event TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);
"""


@pytest.fixture(autouse=True)
def private_key(monkeypatch):
    monkeypatch.setenv("PETRARCA_RESURFACING_KEY", "unit-test-resurfacing-key")


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    yield db
    db.close()


def _old_ms(days: int = 100) -> int:
    return int(time.time() * 1000) - days * 86_400_000


def _insert_voice(conn, *, row_id: str, transcript: str, source: str = "elicitation",
                  input_mode: str | None = "audio", audio_bytes: int = 1000,
                  node_title: str = "Private topic") -> None:
    conn.execute(
        """INSERT INTO voice_transcripts
           (id, source, node_id, domain_id, node_title, transcript,
            audio_bytes, created_at, input_mode)
           VALUES (?, ?, 'node', 'domain', ?, ?, ?, ?, ?)""",
        (row_id, source, node_title, transcript, audio_bytes, _old_ms(), input_mode),
    )
    conn.commit()


def _blob(values) -> bytes:
    return np.asarray(values, dtype=np.float32).tobytes()


def _state_dump(conn) -> str:
    values = []
    for table in ("resurfacing_runs", "resurfacing_run_items", "resurfacing_events"):
        values.extend(str(dict(row)) for row in conn.execute(f"SELECT * FROM {table}"))
    return "\n".join(values)


def test_find_resurface_uses_only_exact_raw_speech_and_collapses_duplicates(conn, monkeypatch):
    transcript = "I remember the exact authored sentence about two rivers and a marshy plain."
    _insert_voice(conn, row_id="entity_alias", transcript=transcript,
                  source="voice_capture_entity")
    _insert_voice(conn, row_id="canonical_capture", transcript=transcript,
                  source="voice_capture")
    _insert_voice(conn, row_id="test_capture", transcript="Synthetic words must never surface.",
                  input_mode="test")

    rows = [
        ("raw_a", "entity_alias", "exact authored sentence", "raw_speech", _blob([1, 0])),
        ("raw_b", "canonical_capture", "two rivers and a marshy plain", "raw_speech", _blob([1, 0])),
        ("generated", "canonical_capture", "LLM paraphrase presented as fact", "captured_fact", _blob([1, 0])),
        ("not_exact", "canonical_capture", "words that are not in the transcript", "raw_speech", _blob([1, 0])),
        ("test_raw", "test_capture", "Synthetic words", "raw_speech", _blob([1, 0])),
    ]
    conn.executemany(
        "INSERT INTO transcript_chunks (id, transcript_id, chunk_text, chunk_type, embedding) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    monkeypatch.setattr(companion, "_embed_query", lambda _text: np.asarray([1, 0], dtype=np.float32))

    result = companion.find_resurface("rivers in an alluvial plain", conn, min_age_days=0,
                                      sim_threshold=0.5, max_results=8)

    assert len(result["echoes"]) == 1
    echo = result["echoes"][0]
    assert echo["chunk_type"] == "raw_speech"
    assert echo["chunk_text"] in transcript
    assert echo["transcript_excerpt"] in transcript
    assert echo["transcript_id"] == "canonical_capture"
    assert result["meta"]["authored_only"] is True
    assert "LLM paraphrase" not in str(result)
    assert "Synthetic words" not in str(result)

    excluded = companion.find_resurface(
        "rivers in an alluvial plain", conn, min_age_days=0,
        sim_threshold=0.5, exclude_transcript_ids=["entity_alias"],
    )
    assert excluded["echoes"] == []


def test_daily_selector_handles_chunkless_voice_and_persists_no_authored_text(conn):
    secret = (
        "My private recollection begins with a landscape and follows the argument through "
        "several historical turns. " * 8
    ).strip()
    _insert_voice(conn, row_id="duplicate_entity", transcript=secret,
                  source="voice_capture_entity")
    _insert_voice(conn, row_id="preferred_capture", transcript=secret,
                  source="voice_capture")
    _insert_voice(conn, row_id="synthetic", transcript="Synthetic production fixture text.",
                  input_mode="test")

    first = companion.select_resurfacing(conn, "daily", local_date="2026-08-24")
    again = companion.select_resurfacing(conn, "daily", local_date="2026-08-24")

    assert first == again
    assert first["item"] is not None
    assert first["item"]["text"] in secret
    assert len(first["item"]["text"]) <= companion.MAX_DAILY_TEXT_CHARS
    assert first["item"]["source_label"] == "Voice capture"
    assert first["item"]["trust_label"] == "verified_audio"
    assert first["item"]["word_count"] == len(first["item"]["text"].split())
    full_context = companion.get_resurfacing_context(
        conn, first["run_id"], first["item"]["item_id"],
    )
    assert full_context["text"] == secret
    assert full_context["word_count"] == len(secret.split())
    assert conn.execute("SELECT COUNT(*) FROM resurfacing_runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM resurfacing_run_items").fetchone()[0] == 1
    provenance = json.loads(conn.execute(
        "SELECT provenance_json FROM resurfacing_run_items"
    ).fetchone()[0])
    assert sorted(provenance["aliases"]) == ["duplicate_entity", "preferred_capture"]
    assert secret not in _state_dump(conn)
    assert "Synthetic production fixture" not in str(first)


def test_selected_is_not_exposure_but_opened_starts_cooldown(conn):
    transcript = "A sufficiently substantial spoken recollection that is suitable for later resurfacing."
    _insert_voice(conn, row_id="only_voice", transcript=transcript)

    day_one = companion.select_resurfacing(conn, "daily", local_date="2026-08-24")
    day_two = companion.select_resurfacing(conn, "daily", local_date="2026-08-25")
    assert day_one["item"]["item_id"] == day_two["item"]["item_id"]

    companion.record_resurfacing_event(
        conn, day_two["run_id"], day_two["item"]["item_id"], "web", "opened"
    )
    day_three = companion.select_resurfacing(conn, "daily", local_date="2026-08-26")
    assert day_three is None
    assert conn.execute("SELECT COUNT(*) FROM resurfacing_runs").fetchone()[0] == 2


def test_event_metadata_drops_all_free_text(conn):
    secret = "This exact transcript and query must not enter an event table."
    _insert_voice(conn, row_id="voice", transcript=secret)
    run = companion.select_resurfacing(conn, "daily", local_date="2026-08-24")

    event_id = companion.record_resurfacing_event(
        conn, run["run_id"], run["item"]["item_id"], "app", "opened",
        metadata={
            "duration_ms": 1234,
            "reason_code": "user-opened",
            "query_text": secret,
            "transcript": secret,
            "note": secret,
        },
    )
    row = conn.execute("SELECT metadata_json FROM resurfacing_events WHERE id=?", (event_id,)).fetchone()
    assert json.loads(row[0]) == {"duration_ms": 1234, "reason_code": "user-opened"}
    assert secret not in _state_dump(conn)

    capture_event = companion.record_resurfacing_event(
        conn, None, "cpc_abc123", "app", "record_completed",
        metadata={"echo_count": 2, "query_text": secret},
    )
    capture_meta = conn.execute(
        "SELECT metadata_json FROM resurfacing_events WHERE id=?", (capture_event,),
    ).fetchone()[0]
    assert json.loads(capture_meta) == {"echo_count": 2}


def test_pull_context_is_keyed_and_idempotent(conn):
    transcript = "An old authored observation about river systems, agriculture, and political organization."
    query = "How did control of water influence early states?"
    _insert_voice(conn, row_id="voice", transcript=transcript)

    first = companion.select_resurfacing(
        conn, "pull", local_date="2026-08-24", context_hash=query,
    )
    again = companion.select_resurfacing(
        conn, "pull", local_date="2026-08-24", context_hash=query,
    )
    stored = conn.execute("SELECT context_hash, run_key FROM resurfacing_runs").fetchone()

    assert first == again
    assert first["item"]["text"] in transcript
    assert stored["context_hash"].startswith("hmac-sha256:")
    assert query not in stored["context_hash"]
    assert query not in stored["run_key"]
    assert query not in _state_dump(conn)


def test_legacy_commonplace_log_hashes_query(conn):
    query = "A private current thought that should never be duplicated into history."
    event_id = companion.log_event(
        query,
        [{"chunk_id": "raw_chunk_1", "chunk_text": "authored output is not persisted here"}],
        conn,
        query_source="manual",
    )
    row = conn.execute("SELECT * FROM commonplace_events WHERE id=?", (event_id,)).fetchone()

    assert row["query_text"].startswith("hmac-sha256:")
    assert query not in str(dict(row))
    assert json.loads(row["echo_chunk_ids"]) == ["raw_chunk_1"]


def test_context_refuses_to_return_changed_source(conn):
    transcript = "An authored recording whose snapshot should remain tied to these exact words."
    _insert_voice(conn, row_id="voice", transcript=transcript)
    run = companion.select_resurfacing(conn, "daily", local_date="2026-08-24")
    conn.execute("UPDATE voice_transcripts SET transcript='Different replacement words' WHERE id='voice'")
    conn.commit()

    assert companion.get_resurfacing_context(
        conn, run["run_id"], run["item"]["item_id"],
    ) is None


def test_source_and_quality_allowlist_and_request_validation(conn):
    _insert_voice(
        conn, row_id="unknown_source",
        transcript="This recording has enough words and characters but comes from an untrusted source adapter.",
        source="agent_generated",
    )
    _insert_voice(
        conn, row_id="too_few_words",
        transcript="One two three four five six seven-very-long-characters-here",
        source="elicitation",
    )
    _insert_voice(
        conn, row_id="too_short",
        transcript="one two three four five six seven eight",
        source="elicitation",
    )

    empty = companion.select_resurfacing(conn, "daily", local_date="2026-08-24")
    assert empty is None
    assert conn.execute("SELECT COUNT(*) FROM resurfacing_runs").fetchone()[0] == 0

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        companion.select_resurfacing(conn, "daily", local_date="2026-2-30")
    with pytest.raises(ValueError, match="invalid timezone"):
        companion.select_resurfacing(conn, "daily", local_date="2026-08-24", timezone="Mars/Olympus")


def test_browser_recorder_has_durable_recovery_before_upload():
    html = (SCRIPT_DIR / "commonplace_companion.html").read_text()
    finish = html.split("const finishRecording = async () => {", 1)[1].split(
        "const startRecording = async () => {", 1,
    )[0]
    attempt = html.split("const attemptPendingUpload = async () => {", 1)[1].split(
        "const finishRecording = async () => {", 1,
    )[0]

    assert "indexedDB.open(RECORDING_DB, 1)" in html
    assert "db.createObjectStore(RECORDING_STORE, { keyPath: 'id' })" in html
    assert 'id="retry-upload"' in html
    assert 'id="download-recording"' in html
    assert "const MAX_UPLOAD_BYTES = 20 * 1024 * 1024" in html
    assert "const MAX_RECORDING_SECONDS = 8 * 60" in html
    assert "recorder.start(1000)" in html
    assert finish.index("await persistCompletedRecording") < finish.index("await attemptPendingUpload")
    assert attempt.index("await uploadRecording") < attempt.index("await clearDurableLocalRecovery")
    assert attempt.index("await clearDurableLocalRecovery") < attempt.index("pendingRecording = null")
    assert "The local recovery copy is still available to retry or download" in attempt


def test_browser_recovery_is_capability_keyed_ciphertext_and_guards_recording_lifecycle():
    html = (SCRIPT_DIR / "commonplace_companion.html").read_text()
    save = html.split("const savePendingRecording = async (recording) => {", 1)[1].split(
        "const loadStoredRecording = async () => {", 1,
    )[0]
    encryption = html.split("const encryptPendingRecording = async (recording) => {", 1)[1].split(
        "const decryptPendingRecording = async (stored) => {", 1,
    )[0]
    finish = html.split("const finishRecording = async () => {", 1)[1].split(
        "const requestStopRecording =", 1,
    )[0]
    pagehide = html.split("window.addEventListener('pagehide', () => {", 1)[1].split(
        "window.addEventListener('pageshow'", 1,
    )[0]

    assert "petrarca-private-[0-9a-f]{64}" in html
    assert "RECOVERY_KEY_CONTEXT" in html
    assert "window.crypto.subtle.digest('SHA-256'" in html
    assert "{ name: 'AES-GCM'" in encryption
    assert "window.crypto.getRandomValues(new Uint8Array(12))" in encryption
    assert "ciphertext" in encryption and "iv: iv.buffer" in encryption
    assert "store.put(encrypted)" in save
    assert "store.put(recording)" not in html
    assert html.index("window.crypto.subtle.encrypt") < html.index("store.put(encrypted)")
    assert "Encrypted browser recovery is not supported" in html
    assert "persistenceUnavailable = true" in finish
    assert "Download the in-memory recording before upload" in finish

    assert "Clear after download" in html
    assert "pendingRecording.downloaded" in html
    assert "Download the recording before clearing" in html
    assert "startingRecording || finishingRecording || uploadInFlight" in html
    assert "const requestStopRecording" in html
    assert "recorder.stop()" in html
    assert "hasUnsafeActiveCapture()" in html
    assert "recorder?.state === 'recording'" in pagehide
    assert "requestStopRecording" in pagehide
    assert "window.addEventListener('beforeunload'" in html


def test_active_media_chunks_are_encrypted_incrementally_and_promoted_before_cleanup():
    html = (SCRIPT_DIR / "commonplace_companion.html").read_text()
    active_encrypt = html.split("const encryptActiveChunk = async", 1)[1].split(
        "const decryptActiveChunk = async", 1,
    )[0]
    enqueue = html.split("const enqueueActiveChunkPersistence =", 1)[1].split(
        "const loadActiveChunkRecording =", 1,
    )[0]
    load_active = html.split("const loadActiveChunkRecording =", 1)[1].split(
        "const clearActiveChunkRecovery =", 1,
    )[0]
    promote = html.split("const persistCompletedRecording =", 1)[1].split(
        "const clearDurableLocalRecovery =", 1,
    )[0]
    restore = html.split("const restorePendingRecording =", 1)[1].split(
        "const supportedMime =", 1,
    )[0]
    finish = html.split("const finishRecording = async () => {", 1)[1].split(
        "const requestStopRecording =", 1,
    )[0]
    data_handler = html.split("recorder.addEventListener('dataavailable'", 1)[1].split(
        "recorder.addEventListener('stop'", 1,
    )[0]

    assert "ACTIVE_SESSION_RECORD_ID = 'active-session'" in html
    assert "ACTIVE_CHUNK_PREFIX = 'active-chunk:'" in html
    assert "activeChunkWriteChain = activeChunkWriteChain.then" in enqueue
    assert "encryptActiveChunk(" in enqueue
    assert "store.put(encrypted)" in enqueue
    assert "store.put(updatedSession)" in enqueue
    assert "ciphertext" in active_encrypt and "iv: iv.buffer" in active_encrypt
    assert "chunk.arrayBuffer()" in active_encrypt
    assert "blob:" not in active_encrypt
    assert "store.put(chunk)" not in html
    assert "store.put(recording)" not in html

    assert data_handler.index("audioParts.push(event.data)") < data_handler.index(
        "enqueueActiveChunkPersistence(event.data, audioBytes)",
    )
    assert finish.index("await activeChunkWriteChain") < finish.index(
        "const blob = new Blob(audioParts",
    )
    assert finish.index("await persistCompletedRecording") < finish.index(
        "await attemptPendingUpload",
    )
    assert promote.index("await savePendingRecording(recording)") < promote.index(
        "await clearActiveChunkRecovery()",
    )

    assert restore.index("await loadPendingRecording()") < restore.index(
        "await loadActiveChunkRecording()",
    )
    assert ".sort((left, right) => left.sequence - right.sequence)" in load_active
    assert "sessionChunks[sequence].sequence !== sequence" in load_active
    assert "plaintextChunks.push(await decryptActiveChunk" in load_active
    assert "blob: new Blob(plaintextChunks" in load_active
    assert "Recovered ${active.chunkCount} encrypted chunks" in restore


def test_companion_javascript_parses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    html = (SCRIPT_DIR / "commonplace_companion.html").read_text()
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    subprocess.run(
        [node, "-e", "new Function(process.argv[1])", script],
        check=True,
        capture_output=True,
        text=True,
    )


def test_capture_handler_uses_content_identity_and_replays_canonical_transcript():
    server = (SCRIPT_DIR / "research-server.py").read_text()
    handler = server.split("def _handle_commonplace_capture(self):", 1)[1].split(
        "def _handle_review_voice_memo", 1,
    )[0]

    assert "capture_id = capture_id_for_audio(audio_data)" in handler
    assert handler.index("persist_audio(") < handler.index("transcribe_on_server(audio_path)")
    assert "SELECT transcript, created_at FROM voice_transcripts WHERE id = ?" in handler
    assert "if existing_row:" in handler
    assert "transcript = existing_row['transcript']" in handler
    assert "'idempotent_replay': not inserted" in handler
