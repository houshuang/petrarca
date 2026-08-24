"""Queue-free capture storage tests. No production data or network calls."""

from __future__ import annotations

import json
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import numpy as np


SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from commonplace_capture import (  # noqa: E402
    audio_file_details,
    capture_id_for_audio,
    capture_processing_lock,
    create_authored_chunks,
    insert_capture_transcript,
    persist_audio,
    relative_audio_path,
    write_capture_status,
)


def test_capture_processing_lock_is_private_and_cross_process(tmp_path):
    audio_data = b"one retained browser recording" * 100
    capture_id = capture_id_for_audio(audio_data)
    lock_dir = tmp_path / "runtime-locks"
    marker = tmp_path / "child-acquired"
    child_code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from commonplace_capture import capture_processing_lock
print('ready', flush=True)
with capture_processing_lock(Path(sys.argv[2]), sys.argv[3]):
    Path(sys.argv[4]).write_text('acquired')
"""

    child = None
    with capture_processing_lock(lock_dir, capture_id):
        lock_file = lock_dir / f"{capture_id}.lock"
        assert stat.S_IMODE(lock_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(lock_file.stat().st_mode) == 0o600
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                child_code,
                str(SCRIPT_DIR),
                str(lock_dir),
                capture_id,
                str(marker),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        time.sleep(0.1)
        assert not marker.exists()
        assert child.poll() is None

    assert child is not None
    stdout, stderr = child.communicate(timeout=5)
    assert child.returncode == 0, (stdout, stderr)
    assert marker.read_text() == "acquired"
    # Do not unlink flock files after release: a waiter may still reference the
    # inode. The private runtime directory is cleared by the OS on reboot.
    assert (lock_dir / f"{capture_id}.lock").exists()


def test_overlapping_retries_transcribe_once_and_reuse_committed_row(tmp_path):
    database_path = tmp_path / "captures.sqlite"
    initial = sqlite3.connect(database_path)
    initial.execute(
        """CREATE TABLE voice_transcripts (
            id TEXT PRIMARY KEY, source TEXT, node_id TEXT, domain_id TEXT,
            node_title TEXT, transcript TEXT, audio_bytes INTEGER,
            llm_result TEXT, microlearning_triggered TEXT, created_at INTEGER,
            input_mode TEXT, audio_path TEXT
        )"""
    )
    initial.close()

    audio_data = b"same concurrent browser upload" * 100
    capture_id = capture_id_for_audio(audio_data)
    lock_dir = tmp_path / "runtime-locks"
    start = threading.Barrier(3)
    results = []
    errors = []
    transcription_calls = 0
    state_guard = threading.Lock()

    def retry_worker():
        nonlocal transcription_calls
        connection = None
        try:
            start.wait(timeout=5)
            with capture_processing_lock(lock_dir, capture_id):
                connection = sqlite3.connect(database_path)
                existing = connection.execute(
                    "SELECT transcript FROM voice_transcripts WHERE id = ?",
                    (capture_id,),
                ).fetchone()
                if existing:
                    transcript = existing[0]
                else:
                    with state_guard:
                        transcription_calls += 1
                    # Keep the first request in the paid side effect long
                    # enough for the retry to contend on the keyed lock.
                    time.sleep(0.1)
                    transcript = "One canonical transcript from the paid service."
                    inserted = insert_capture_transcript(
                        connection,
                        capture_id=capture_id,
                        transcript=transcript,
                        audio_bytes=len(audio_data),
                        audio_path=f"audio/commonplace/{capture_id}.webm",
                        created_at=1_724_000_000_000,
                    )
                    assert inserted is True
                    connection.commit()
                with state_guard:
                    results.append(transcript)
        except Exception as exc:  # pragma: no cover - asserted below
            with state_guard:
                errors.append(exc)
        finally:
            if connection is not None:
                connection.close()

    threads = [threading.Thread(target=retry_worker) for _index in range(2)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert errors == []
    assert transcription_calls == 1
    assert results == [
        "One canonical transcript from the paid service.",
        "One canonical transcript from the paid service.",
    ]
    check = sqlite3.connect(database_path)
    assert check.execute("SELECT COUNT(*) FROM voice_transcripts").fetchone()[0] == 1
    check.close()


def test_live_handler_rechecks_and_commits_inside_capture_lock():
    server = (SCRIPT_DIR / "research-server.py").read_text()
    handler = server.split("def _handle_commonplace_capture(self):", 1)[1].split(
        "def _handle_review_voice_memo", 1,
    )[0]

    lock = handler.index("with capture_processing_lock(CAPTURE_LOCK_DIR, capture_id):")
    recheck = handler.index(
        "SELECT transcript, created_at FROM voice_transcripts WHERE id = ?"
    )
    transcribe = handler.index("transcribe_on_server(audio_path)")
    commit = handler.index("transcript_conn.commit()")
    enrichment = handler.index("conn = get_connection()", commit)
    assert lock < recheck < transcribe < commit < enrichment
    assert "'/run/lock/petrarca-companion'" in server


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("thought.webm", (".webm", "audio/webm")),
        ("thought.mp4", (".mp4", "audio/mp4")),
        ("thought.m4a", (".m4a", "audio/mp4")),
        ("thought.wav", (".wav", "audio/wav")),
        ("no-extension", (".m4a", "audio/mp4")),
        ("misleading.exe", (".m4a", "audio/mp4")),
    ],
)
def test_audio_file_details_allowlists_browser_formats(filename, expected):
    assert audio_file_details(filename) == expected


def test_persist_audio_and_sidecar_are_private_and_atomic(tmp_path):
    audio_data = b"browser-audio" * 100
    capture_id = capture_id_for_audio(audio_data)
    audio_path, mime = persist_audio(
        tmp_path / "audio",
        capture_id,
        audio_data,
        "thought.webm",
    )
    assert mime == "audio/webm"
    assert audio_path.read_bytes() == audio_data
    assert stat.S_IMODE(audio_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(audio_path.parent.stat().st_mode) == 0o700
    assert not list(audio_path.parent.glob("*.partial"))

    sidecar = write_capture_status(audio_path, {"status": "completed"})
    assert json.loads(sidecar.read_text()) == {"status": "completed"}
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600
    assert relative_audio_path(audio_path, tmp_path / "audio").startswith(
        "audio/commonplace/"
    )

    # An identical retry (even with a changed browser extension) resolves to
    # the same durable file and never replaces or duplicates its bytes.
    retried_path, retried_mime = persist_audio(
        tmp_path / "audio", capture_id, audio_data, "thought.m4a",
    )
    assert retried_path == audio_path
    assert retried_mime == mime
    retained_audio = [
        path for path in audio_path.parent.glob(f"{capture_id}.*")
        if path.suffix in {".m4a", ".mp4", ".webm", ".wav", ".ogg"}
    ]
    assert retained_audio == [audio_path]


def test_capture_id_is_deterministic_and_bound_to_audio(tmp_path):
    first = b"same browser blob" * 100
    second = b"different browser blob" * 100
    assert capture_id_for_audio(first) == capture_id_for_audio(first)
    assert capture_id_for_audio(first) != capture_id_for_audio(second)
    assert capture_id_for_audio(first).startswith("cpc_sha256_")

    with pytest.raises(ValueError, match="does not match audio content"):
        persist_audio(
            tmp_path / "audio", capture_id_for_audio(first), second, "thought.webm",
        )


def test_insert_capture_transcript_does_not_touch_scheduling_tables():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE voice_transcripts (
            id TEXT PRIMARY KEY, source TEXT, node_id TEXT, domain_id TEXT,
            node_title TEXT, transcript TEXT, audio_bytes INTEGER,
            llm_result TEXT, microlearning_triggered TEXT, created_at INTEGER,
            input_mode TEXT, audio_path TEXT
        );
        CREATE TABLE knowledge_items (id TEXT PRIMARY KEY);
        CREATE TABLE microlearning_cards (id TEXT PRIMARY KEY);
        CREATE TABLE microlearning_quizzes (id TEXT PRIMARY KEY);
        CREATE TABLE structural_cards (id TEXT PRIMARY KEY);
        INSERT INTO knowledge_items VALUES ('ki-before');
        INSERT INTO microlearning_cards VALUES ('ml-before');
        INSERT INTO microlearning_quizzes VALUES ('quiz-before');
        INSERT INTO structural_cards VALUES ('struct-before');
        """
    )
    before = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "knowledge_items",
            "microlearning_cards",
            "microlearning_quizzes",
            "structural_cards",
        )
    }

    assert insert_capture_transcript(
        conn,
        capture_id="cpc_1720000000000_deadbeef",
        transcript="Sumer developed in the marshy land between two rivers.",
        audio_bytes=1234,
        audio_path="audio/commonplace/cpc_1720000000000_deadbeef.webm",
        created_at=1720000000000,
    ) is True

    # The content-addressed request can be replayed after a lost response. The
    # first committed transcript wins and no scheduling row is duplicated.
    assert insert_capture_transcript(
        conn,
        capture_id="cpc_1720000000000_deadbeef",
        transcript="A second transcription result that must not replace the first.",
        audio_bytes=1234,
        audio_path="audio/commonplace/cpc_1720000000000_deadbeef.webm",
        created_at=1720000000001,
    ) is False

    row = conn.execute("SELECT * FROM voice_transcripts").fetchone()
    assert row[1] == "commonplace_capture"
    assert row[6] == 1234
    assert row[7] is None
    assert row[8] == "[]"
    assert row[10] == "audio"
    assert conn.execute("SELECT COUNT(*) FROM voice_transcripts").fetchone()[0] == 1
    assert "Sumer developed" in row[5]
    assert {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in before
    } == before


def test_empty_audio_and_transcript_fail_without_artifacts(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        persist_audio(
            tmp_path / "audio",
            "cpc_1720000000000_deadbeef",
            b"",
            "thought.webm",
        )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE voice_transcripts (
            id TEXT, source TEXT, node_id TEXT, domain_id TEXT, node_title TEXT,
            transcript TEXT, audio_bytes INTEGER, llm_result TEXT,
            microlearning_triggered TEXT, created_at INTEGER, input_mode TEXT,
            audio_path TEXT)"""
    )
    with pytest.raises(ValueError, match="transcript is empty"):
        insert_capture_transcript(
            conn,
            capture_id="cpc_1720000000000_deadbeef",
            transcript="   ",
            audio_bytes=10,
            audio_path="audio/commonplace/test.webm",
        )
    assert conn.execute("SELECT COUNT(*) FROM voice_transcripts").fetchone()[0] == 0


def test_authored_chunker_writes_only_exact_raw_speech():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE transcript_chunks (
            id TEXT PRIMARY KEY, transcript_id TEXT, chunk_text TEXT,
            chunk_type TEXT, embedding BLOB
        );
        CREATE TABLE chunk_node_links (chunk_id TEXT, node_id TEXT);
        CREATE TABLE chunk_entity_links (chunk_id TEXT, entity_name TEXT);
        """
    )
    transcript = "First exact paragraph about a marshy plain.\n\nSecond exact paragraph about two rivers."
    chunks = create_authored_chunks(
        conn,
        transcript_id="cpc_1720000000000_deadbeef",
        transcript=transcript,
        embed_batch=lambda texts: [np.asarray([index, 1], dtype=np.float32)
                                   for index, _text in enumerate(texts)],
    )
    rows = conn.execute(
        "SELECT chunk_text, chunk_type FROM transcript_chunks ORDER BY rowid"
    ).fetchall()
    assert chunks == 2
    assert rows == [
        ("First exact paragraph about a marshy plain.", "raw_speech"),
        ("Second exact paragraph about two rivers.", "raw_speech"),
    ]
    assert all(text in transcript for text, _kind in rows)
    assert conn.execute("SELECT COUNT(*) FROM chunk_node_links").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM chunk_entity_links").fetchone()[0] == 0

    # Retrying the post-transcript indexing step is idempotent.
    assert create_authored_chunks(
        conn,
        transcript_id="cpc_1720000000000_deadbeef",
        transcript=transcript,
        embed_batch=lambda _texts: (_ for _ in ()).throw(AssertionError("must not embed twice")),
    ) == 0
