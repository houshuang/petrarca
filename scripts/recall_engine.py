"""Desktop-first, provenance-preserving recall for the private Companion.

The selector uses only questions backed by prior user interaction. It never
turns the generated inventory into a due queue, and it never generates new
questions. Runs snapshot the exact question and answer so later quality analysis
is stable even if the canonical review system regenerates a knowledge-item cue.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


ALGORITHM_VERSION = "encountered-recall-v1"
QUESTION_COOLDOWN_DAYS = 30
MAX_EXCLUDED_ITEMS = 100
MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 5_000
MAX_NOTE_CHARS = 4_000

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}")
_NOTE_KINDS = {"thought", "inquiry", "question_feedback", "correction"}
_EVENTS = {
    "opened",
    "revealed",
    "skipped",
    "quality_good",
    "quality_bad",
    "note_opened",
    "note_saved",
    "graded",
    "client_error",
}
_EVENT_METADATA_KEYS = {
    "elapsed_ms",
    "visible_ms",
    "response_ms",
    "reveal_ms",
    "revealed",
    "reason_code",
    "error_code",
    "score",
    "kind",
    "char_count",
    "source_table",
}


def _private_key() -> bytes:
    value = os.environ.get("PETRARCA_RESURFACING_KEY", "")
    if len(value.encode("utf-8")) < 32:
        raise RuntimeError("PETRARCA_RESURFACING_KEY must contain at least 32 bytes")
    return value.encode("utf-8")


def _digest(label: str, value: str, length: int = 32) -> str:
    payload = f"petrarca-recall\0{label}\0{value}".encode("utf-8")
    return hmac.new(_private_key(), payload, hashlib.sha256).hexdigest()[:length]


def _validate_id(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not _ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} is invalid")
    return normalized


def _validate_local_context(local_date: str | None, timezone: str) -> tuple[str, str]:
    zone_name = str(timezone or "Europe/Oslo")
    try:
        zone = ZoneInfo(zone_name)
    except Exception as exc:
        raise ValueError("invalid timezone") from exc
    if local_date is None:
        local_date = datetime.now(zone).date().isoformat()
    try:
        parsed = datetime.strptime(str(local_date), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("local_date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != str(local_date):
        raise ValueError("local_date must be YYYY-MM-DD")
    return parsed.isoformat(), zone_name


def _clean_text(value: Any, maximum: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) > maximum:
        return ""
    return text


def _question_kind(question: str, answer: str) -> str:
    first = question.casefold().split(" ", 1)[0].rstrip("?'\"")
    if first in {"when", "where", "who", "which"}:
        return "factual_anchor"
    if first == "what" and len(answer) <= 500:
        return "factual_anchor"
    if first in {"why", "how"}:
        return "conceptual_connection"
    return "retrieval_prompt"


def _item_id(source_table: str, source_id: str, question: str) -> str:
    question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()
    return "rq_" + _digest("item", f"{source_table}\0{source_id}\0{question_hash}", 28)


def _safe_json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _quiz_candidates(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT q.id, q.question, q.answer, q.rich_answer, q.quiz_type,
                  q.review_count, q.last_score, q.created_at,
                  c.title, c.query, c.source_domain, c.source_node_id
           FROM microlearning_quizzes q
           JOIN microlearning_cards c ON c.id = q.card_id
           WHERE q.status = 'active' AND q.review_count > 0
             AND c.status = 'completed'
           ORDER BY q.review_count DESC, q.created_at DESC"""
    ).fetchall()
    candidates = []
    for row in rows:
        item = dict(row)
        question = _clean_text(item.get("question"), MAX_QUESTION_CHARS)
        answer = _clean_text(item.get("rich_answer") or item.get("answer"), MAX_ANSWER_CHARS)
        if len(question) < 12 or len(answer) < 2:
            continue
        kind = item.get("quiz_type") or _question_kind(question, answer)
        title = _clean_text(item.get("title") or item.get("query"), 300)
        candidates.append({
            "source_table": "microlearning_quizzes",
            "source_id": item["id"],
            "question": question,
            "answer": answer,
            "question_kind": kind,
            "source_domain": item.get("source_domain") or "",
            "source_node_id": item.get("source_node_id") or "",
            "source_title": title,
            "last_score": item.get("last_score") or "",
            "review_count": int(item.get("review_count") or 0),
        })
    return candidates


def _knowledge_candidates(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT k.id, k.cached_question, k.curriculum_domain,
                  k.curriculum_node_id, k.review_count, k.last_score,
                  n.title AS node_title
           FROM knowledge_items k
           LEFT JOIN curriculum_nodes n
             ON n.id = k.curriculum_node_id AND n.domain_id = k.curriculum_domain
           WHERE k.review_count > 0 AND k.cached_question IS NOT NULL
           ORDER BY k.review_count DESC, k.last_reviewed_at DESC"""
    ).fetchall()
    candidates = []
    for row in rows:
        item = dict(row)
        payload = _safe_json(item.get("cached_question"))
        question = _clean_text(payload.get("question"), MAX_QUESTION_CHARS)
        answer = _clean_text(
            payload.get("rich_answer") or payload.get("answer") or payload.get("answer_guidance"),
            MAX_ANSWER_CHARS,
        )
        if len(question) < 12 or len(answer) < 2:
            continue
        # These generic shells are known generation failures, not useful cues.
        if question.casefold().startswith("what was historically significant about"):
            continue
        candidates.append({
            "source_table": "knowledge_items",
            "source_id": item["id"],
            "question": question,
            "answer": answer,
            "question_kind": payload.get("quiz_type") or _question_kind(question, answer),
            "source_domain": item.get("curriculum_domain") or "",
            "source_node_id": item.get("curriculum_node_id") or "",
            "source_title": _clean_text(item.get("node_title"), 300),
            "last_score": item.get("last_score") or "",
            "review_count": int(item.get("review_count") or 0),
        })
    return candidates


def _load_run(conn, run_key: str) -> dict | None:
    row = conn.execute(
        """SELECT r.id AS run_id, r.mode, r.local_date, r.timezone,
                  i.item_id, i.question_text, i.answer_text, i.provenance_json
           FROM recall_runs r
           JOIN recall_run_items i ON i.run_id = r.id AND i.position = 0
           WHERE r.run_key = ?""",
        (run_key,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    provenance = _safe_json(data.get("provenance_json"))
    return {
        "run_id": data["run_id"],
        "mode": data["mode"],
        "local_date": data["local_date"],
        "item": {
            "item_id": data["item_id"],
            "question": data["question_text"],
            "answer": data["answer_text"],
            **provenance,
        },
    }


def _priority(candidate: dict, run_key: str) -> float:
    recall_need = {"missed": 6.0, "partly": 4.0, "knew": 1.5}.get(
        candidate.get("last_score"), 1.0
    )
    encountered = min(candidate.get("review_count", 0), 6) * 0.35
    concise = 1.0 if len(candidate["answer"]) <= 700 else 0.0
    factual = 0.8 if candidate["question_kind"] == "factual_anchor" else 0.0
    source_balance = 0.6 if candidate["source_table"] == "microlearning_quizzes" else 0.0
    random_bits = int(_digest("rank", f"{run_key}\0{candidate['item_id']}", 8), 16)
    deterministic_mix = (random_bits / 0xFFFFFFFF) * 3.0
    return recall_need + encountered + concise + factual + source_balance + deterministic_mix


def select_question(
    conn,
    *,
    selection_id: str,
    mode: str = "daily",
    local_date: str | None = None,
    timezone: str = "Europe/Oslo",
    exclude_item_ids: list[str] | None = None,
) -> dict:
    """Return one encountered question and persist an idempotent run snapshot."""
    selection_id = _validate_id(selection_id, "selection_id")
    if mode not in {"daily", "pull"}:
        raise ValueError("mode must be daily or pull")
    local_date, timezone = _validate_local_context(local_date, timezone)
    excluded = {str(value) for value in (exclude_item_ids or [])}
    if len(excluded) > MAX_EXCLUDED_ITEMS:
        raise ValueError("exclude_item_ids is invalid")

    run_key = "hmac-sha256:" + _digest("selection", selection_id, 64)
    existing = _load_run(conn, run_key)
    if existing:
        return existing

    candidates = _quiz_candidates(conn) + _knowledge_candidates(conn)
    for candidate in candidates:
        candidate["item_id"] = _item_id(
            candidate["source_table"], candidate["source_id"], candidate["question"]
        )
    candidates = [candidate for candidate in candidates if candidate["item_id"] not in excluded]
    if not candidates:
        raise LookupError("No encountered questions are available")

    cutoff = int(time.time() * 1000) - QUESTION_COOLDOWN_DAYS * 86_400_000
    recent = {
        row["item_id"]
        for row in conn.execute(
            """SELECT DISTINCT item_id FROM recall_events
               WHERE created_at >= ? AND event IN ('opened','revealed','graded')""",
            (cutoff,),
        ).fetchall()
    }
    cooled = [candidate for candidate in candidates if candidate["item_id"] not in recent]
    if cooled:
        candidates = cooled

    chosen = max(candidates, key=lambda candidate: _priority(candidate, run_key))
    score = _priority(chosen, run_key)
    run_id = "rrc_" + _digest("run", selection_id, 24)
    now = int(time.time() * 1000)
    provenance = {
        "source_table": chosen["source_table"],
        "source_type": "reviewed_quiz" if chosen["source_table"] == "microlearning_quizzes" else "reviewed_knowledge_item",
        "source_domain": chosen["source_domain"],
        "source_node_id": chosen["source_node_id"],
        "source_title": chosen["source_title"],
        "question_kind": chosen["question_kind"],
        "last_score": chosen["last_score"],
        "review_count": chosen["review_count"],
        "algorithm_version": ALGORITHM_VERSION,
    }
    try:
        conn.execute(
            """INSERT INTO recall_runs
               (id, run_key, mode, local_date, timezone, algorithm_version, seed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, run_key, mode, local_date, timezone, ALGORITHM_VERSION,
             _digest("seed", selection_id, 24), now),
        )
        conn.execute(
            """INSERT INTO recall_run_items
               (run_id, position, item_id, source_table, source_id,
                question_text, answer_text, question_hash, answer_hash,
                provenance_json, score)
               VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                chosen["item_id"],
                chosen["source_table"],
                chosen["source_id"],
                chosen["question"],
                chosen["answer"],
                hashlib.sha256(chosen["question"].encode("utf-8")).hexdigest(),
                hashlib.sha256(chosen["answer"].encode("utf-8")).hexdigest(),
                json.dumps(provenance, ensure_ascii=False, separators=(",", ":")),
                score,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        concurrent = _load_run(conn, run_key)
        if concurrent:
            return concurrent
        raise
    return _load_run(conn, run_key)


def _resolve_item(conn, run_id: str, item_id: str):
    run_id = _validate_id(run_id, "run_id")
    item_id = _validate_id(item_id, "item_id")
    row = conn.execute(
        """SELECT i.*, r.mode FROM recall_run_items i
           JOIN recall_runs r ON r.id = i.run_id
           WHERE i.run_id = ? AND i.item_id = ?""",
        (run_id, item_id),
    ).fetchone()
    if not row:
        raise ValueError("recall item does not belong to this run")
    return dict(row)


def _clean_metadata(metadata: Any) -> dict:
    if not isinstance(metadata, dict):
        return {}
    clean = {}
    for key, value in metadata.items():
        if key not in _EVENT_METADATA_KEYS:
            continue
        if isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            clean[key] = max(0, min(int(value), 86_400_000))
        elif isinstance(value, str) and len(value) <= 80:
            clean[key] = value
    return clean


def record_event(
    conn,
    *,
    event_id: str,
    run_id: str,
    item_id: str,
    event: str,
    metadata: dict | None = None,
) -> int:
    event_id = _validate_id(event_id, "event_id")
    if event not in _EVENTS:
        raise ValueError("event is invalid")
    _resolve_item(conn, run_id, item_id)
    event_key = "hmac-sha256:" + _digest("event", event_id, 64)
    clean = _clean_metadata(metadata)
    cursor = conn.execute(
        """INSERT OR IGNORE INTO recall_events
           (event_key, run_id, item_id, event, metadata_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (event_key, run_id, item_id, event,
         json.dumps(clean, separators=(",", ":")), int(time.time() * 1000)),
    )
    conn.commit()
    if cursor.rowcount == 1:
        return int(cursor.lastrowid)
    row = conn.execute("SELECT id FROM recall_events WHERE event_key = ?", (event_key,)).fetchone()
    return int(row["id"])


def record_grade(
    conn,
    *,
    response_id: str,
    run_id: str,
    item_id: str,
    score: str,
    response_ms: int | None = None,
    reveal_ms: int | None = None,
) -> dict:
    response_id = _validate_id(response_id, "response_id")
    if score not in {"knew", "missed"}:
        raise ValueError("score must be knew or missed")
    item = _resolve_item(conn, run_id, item_id)
    if item["source_table"] not in {"microlearning_quizzes", "knowledge_items"}:
        raise ValueError("question source cannot be graded")
    from review_engine import record_answer

    result = record_answer(
        item["source_id"], score, conn,
        idempotency_key=f"recall:{response_id}",
        allow_background_generation=False,
    )
    if not result:
        raise LookupError("canonical review item is unavailable")
    event_id = record_event(
        conn,
        event_id=f"grade:{response_id}",
        run_id=run_id,
        item_id=item_id,
        event="graded",
        metadata={
            "score": score,
            "response_ms": response_ms or 0,
            "reveal_ms": reveal_ms or 0,
            "source_table": item["source_table"],
        },
    )
    return {**result, "event_id": event_id}


def save_note(
    conn,
    *,
    note_id: str,
    run_id: str,
    item_id: str,
    kind: str,
    text: str,
) -> dict:
    note_id = _validate_id(note_id, "note_id")
    _resolve_item(conn, run_id, item_id)
    if kind not in _NOTE_KINDS:
        raise ValueError("note kind is invalid")
    note = str(text or "").strip()
    if not note:
        raise ValueError("note text is required")
    if len(note) > MAX_NOTE_CHARS:
        raise ValueError(f"note must be at most {MAX_NOTE_CHARS} characters")
    note_key = "hmac-sha256:" + _digest("note", note_id, 64)
    cursor = conn.execute(
        """INSERT OR IGNORE INTO recall_notes
           (id, note_key, run_id, item_id, kind, note_text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("rn_" + _digest("note-row", note_id, 24), note_key, run_id, item_id,
         kind, note, int(time.time() * 1000)),
    )
    created = cursor.rowcount == 1
    if not created:
        existing = conn.execute(
            '''SELECT run_id, item_id, kind, note_text FROM recall_notes
               WHERE note_key=?''',
            (note_key,),
        ).fetchone()
        if not existing or (
            existing['run_id'] != run_id
            or existing['item_id'] != item_id
            or existing['kind'] != kind
            or existing['note_text'] != note
        ):
            raise ValueError('note_id was already used for different note content')
    conn.commit()
    event_id = record_event(
        conn,
        event_id=f"note:{note_id}",
        run_id=run_id,
        item_id=item_id,
        event="note_saved",
        metadata={"kind": kind, "char_count": len(note)},
    )
    return {"saved": True, "idempotent_replay": not created, "event_id": event_id}
