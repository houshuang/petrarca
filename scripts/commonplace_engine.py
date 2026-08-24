"""Private, authored-source resurfacing for Petrarca.

``find_resurface`` is associative pull over exact ``raw_speech`` excerpts.
``select_resurfacing`` is a channel-neutral daily/pull selector over canonical
voice transcripts. Generated analysis chunks are never presented as the
user's words, and resurfacing state never stores transcript or query text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo


DEFAULT_MIN_AGE_DAYS = 30
DEFAULT_SIM_THRESHOLD = 0.55
ALGORITHM_VERSION = "authored-voice-v1"
MAX_DAILY_TEXT_CHARS = 600
DELIVERY_COOLDOWN_DAYS = 30

_DEV_PROCESS_KEY = secrets.token_bytes(32)
_SOURCE_PRIORITY = {
    "voice_capture": 0,
    "voice_capture_entity": 1,
    "commonplace_capture": 2,
    "elicitation": 3,
    "insight": 4,
    "explore_capture": 5,
    "defender_response": 6,
}
VOICE_SOURCE_ALLOWLIST = (
    "elicitation", "review_memo", "book_note",
    "explore_capture", "voice_capture", "voice_capture_entity", "insight",
    "era_sweep", "resurfacing_response", "commonplace_capture",
)
_EVENTS = {
    "selected", "delivered", "opened", "expanded", "played", "responded",
    "snoozed", "hidden", "saved", "connected", "another",
    "record_started", "record_completed",
}
_CHANNELS = {"app", "web", "email", "podcast"}
_SAFE_METADATA_NUMBERS = {
    "duration_ms", "position", "similarity", "snoozed_until", "delivery_attempt",
    "echo_count",
}
_SAFE_METADATA_TOKENS = {"client_event_id", "reason_code", "status"}


def _connection_is_local(conn) -> bool:
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
        filenames = [str(row[2] or "") for row in rows]
    except Exception:
        return False
    if not filenames or all(not name or name == ":memory:" for name in filenames):
        return True
    return all(name.startswith(("/tmp/", "/private/tmp/")) for name in filenames)


def _resurfacing_key(conn=None) -> bytes:
    """Get a server-only key, permitting a process key only for local tests."""
    value = os.environ.get("PETRARCA_RESURFACING_KEY") or os.environ.get("PETRARCA_INGEST_TOKEN")
    if value:
        return value.encode("utf-8")
    if conn is not None and _connection_is_local(conn):
        return _DEV_PROCESS_KEY
    if os.environ.get("PETRARCA_ENV", "").lower() in {"test", "development", "dev"}:
        return _DEV_PROCESS_KEY
    raise RuntimeError("PETRARCA_RESURFACING_KEY (or PETRARCA_INGEST_TOKEN) is required")


def _normalize_authored_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text or "").split()).casefold()


def _private_hash(text: str, conn=None) -> str:
    digest = hmac.new(
        _resurfacing_key(conn),
        _normalize_authored_text(text).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def hash_resurfacing_context(query_text: str, conn=None) -> str:
    """Return a keyed marker safe to persist instead of a private query."""
    return _private_hash(query_text, conn)


def _safe_context_hash(value: str | None, conn) -> str | None:
    if not value:
        return None
    if re.fullmatch(r"(?:hmac-)?sha256:[0-9a-f]{64}", value):
        return value
    return hash_resurfacing_context(value, conn)


def _embed_query(text: str):
    try:
        from limbic.amygdala import EmbeddingModel

        return EmbeddingModel().embed(text)
    except Exception as exc:
        print(f"[commonplace] embedding unavailable: {exc}", flush=True)
        return None


def _row_dict(row) -> dict[str, Any]:
    return dict(row)


def _load_voice_rows(conn, cutoff_ms: int) -> list[dict[str, Any]]:
    source_placeholders = ",".join("?" for _ in VOICE_SOURCE_ALLOWLIST)
    sql = f"""SELECT id, source, node_id, domain_id, node_title, transcript,
                    audio_bytes, created_at, input_mode
             FROM voice_transcripts
             WHERE created_at < ?
               AND source IN ({source_placeholders})
               AND COALESCE(input_mode, '') != 'test'
               AND length(trim(transcript)) >= 40
             ORDER BY created_at, id"""
    params = (cutoff_ms, *VOICE_SOURCE_ALLOWLIST)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        if "input_mode" not in str(exc):
            raise
        rows = conn.execute(
            f"""SELECT id, source, node_id, domain_id, node_title, transcript,
                      audio_bytes, created_at, NULL AS input_mode
               FROM voice_transcripts
               WHERE created_at < ?
                 AND source IN ({source_placeholders})
                 AND length(trim(transcript)) >= 40
               ORDER BY created_at, id""",
            params,
        ).fetchall()
    return [
        _row_dict(row) for row in rows
        if len(str(row["transcript"] or "").split()) >= 8
    ]


def _canonical_rank(row: dict[str, Any]) -> tuple:
    return (
        0 if row.get("input_mode") == "audio" else 1,
        0 if int(row.get("audio_bytes") or 0) > 0 else 1,
        _SOURCE_PRIORITY.get(str(row.get("source") or ""), 50),
        int(row.get("created_at") or 0),
        str(row.get("id") or ""),
    )


def _dedupe_voice_rows(rows: Iterable[dict[str, Any]], conn) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        normalized = _normalize_authored_text(str(row.get("transcript") or ""))
        if normalized:
            groups.setdefault(normalized, []).append(row)

    candidates: list[dict[str, Any]] = []
    for normalized, aliases in groups.items():
        ordered = sorted(aliases, key=_canonical_rank)
        canonical = dict(ordered[0])
        content_hash = _private_hash(normalized, conn)
        canonical["aliases"] = [str(row["id"]) for row in ordered]
        canonical["content_hash"] = content_hash
        canonical["item_id"] = f"voice:{content_hash.split(':', 1)[1][:24]}"
        candidates.append(canonical)
    return candidates


def _source_label(source: str) -> str:
    return {
        "elicitation": "Voice elicitation",
        "voice_capture": "Voice capture",
        "voice_capture_entity": "Voice capture",
        "commonplace_capture": "Companion recording",
        "explore_capture": "Voice capture",
        "insight": "Insight recording",
        "defender_response": "Defender response",
        "era_sweep": "Knowledge sweep",
        "resurfacing_response": "Resurfacing response",
    }.get(source, "Voice recording")


def _trust_label(row: dict[str, Any]) -> str:
    if row.get("input_mode") == "audio" or int(row.get("audio_bytes") or 0) > 0:
        return "verified_audio"
    if row.get("input_mode") == "text_json":
        return "user_text"
    return "legacy_unstamped"


def _trust_quality(row: dict[str, Any]) -> float:
    return {"verified_audio": 1.0, "user_text": 0.9, "legacy_unstamped": 0.75}[
        _trust_label(row)
    ]


def _stable_fraction(seed: str, item_id: str) -> float:
    digest = hashlib.sha256(f"{seed}:{item_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _exact_excerpt(text: str, seed: str, item_id: str,
                   max_chars: int = MAX_DAILY_TEXT_CHARS) -> str:
    """Choose a deterministic exact slice of authored text."""
    if len(text) <= max_chars:
        return text
    starts = [0]
    starts.extend(match.end() for match in re.finditer(r"(?:\n\s*\n|(?<=[.!?])\s+)", text))
    starts = [start for start in starts if start < len(text) - 40]
    index = min(len(starts) - 1, int(_stable_fraction(seed, item_id) * len(starts)))
    start = starts[index]
    hard_end = min(len(text), start + max_chars)
    if hard_end < len(text):
        boundary = max(
            text.rfind(". ", start + 80, hard_end),
            text.rfind("? ", start + 80, hard_end),
            text.rfind("! ", start + 80, hard_end),
            text.rfind("\n", start + 80, hard_end),
        )
        end = boundary + 1 if boundary >= start + 80 else hard_end
    else:
        end = hard_end
    return text[start:end]


def _candidate_history(conn) -> dict[str, dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    rows = conn.execute(
        """SELECT item_id,
                  SUM(CASE WHEN event IN ('delivered','opened') THEN 1 ELSE 0 END) AS deliveries,
                  MAX(CASE WHEN event IN ('delivered','opened') THEN created_at END) AS last_delivered,
                  MAX(CASE WHEN event='hidden' THEN created_at END) AS hidden_at
           FROM resurfacing_events
           WHERE item_id IS NOT NULL
           GROUP BY item_id"""
    ).fetchall()
    for row in rows:
        history[str(row["item_id"])] = _row_dict(row)
    return history


def _score_candidate(candidate: dict[str, Any], history: dict[str, Any],
                     now_ms: int, seed: str) -> tuple[float, dict[str, float]]:
    created_at = int(candidate.get("created_at") or 0)
    age_days = max(0.0, (now_ms - created_at) / 86_400_000)
    deliveries = int(history.get("deliveries") or 0)
    last_delivered = int(history.get("last_delivered") or 0)
    provenance = 35.0 * _trust_quality(candidate)
    if deliveries == 0:
        unseen_or_overdue = 25.0
    else:
        overdue = max(0.0, (now_ms - last_delivered) / 86_400_000 - DELIVERY_COOLDOWN_DAYS)
        unseen_or_overdue = 25.0 * min(1.0, overdue / 90.0)
    age = 15.0 * min(1.0, age_days / 365.0)
    words = len(str(candidate.get("transcript") or "").split())
    length_quality = 10.0 * min(1.0, words / 80.0)
    jitter = 10.0 * _stable_fraction(seed, str(candidate["item_id"]))
    breakdown = {
        "provenance": round(provenance, 6),
        "unseen_or_overdue": round(unseen_or_overdue, 6),
        "age": round(age, 6),
        "length_quality": round(length_quality, 6),
        "stable_jitter": round(jitter, 6),
    }
    return round(sum(breakdown.values()), 6), breakdown


def _local_date(timezone: str, now_ms: int) -> str:
    return datetime.fromtimestamp(now_ms / 1000, ZoneInfo(timezone)).date().isoformat()


def _validate_local_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        raise ValueError("local_date must use YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError("local_date must be a real YYYY-MM-DD date") from exc
    if parsed != value:
        raise ValueError("local_date must use zero-padded YYYY-MM-DD")
    return parsed


def _run_seed(run_key: str, conn) -> str:
    return _private_hash(f"seed:{run_key}", conn)


def _serialize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_run_item_context(conn, run_id: str,
                           item_id: str | None = None) -> dict[str, Any] | None:
    params: list[Any] = [run_id]
    item_clause = ""
    if item_id is not None:
        item_clause = " AND ri.item_id = ?"
        params.append(item_id)
    row = conn.execute(
        f"""SELECT r.id AS run_id, r.mode, r.local_date, r.timezone, r.seed,
                   ri.position, ri.item_id, ri.source_id, ri.source_subkey,
                   ri.content_hash, ri.provenance_json, ri.score,
                   ri.score_breakdown_json
            FROM resurfacing_runs r
            JOIN resurfacing_run_items ri ON ri.run_id = r.id
            WHERE r.id = ?{item_clause}
            ORDER BY ri.position LIMIT 1""",
        params,
    ).fetchone()
    return _row_dict(row) if row else None


def get_resurfacing_context(conn, run_id: str, item_id: str) -> dict | None:
    """Resolve a run item to its full canonical authored transcript."""
    item = _load_run_item_context(conn, run_id, item_id)
    if not item:
        return None
    try:
        provenance = json.loads(item.get("provenance_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        provenance = {}
    source_ids = [str(item["source_id"])]
    source_ids.extend(str(value) for value in provenance.get("aliases", []) if value)
    source_ids = list(dict.fromkeys(source_ids))
    placeholders = ",".join("?" for _ in source_ids)
    try:
        rows = conn.execute(
            f"""SELECT id, source, node_title, transcript, audio_bytes, created_at, input_mode
                FROM voice_transcripts
                WHERE id IN ({placeholders}) AND COALESCE(input_mode, '') != 'test'""",
            source_ids,
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "input_mode" not in str(exc):
            raise
        rows = conn.execute(
            f"""SELECT id, source, node_title, transcript, audio_bytes, created_at,
                       NULL AS input_mode
                FROM voice_transcripts WHERE id IN ({placeholders})""",
            source_ids,
        ).fetchall()
    source = None
    for row in rows:
        candidate = _row_dict(row)
        if _private_hash(str(candidate.get("transcript") or ""), conn) == item["content_hash"]:
            source = candidate
            break
    if source is None:
        return None
    text = str(source["transcript"])
    return {
        "text": text,
        "item_id": item["item_id"],
        "source_label": _source_label(str(source.get("source") or "")),
        "trust_label": _trust_label(source),
        "date": int(source.get("created_at") or 0),
        "node_title": source.get("node_title") or "",
        "word_count": len(text.split()),
    }


def _get_selection_context(conn, run_id: str, item_id: str) -> dict | None:
    """Resolve the bounded excerpt returned by the selection endpoint."""
    context = get_resurfacing_context(conn, run_id, item_id)
    item = _load_run_item_context(conn, run_id, item_id)
    if not context or not item:
        return None
    excerpt = _exact_excerpt(context["text"], str(item["seed"]), item_id)
    return {**context, "text": excerpt, "word_count": len(excerpt.split())}


def _existing_run(conn, run_key: str) -> dict | None:
    row = conn.execute("SELECT id FROM resurfacing_runs WHERE run_key = ?", (run_key,)).fetchone()
    if not row:
        return None
    run_id = str(row["id"])
    item = _load_run_item_context(conn, run_id)
    context = _get_selection_context(conn, run_id, str(item["item_id"])) if item else None
    return {"run_id": run_id, "item": context}


def select_resurfacing(conn, mode, local_date=None, timezone="Europe/Oslo",
                       exclude_item_ids=None, context_hash=None) -> dict:
    """Select and persist one channel-neutral authored voice item."""
    if mode not in {"daily", "pull"}:
        raise ValueError("mode must be 'daily' or 'pull'")
    try:
        ZoneInfo(timezone)
    except Exception as exc:
        raise ValueError(f"invalid timezone: {timezone}") from exc
    now_ms = int(time.time() * 1000)
    date_value = _validate_local_date(local_date) if local_date else _local_date(timezone, now_ms)
    safe_context = _safe_context_hash(context_hash, conn)
    if mode == "daily":
        run_key = f"daily:{date_value}:{timezone}"
    else:
        marker = safe_context or _private_hash(f"pull:{uuid.uuid4().hex}", conn)
        run_key = f"pull:{date_value}:{timezone}:{marker}"
    existing = _existing_run(conn, run_key)
    if existing:
        return existing

    seed = _run_seed(run_key, conn)
    cutoff_ms = now_ms - DEFAULT_MIN_AGE_DAYS * 86_400_000
    candidates = _dedupe_voice_rows(_load_voice_rows(conn, cutoff_ms), conn)
    excluded = set(exclude_item_ids or [])
    history = _candidate_history(conn)
    scored: list[tuple[float, dict[str, Any], dict[str, float]]] = []
    for candidate in candidates:
        item_id = str(candidate["item_id"])
        if item_id in excluded:
            continue
        item_history = history.get(item_id, {})
        if item_history.get("hidden_at"):
            continue
        last_delivered = int(item_history.get("last_delivered") or 0)
        if last_delivered and now_ms - last_delivered < DELIVERY_COOLDOWN_DAYS * 86_400_000:
            continue
        score, breakdown = _score_candidate(candidate, item_history, now_ms, seed)
        scored.append((score, candidate, breakdown))
    scored.sort(key=lambda entry: (-entry[0], str(entry[1]["item_id"])))

    # A selection with no eligible authored item is not a run. In particular,
    # do not let an empty idempotency record mask a later eligible capture.
    if not scored:
        return None

    run_id = f"rs_{int(time.time())}_{uuid.uuid4().hex[:10]}"
    expires_at = now_ms + (2 if mode == "daily" else 7) * 86_400_000
    conn.execute(
        """INSERT OR IGNORE INTO resurfacing_runs
           (id, run_key, mode, local_date, timezone, context_hash,
            algorithm_version, seed, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, run_key, mode, date_value, timezone, safe_context,
         ALGORITHM_VERSION, seed, now_ms, expires_at),
    )
    actual = conn.execute("SELECT id FROM resurfacing_runs WHERE run_key = ?", (run_key,)).fetchone()
    actual_run_id = str(actual["id"])
    if actual_run_id == run_id:
        score, candidate, breakdown = scored[0]
        provenance = {
            "aliases": candidate.get("aliases", []),
            "input_mode": candidate.get("input_mode"),
            "source": candidate.get("source"),
            "trust_label": _trust_label(candidate),
        }
        conn.execute(
            """INSERT INTO resurfacing_run_items
               (run_id, position, item_id, source_table, source_id, source_subkey,
                content_hash, provenance_json, score, score_breakdown_json)
               VALUES (?, 0, ?, 'voice_transcripts', ?, 'transcript', ?, ?, ?, ?)""",
            (run_id, candidate["item_id"], candidate["id"], candidate["content_hash"],
             _serialize_json(provenance), score, _serialize_json(breakdown)),
        )
        conn.execute(
            """INSERT INTO resurfacing_events
               (run_id, item_id, channel, event, metadata_json, created_at)
               VALUES (?, ?, 'web', 'selected', '{}', ?)""",
            (run_id, candidate["item_id"], now_ms),
        )
    conn.commit()
    if actual_run_id != run_id:
        concurrent = _existing_run(conn, run_key)
        if concurrent:
            return concurrent
    item_row = _load_run_item_context(conn, actual_run_id)
    context = _get_selection_context(conn, actual_run_id, str(item_row["item_id"])) if item_row else None
    return {"run_id": actual_run_id, "item": context}


def _safe_metadata(metadata: dict | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if key in _SAFE_METADATA_NUMBERS and isinstance(value, (int, float)) and math.isfinite(float(value)):
            result[key] = value
        elif (key in _SAFE_METADATA_TOKENS and isinstance(value, str)
              and re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value)):
            result[key] = value
    return result


def record_resurfacing_event(conn, run_id, item_id, channel, event, metadata=None) -> int:
    """Record a typed action without accepting free-form private text."""
    if channel not in _CHANNELS:
        raise ValueError(f"unsupported channel: {channel}")
    if event not in _EVENTS:
        raise ValueError(f"unsupported resurfacing event: {event}")
    capture_lifecycle = (
        event in {"record_started", "record_completed"}
        and run_id is None
        and isinstance(item_id, str)
        and re.fullmatch(r"cpc_[A-Za-z0-9_.:-]{1,100}", item_id) is not None
    )
    if not capture_lifecycle:
        exists = conn.execute(
            "SELECT 1 FROM resurfacing_run_items WHERE run_id = ? AND item_id = ?",
            (run_id, item_id),
        ).fetchone()
        if not exists:
            raise ValueError("item is not part of run")
    cursor = conn.execute(
        """INSERT INTO resurfacing_events
           (run_id, item_id, channel, event, metadata_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (run_id, item_id, channel, event, _serialize_json(_safe_metadata(metadata)),
         int(time.time() * 1000)),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _raw_chunks(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT tc.id AS chunk_id, tc.chunk_text, tc.embedding, tc.transcript_id
           FROM transcript_chunks tc
           WHERE tc.chunk_type = 'raw_speech' AND tc.embedding IS NOT NULL
           ORDER BY tc.id LIMIT 5000"""
    ).fetchall()
    return [_row_dict(row) for row in rows]


def _surrounding_exact_excerpt(full: str, chunk: str) -> str:
    index = full.find(chunk)
    if index < 0:
        return ""
    return full[max(0, index - 120):min(len(full), index + len(chunk) + 120)]


def find_resurface(query_text: str, conn,
                   min_age_days: int = DEFAULT_MIN_AGE_DAYS,
                   sim_threshold: float = DEFAULT_SIM_THRESHOLD,
                   max_results: int = 5,
                   exclude_transcript_ids: list[str] | None = None) -> dict:
    """Find exact authored raw-speech excerpts that match a query."""
    import numpy as np

    query = (query_text or "").strip()
    if len(query) < 8:
        return {"echoes": [], "query_excerpt": query[:200], "meta": {"error": "query too short"}}
    qvec = _embed_query(query)
    if qvec is None:
        return {"echoes": [], "query_excerpt": query[:200], "meta": {"error": "embedding unavailable"}}
    qvec = np.asarray(qvec, dtype=np.float32)
    qnorm = float(np.linalg.norm(qvec)) + 1e-9

    now_ms = int(time.time() * 1000)
    age_days = max(0, min(int(min_age_days), 36_500))
    cutoff_ms = now_ms - age_days * 86_400_000 if age_days else now_ms + 1
    rows = _load_voice_rows(conn, cutoff_ms)
    groups = _dedupe_voice_rows(rows, conn)
    alias_to_group: dict[str, dict[str, Any]] = {}
    for group in groups:
        for alias in group.get("aliases", []):
            alias_to_group[str(alias)] = group
    excluded = set(exclude_transcript_ids or [])
    source_rows = {str(row["id"]): row for row in rows}
    scored: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    valid_candidates = 0
    for chunk in _raw_chunks(conn):
        transcript_id = str(chunk["transcript_id"])
        group = alias_to_group.get(transcript_id)
        source = source_rows.get(transcript_id)
        if not group or not source or excluded.intersection(group.get("aliases", [])):
            continue
        full = str(source.get("transcript") or "")
        authored = str(chunk.get("chunk_text") or "")
        if not authored or full.find(authored) < 0:
            continue
        valid_candidates += 1
        try:
            cvec = np.frombuffer(chunk["embedding"], dtype=np.float32)
            if cvec.shape != qvec.shape:
                continue
            similarity = float(np.dot(qvec, cvec) / (qnorm * (float(np.linalg.norm(cvec)) + 1e-9)))
        except Exception:
            continue
        if similarity >= float(sim_threshold):
            scored.append((similarity, group, source, chunk))

    scored.sort(key=lambda entry: (-entry[0], str(entry[1]["item_id"]), str(entry[3]["chunk_id"])))
    seen_items: set[str] = set()
    echoes: list[dict[str, Any]] = []
    for similarity, group, source, chunk in scored:
        item_id = str(group["item_id"])
        if item_id in seen_items:
            continue
        seen_items.add(item_id)
        transcript_date = int(source.get("created_at") or 0)
        authored = str(chunk["chunk_text"])
        echoes.append({
            "chunk_id": chunk["chunk_id"],
            "chunk_text": authored,
            "chunk_type": "raw_speech",
            "similarity": round(similarity, 3),
            "item_id": item_id,
            "transcript_id": group["id"],
            "transcript_source": source.get("source") or "",
            "transcript_date": transcript_date,
            "days_ago": max(1, (now_ms - transcript_date) // 86_400_000),
            "transcript_node_title": source.get("node_title") or "",
            "transcript_excerpt": _surrounding_exact_excerpt(str(source["transcript"]), authored),
        })
        if len(echoes) >= max(1, min(int(max_results), 10)):
            break
    return {
        "echoes": echoes,
        "query_excerpt": query[:300],
        "meta": {
            "threshold": float(sim_threshold),
            "min_age_days": age_days,
            "candidates_scanned": valid_candidates,
            "matches_above_threshold": len(scored),
            "authored_only": True,
        },
    }


def log_event(query_text: str, echoes: list[dict], conn,
              query_source: str = "manual", audio_bytes: int = 0) -> str:
    """Log legacy commonplace pull without persisting its private query."""
    event_id = f"cp_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    source = query_source if re.fullmatch(r"[A-Za-z0-9_.:-]{1,40}", query_source or "") else "manual"
    conn.execute(
        """INSERT INTO commonplace_events
           (id, query_text, query_source, audio_bytes, echo_chunk_ids,
            echo_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event_id, hash_resurfacing_context(query_text or "", conn), source,
         max(0, int(audio_bytes or 0)),
         _serialize_json([str(echo.get("chunk_id") or "") for echo in echoes]),
         len(echoes), int(time.time() * 1000)),
    )
    conn.commit()
    return event_id


def list_recent_events(conn, limit: int = 30) -> list[dict]:
    """Return legacy event metadata; query_text contains only a hash marker."""
    rows = conn.execute(
        """SELECT id, query_text, query_source, echo_count, created_at
           FROM commonplace_events ORDER BY created_at DESC LIMIT ?""",
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]
