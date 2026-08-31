"""Focused tests for the private desktop recall loop."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import types
import shutil
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import recall_engine as recall  # noqa: E402


SCHEMA = """
CREATE TABLE microlearning_cards (
    id TEXT PRIMARY KEY,
    title TEXT,
    query TEXT NOT NULL,
    source_domain TEXT,
    source_node_id TEXT,
    status TEXT NOT NULL,
    review_count INTEGER DEFAULT 0
);
CREATE TABLE microlearning_quizzes (
    id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    rich_answer TEXT,
    quiz_type TEXT,
    status TEXT NOT NULL,
    review_count INTEGER DEFAULT 0,
    last_score TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE curriculum_nodes (
    id TEXT NOT NULL,
    domain_id TEXT NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY(domain_id, id)
);
CREATE TABLE knowledge_items (
    id TEXT PRIMARY KEY,
    cached_question TEXT,
    curriculum_domain TEXT NOT NULL,
    curriculum_node_id TEXT NOT NULL,
    review_count INTEGER DEFAULT 0,
    last_score TEXT,
    last_reviewed_at INTEGER
);
CREATE TABLE recall_runs (
    id TEXT PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL,
    local_date TEXT NOT NULL,
    timezone TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    seed TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE recall_run_items (
    run_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_id TEXT NOT NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    question_hash TEXT NOT NULL,
    answer_hash TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    score REAL NOT NULL,
    PRIMARY KEY(run_id, position),
    UNIQUE(run_id, item_id)
);
CREATE TABLE recall_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    event TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE recall_notes (
    id TEXT PRIMARY KEY,
    note_key TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    note_text TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


@pytest.fixture(autouse=True)
def private_key(monkeypatch):
    monkeypatch.setenv("PETRARCA_RESURFACING_KEY", "unit-test-recall-key-that-is-at-least-32-bytes")


@pytest.fixture
def conn():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.executescript(SCHEMA)
    yield database
    database.close()


def _insert_quiz(
    conn,
    *,
    quiz_id: str,
    question: str,
    answer: str,
    review_count: int = 1,
    last_score: str = "knew",
    status: str = "active",
    card_status: str = "completed",
):
    card_id = f"card-{quiz_id}"
    conn.execute(
        """INSERT INTO microlearning_cards
           (id, title, query, source_domain, source_node_id, status)
           VALUES (?, ?, ?, 'sicily', 'node', ?)""",
        (card_id, f"Title for {quiz_id}", f"Query for {quiz_id}", card_status),
    )
    conn.execute(
        """INSERT INTO microlearning_quizzes
           (id, card_id, question, answer, status, review_count, last_score, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1000)""",
        (quiz_id, card_id, question, answer, status, review_count, last_score),
    )
    conn.commit()


def _select(conn, selection_id="selection-00000001", excluded=None):
    return recall.select_question(
        conn,
        selection_id=selection_id,
        mode="daily",
        local_date="2026-08-31",
        timezone="Europe/Oslo",
        exclude_item_ids=excluded or [],
    )


def test_selection_uses_only_encountered_completed_active_questions(conn):
    _insert_quiz(
        conn,
        quiz_id="reviewed",
        question="What made Sicily's 1848 revolt significant in timing?",
        answer="It began before the Paris uprising.",
        review_count=2,
        last_score="missed",
    )
    _insert_quiz(
        conn,
        quiz_id="unreviewed",
        question="A generated question the user never encountered?",
        answer="It must not appear.",
        review_count=0,
        last_score="",
    )
    _insert_quiz(
        conn,
        quiz_id="pending-parent",
        question="A question from incomplete material?",
        answer="It must not appear either.",
        card_status="pending",
    )

    selected = _select(conn)

    assert selected["item"]["question"] == "What made Sicily's 1848 revolt significant in timing?"
    assert selected["item"]["source_type"] == "reviewed_quiz"
    assert selected["item"]["source_table"] == "microlearning_quizzes"
    assert "unreviewed" not in str(selected)
    assert conn.execute("SELECT COUNT(*) FROM recall_runs").fetchone()[0] == 1


def test_selection_is_idempotent_and_snapshots_question_before_regeneration(conn):
    _insert_quiz(
        conn,
        quiz_id="stable",
        question="When did Aristotle live?",
        answer="384–322 BCE.",
    )
    first = _select(conn)
    conn.execute(
        "UPDATE microlearning_quizzes SET question='A changed canonical cue?' WHERE id='stable'"
    )
    conn.commit()

    replay = _select(conn)

    assert replay == first
    assert replay["item"]["question"] == "When did Aristotle live?"
    assert conn.execute("SELECT COUNT(*) FROM recall_runs").fetchone()[0] == 1


def test_another_respects_exclusion_but_cooldown_falls_back_when_pool_is_small(conn):
    _insert_quiz(conn, quiz_id="one", question="When did Aristotle live?", answer="384–322 BCE.")
    _insert_quiz(conn, quiz_id="two", question="Where was Caesar killed?", answer="The Theatre of Pompey.")
    first = _select(conn, "selection-00000001")
    recall.record_event(
        conn,
        event_id="event-open-00000001",
        run_id=first["run_id"],
        item_id=first["item"]["item_id"],
        event="opened",
    )
    second = _select(
        conn,
        "selection-00000002",
        excluded=[first["item"]["item_id"]],
    )
    assert second["item"]["item_id"] != first["item"]["item_id"]

    # A fresh session can still receive something when every tiny-pool item is
    # cooling down; cooldown is not allowed to turn the app into an empty queue.
    recall.record_event(
        conn,
        event_id="event-open-00000002",
        run_id=second["run_id"],
        item_id=second["item"]["item_id"],
        event="opened",
    )
    third = _select(conn, "selection-00000003")
    assert third["item"] is not None


def test_generic_knowledge_shells_are_excluded_but_real_reviewed_items_can_surface(conn):
    conn.execute(
        "INSERT INTO curriculum_nodes VALUES ('node-real', 'rome', 'The Punic Wars')"
    )
    conn.execute(
        "INSERT INTO curriculum_nodes VALUES ('node-shell', 'rome', 'Generic topic')"
    )
    conn.execute(
        """INSERT INTO knowledge_items VALUES
           ('rome:real', ?, 'rome', 'node-real', 3, 'missed', 2000),
           ('rome:shell', ?, 'rome', 'node-shell', 5, 'missed', 3000)""",
        (
            json.dumps({
                "question": "Why did Rome destroy Carthage after it ceased to be a military threat?",
                "rich_answer": "The memory of Hannibal remained politically powerful.",
            }),
            json.dumps({
                "question": "What was historically significant about Generic topic?",
                "rich_answer": "A generic answer.",
            }),
        ),
    )
    conn.commit()

    selected = _select(conn)

    assert selected["item"]["source_type"] == "reviewed_knowledge_item"
    assert selected["item"]["source_title"] == "The Punic Wars"
    assert "Generic topic" not in str(selected)


def test_events_are_idempotent_and_drop_free_text_metadata(conn):
    _insert_quiz(conn, quiz_id="evented", question="When did Aristotle live?", answer="384–322 BCE.")
    selected = _select(conn)
    kwargs = {
        "event_id": "event-reveal-00000001",
        "run_id": selected["run_id"],
        "item_id": selected["item"]["item_id"],
        "event": "revealed",
        "metadata": {
            "elapsed_ms": 1234,
            "revealed": True,
            "note": "private text must not enter analytics metadata",
            "question_text": "also forbidden",
        },
    }

    first = recall.record_event(conn, **kwargs)
    second = recall.record_event(conn, **kwargs)

    assert second == first
    assert conn.execute("SELECT COUNT(*) FROM recall_events").fetchone()[0] == 1
    stored = json.loads(conn.execute("SELECT metadata_json FROM recall_events").fetchone()[0])
    assert stored == {"elapsed_ms": 1234, "revealed": True}


def test_note_text_is_stored_only_in_note_table_and_is_idempotent(conn):
    _insert_quiz(conn, quiz_id="noted", question="When did Aristotle live?", answer="384–322 BCE.")
    selected = _select(conn)
    secret = "How did Aristotle's years overlap with Macedon's rise?"
    kwargs = {
        "note_id": "note-client-00000001",
        "run_id": selected["run_id"],
        "item_id": selected["item"]["item_id"],
        "kind": "inquiry",
        "text": secret,
    }

    first = recall.save_note(conn, **kwargs)
    second = recall.save_note(conn, **kwargs)

    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert conn.execute("SELECT note_text FROM recall_notes").fetchone()[0] == secret
    event_dump = "\n".join(
        row[0] for row in conn.execute("SELECT metadata_json FROM recall_events")
    )
    assert secret not in event_dump
    assert json.loads(event_dump) == {"kind": "inquiry", "char_count": len(secret)}


def test_grade_uses_canonical_source_and_idempotency_receipt(conn, monkeypatch):
    _insert_quiz(conn, quiz_id="graded", question="When did Aristotle live?", answer="384–322 BCE.")
    selected = _select(conn)
    calls = []
    fake_review_engine = types.ModuleType("review_engine")

    def fake_record_answer(
        item_id, score, connection, idempotency_key=None,
        allow_background_generation=True,
    ):
        calls.append((
            item_id, score, idempotency_key, connection is conn,
            allow_background_generation,
        ))
        return {"next_due_at": 123, "new_stability_days": 9.5}

    fake_review_engine.record_answer = fake_record_answer
    monkeypatch.setitem(sys.modules, "review_engine", fake_review_engine)

    result = recall.record_grade(
        conn,
        response_id="response-client-00000001",
        run_id=selected["run_id"],
        item_id=selected["item"]["item_id"],
        score="knew",
        response_ms=2500,
        reveal_ms=1400,
    )

    assert calls == [(
        "graded", "knew", "recall:response-client-00000001", True, False,
    )]
    assert result["new_stability_days"] == 9.5
    event = conn.execute("SELECT event, metadata_json FROM recall_events").fetchone()
    assert event["event"] == "graded"
    assert json.loads(event["metadata_json"])["score"] == "knew"


def test_invalid_note_kind_and_oversized_exclusions_fail_closed(conn):
    _insert_quiz(conn, quiz_id="safe", question="When did Aristotle live?", answer="384–322 BCE.")
    selected = _select(conn)
    with pytest.raises(ValueError, match="note kind"):
        recall.save_note(
            conn,
            note_id="note-client-00000002",
            run_id=selected["run_id"],
            item_id=selected["item"]["item_id"],
            kind="instructions",
            text="Do something else",
        )
    with pytest.raises(ValueError, match="exclude_item_ids"):
        recall.select_question(
            conn,
            selection_id="selection-00000004",
            local_date="2026-08-31",
            exclude_item_ids=[f"rq_{index:03d}" for index in range(101)],
        )


def test_note_retry_rejects_changed_content(conn):
    _insert_quiz(conn, quiz_id="stable-note", question="When did Aristotle live?", answer="384–322 BCE.")
    selected = _select(conn)
    arguments = {
        "note_id": "note-client-stable-01",
        "run_id": selected["run_id"],
        "item_id": selected["item"]["item_id"],
        "kind": "question_feedback",
    }
    recall.save_note(conn, text="The original feedback.", **arguments)

    with pytest.raises(ValueError, match="different note content"):
        recall.save_note(conn, text="Changed text under the same retry ID.", **arguments)

    assert conn.execute("SELECT note_text FROM recall_notes").fetchone()[0] == "The original feedback."


def test_private_page_is_desktop_quiz_first_and_preserves_secondary_commonplace():
    html = (SCRIPT_DIR / "commonplace_companion.html").read_text()
    recall_position = html.index('id="recall-question"')
    secondary_position = html.index('id="commonplace-tools"')
    recorder_position = html.index('id="record"')

    assert recall_position < secondary_position < recorder_position
    assert 'id="reveal-answer"' in html
    assert 'id="grade-knew"' in html
    assert 'id="grade-missed"' in html
    assert 'id="quality-good"' in html
    assert 'id="quality-bad"' in html
    assert 'data-note-kind="question_feedback"' in html
    assert "postJson('recall/select'" in html
    assert "postJson('recall/grade'" in html
    assert "postJson('recall/note'" in html
    assert "recallEvent(`quality_${quality}`" in html
    assert "One question, not a queue. A skip is neutral." in html


def test_private_page_javascript_parses():
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


def test_server_and_nginx_expose_only_exact_recall_capability_routes():
    server = (SCRIPT_DIR / "research-server.py").read_text()
    template = (SCRIPT_DIR / "nginx-petrarca-companion.conf.template").read_text()
    for route in ("select", "event", "grade", "note"):
        assert f"if self.path == '/recall/{route}'" in server
        block = template.split(
            f"location = /__CAPABILITY_PATH__/recall/{route}", 1
        )[1].split("location ", 1)[0]
        assert "access_log off;" in block
        assert "error_log /dev/null crit;" in block
        assert "limit_except POST { deny all; }" in block
        assert f"proxy_pass http://127.0.0.1:8090/recall/{route};" in block
    assert "location ^~ /__CAPABILITY_PATH__/" in template
    assert "return 404;" in template
