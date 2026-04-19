"""Build a per-transcript calibration payload that traces voice captures
through the full question-generation pipeline.

For each recent voice_capture / entity_capture:
  transcript text
  → facts extracted by the LLM (with source_excerpt + node_ids + confidence)
  → for each touched curriculum node: the knowledge_item's main question,
    rich_answer, memory_hook, quiz_suggestions and every microlearning_quizzes
    row grouped by fact_id (so each "angle asked" is visible)
  → for each touched knowledge_entity: same but entity-keyed
  → wonderings, knowledge_updates, unrouted facts

The HTML page at /voice/calibration renders this as a transcript with
inline colored span overlays per fact and side-panel cards per node.

No fact-to-character-span is stored anywhere in the DB, so spans are
reconstructed by substring-matching source_excerpt in the transcript.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

CALIBRATION_SOURCES = ("voice_capture", "entity_capture")


def _safe_json(text: str | None, default: Any):
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def _find_span(transcript: str, excerpt: str) -> tuple[int, int] | None:
    """Best-effort substring match. Try full excerpt, then progressively
    shorter prefixes until we find a hit. Return (start, end) or None."""
    if not excerpt or not transcript:
        return None
    # Normalize whitespace on both sides for fuzzy matching
    tnorm = " ".join(transcript.split())
    enorm = " ".join(excerpt.split())

    # Full first
    hit = tnorm.find(enorm)
    if hit >= 0:
        return _remap_span(transcript, tnorm, hit, len(enorm))

    # Try anchor prefixes of decreasing length
    for anchor_len in (120, 80, 60, 40, 30):
        if len(enorm) <= anchor_len:
            continue
        hit = tnorm.find(enorm[:anchor_len])
        if hit >= 0:
            return _remap_span(transcript, tnorm, hit, len(enorm))
    # Try shortest viable anchor
    anchor = enorm[:40] if len(enorm) >= 40 else enorm
    hit = tnorm.find(anchor)
    if hit >= 0:
        return _remap_span(transcript, tnorm, hit, len(anchor))
    return None


def _remap_span(original: str, normalized: str, nstart: int, length: int) -> tuple[int, int] | None:
    """Map a (start, length) hit in the normalized string back to the
    original transcript by counting non-whitespace collapse offsets."""
    # Walk original counting characters that appear in normalized
    osrc = 0
    ndst = 0
    start_orig = None
    end_orig = None
    prev_ws = False
    while osrc < len(original) and ndst < nstart + length:
        ch = original[osrc]
        if ch.isspace():
            if not prev_ws and ndst > 0:
                ndst += 1  # single space in normalized
            prev_ws = True
        else:
            if ndst == nstart and start_orig is None:
                start_orig = osrc
            ndst += 1
            prev_ws = False
        if ndst == nstart + length and end_orig is None:
            end_orig = osrc + 1
        osrc += 1
    if start_orig is None:
        return None
    if end_orig is None:
        end_orig = osrc
    return (start_orig, end_orig)


def _load_node_titles(conn: sqlite3.Connection, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """For (domain_id, node_id) pairs, return titles by joining curriculum_nodes."""
    if not pairs:
        return {}
    out: dict[tuple[str, str], str] = {}
    cur = conn.cursor()
    # curriculum_nodes columns vary; read first row for schema introspection
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(curriculum_nodes)").fetchall()}
    has_domain = "domain_id" in cols
    for dom, nid in pairs:
        if has_domain:
            r = cur.execute(
                "SELECT title FROM curriculum_nodes WHERE domain_id=? AND id=? LIMIT 1",
                (dom, nid),
            ).fetchone()
        else:
            r = cur.execute(
                "SELECT title FROM curriculum_nodes WHERE id=? LIMIT 1", (nid,)
            ).fetchone()
        if r:
            out[(dom, nid)] = r["title"] if isinstance(r, sqlite3.Row) else r[0]
    return out


def _quiz_rows_for_fact_ids(conn: sqlite3.Connection, fact_ids: list[str]) -> dict[str, list[dict]]:
    if not fact_ids:
        return {}
    out: dict[str, list[dict]] = {fid: [] for fid in fact_ids}
    qmarks = ",".join(["?"] * len(fact_ids))
    cur = conn.execute(
        f"""SELECT id, fact_id, quiz_type, status, question, answer,
                   review_count, last_score, stability_days, due_at
            FROM microlearning_quizzes
            WHERE fact_id IN ({qmarks})
            ORDER BY fact_id, quiz_type, id""",
        fact_ids,
    )
    for r in cur:
        out.setdefault(r["fact_id"], []).append({
            "id": r["id"],
            "quiz_type": r["quiz_type"] or "",
            "status": r["status"] or "active",
            "question": r["question"] or "",
            "answer": (r["answer"] or "")[:260],
            "review_count": r["review_count"] or 0,
            "last_score": r["last_score"] or None,
            "stability_days": r["stability_days"] or 0.0,
            "due_at": r["due_at"] or 0,
        })
    return out


def _ki_row_to_summary(row: sqlite3.Row) -> dict:
    cq = _safe_json(row["cached_question"], {})
    sources = _safe_json(row["sources"], [])
    voice_sources = [s for s in sources if isinstance(s, dict) and s.get("source") == "voice_capture"]
    book_sources = [s for s in sources if isinstance(s, dict) and s.get("book_id")]
    qsug = cq.get("quiz_suggestions") or []
    # normalize quiz suggestions shape
    norm_sug = []
    for q in qsug:
        if not isinstance(q, dict):
            continue
        norm_sug.append({
            "fact_id": q.get("fact_id", ""),
            "question": q.get("question", ""),
            "answer": (q.get("answer", "") or "")[:200],
            "type": q.get("type", ""),
        })
    return {
        "id": row["id"],
        "review_count": row["review_count"] or 0,
        "last_score": row["last_score"] or None,
        "stability_days": row["stability_days"] or 0.0,
        "due_at": row["due_at"] or 0,
        "main_question": cq.get("question", ""),
        "answer_guidance": (cq.get("answer_guidance", "") or "")[:400],
        "rich_answer": (cq.get("rich_answer", "") or "")[:900],
        "memory_hook": cq.get("memory_hook", "") or "",
        "answer_type": cq.get("answer_type", ""),
        "main_fact_id": cq.get("fact_id", ""),
        "entities": cq.get("entities", []) or [],
        "temporal_hook": cq.get("temporal_hook", "") or "",
        "follow_up_queries": cq.get("follow_up_queries", []) or [],
        "quiz_suggestions": norm_sug,
        "sources": {
            "book_count": len(book_sources),
            "voice_count": len(voice_sources),
            "book_snippets": [
                {
                    "chapter": s.get("chapter_title", ""),
                    "book_id": s.get("book_id"),
                    "text": (s.get("source_text", "") or "")[:260],
                }
                for s in book_sources[:4]
            ],
            "voice_snippets": [
                {
                    "entity": s.get("entity_name", ""),
                    "text": (s.get("source_text", "") or "")[:260],
                    "fact_count": s.get("fact_count", 0),
                }
                for s in voice_sources[:4]
            ],
        },
    }


def _entity_row_to_summary(row: sqlite3.Row) -> dict:
    cq = _safe_json(row["cached_question"], {})
    kf = _safe_json(row["key_facts"], [])
    sources = _safe_json(row["sources"], [])
    return {
        "id": row["id"],
        "entity_id": row["entity_id"],
        "entity_name": row["entity_name"],
        "entity_type": row["entity_type"] or "",
        "wikidata_qid": row["wikidata_qid"] or "",
        "review_count": row["review_count"] or 0,
        "last_score": row["last_score"] or None,
        "stability_days": row["stability_days"] or 0.0,
        "due_at": row["due_at"] or 0,
        "main_question": cq.get("question", ""),
        "rich_answer": (cq.get("rich_answer", "") or "")[:900],
        "memory_hook": cq.get("memory_hook", "") or "",
        "main_fact_id": cq.get("fact_id", ""),
        "follow_up_queries": cq.get("follow_up_queries", []) or [],
        "quiz_suggestions": cq.get("quiz_suggestions", []) or [],
        "key_facts": [
            {
                "id": f.get("id", ""),
                "question": f.get("question", ""),
                "answer": (f.get("answer", "") or "")[:200],
                "type": f.get("type", ""),
                "source_excerpt": (f.get("source_excerpt", "") or "")[:260],
            }
            for f in kf[:30]
            if isinstance(f, dict)
        ],
        "sources_count": len([s for s in sources if isinstance(s, dict)]),
    }


def get_voice_calibration_data(conn: sqlite3.Connection, limit: int = 5) -> dict:
    """Return the calibration payload for the last N voice_capture/entity_capture transcripts."""
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(CALIBRATION_SOURCES))
    transcripts = conn.execute(
        f"""SELECT id, source, node_id, domain_id, node_title, transcript, llm_result, created_at
            FROM voice_transcripts
            WHERE source IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ?""",
        (*CALIBRATION_SOURCES, limit),
    ).fetchall()

    result_transcripts: list[dict] = []

    for vt in transcripts:
        llm = _safe_json(vt["llm_result"], {})
        transcript_text = vt["transcript"] or ""
        raw_facts = llm.get("facts", []) or []
        conf_tagged = llm.get("confidence_tagged", []) or []
        # build fact→confidence map by textual similarity (substring match of fact text)
        conf_by_text: dict[str, str] = {}
        for c in conf_tagged:
            if not isinstance(c, dict):
                continue
            conf_by_text[c.get("fact", "").strip().lower()[:60]] = c.get("confidence", "")

        # materialize facts with spans
        facts: list[dict] = []
        # per-node fact→indices map so each node card can show which facts fed it
        node_to_fact_idxs: dict[tuple[str, str] | str, list[int]] = {}
        entity_to_fact_idxs: dict[str, list[int]] = {}
        for i, f in enumerate(raw_facts):
            if not isinstance(f, dict):
                continue
            fact_text = f.get("fact", "") or ""
            excerpt = f.get("source_excerpt", "") or ""
            span = _find_span(transcript_text, excerpt) if excerpt else None
            node_ids = f.get("node_ids") or []
            entities = f.get("entities") or f.get("entity_names") or []
            # confidence lookup
            ft_key = fact_text.strip().lower()[:60]
            confidence = conf_by_text.get(ft_key, "")
            if not confidence:
                # loose substring match
                for k, v in conf_by_text.items():
                    if k and k[:30] in ft_key:
                        confidence = v
                        break
            facts.append({
                "idx": i,
                "text": fact_text,
                "source_excerpt": excerpt,
                "span": list(span) if span else None,
                "node_ids": node_ids,
                "entities": entities,
                "confidence": confidence or None,
            })
            for nid in node_ids:
                key = nid  # we don't always know domain at fact level
                node_to_fact_idxs.setdefault(key, []).append(i)
            for ent in entities:
                entity_to_fact_idxs.setdefault(ent, []).append(i)

        # knowledge_updates gives us (node_id, domain_id) pairs for the KI lookup
        kupdates = llm.get("knowledge_updates", []) or []
        assessments = llm.get("node_assessments", []) or []
        # index assessments by node_id
        assess_by_nid = {a.get("node_id"): a for a in assessments if isinstance(a, dict) and a.get("node_id")}

        touched_nodes: list[dict] = []

        # Prefer knowledge_updates for (domain, node) pairs (authoritative)
        pairs_ordered: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for u in kupdates:
            if isinstance(u, dict) and u.get("node_id"):
                key = (u.get("domain_id") or vt["domain_id"] or "", u["node_id"])
                if key not in seen:
                    seen.add(key)
                    pairs_ordered.append(key)
        # Add assessed nodes not in updates
        for nid in assess_by_nid.keys():
            if not any(p[1] == nid for p in pairs_ordered):
                key = (vt["domain_id"] or "", nid)
                if key not in seen:
                    seen.add(key)
                    pairs_ordered.append(key)

        node_titles = _load_node_titles(conn, set(pairs_ordered))

        # fetch all KIs
        ki_by_nid: dict[str, sqlite3.Row] = {}
        for dom, nid in pairs_ordered:
            r = conn.execute(
                """SELECT id, curriculum_node_id, curriculum_domain, review_count, last_score,
                          stability_days, due_at, sources, cached_question
                   FROM knowledge_items
                   WHERE curriculum_domain=? AND curriculum_node_id=?""",
                (dom, nid),
            ).fetchone()
            if r:
                ki_by_nid[nid] = r

        # assemble touched_nodes entries
        for idx, (dom, nid) in enumerate(pairs_ordered):
            assessment = assess_by_nid.get(nid, {})
            upd = next((u for u in kupdates if isinstance(u, dict) and u.get("node_id") == nid), {})
            ki_row = ki_by_nid.get(nid)
            ki_summary = _ki_row_to_summary(ki_row) if ki_row else None
            # collect fact_ids from KI and trace to quizzes
            if ki_summary:
                fact_ids = [q["fact_id"] for q in ki_summary["quiz_suggestions"] if q.get("fact_id")]
                if ki_summary.get("main_fact_id"):
                    fact_ids.append(ki_summary["main_fact_id"])
                quiz_rows_map = _quiz_rows_for_fact_ids(conn, list(set(fact_ids)))
                for q in ki_summary["quiz_suggestions"]:
                    q["quiz_rows"] = quiz_rows_map.get(q.get("fact_id", ""), [])
                ki_summary["main_quiz_rows"] = quiz_rows_map.get(ki_summary.get("main_fact_id", ""), []) if ki_summary.get("main_fact_id") else []
            # Which transcript-facts fed this node?
            feeding_facts = node_to_fact_idxs.get(nid, [])
            touched_nodes.append({
                "node_id": nid,
                "domain_id": dom,
                "node_title": node_titles.get((dom, nid)) or (assessment.get("node_title") if isinstance(assessment, dict) else None) or upd.get("node_title") or nid,
                "assessed_level": assessment.get("knowledge_level") if isinstance(assessment, dict) else None,
                "assessed_summary": assessment.get("summary", "") if isinstance(assessment, dict) else "",
                "facts_captured": upd.get("facts_captured", 0) if isinstance(upd, dict) else 0,
                "feeding_fact_indices": feeding_facts,
                "exists_in_ki": ki_row is not None,
                "ki": ki_summary,
                "color_index": idx,
            })

        # knowledge_entities touched (via capture_id in sources OR via this transcript id)
        touched_entities: list[dict] = []
        kes = conn.execute(
            """SELECT id, entity_id, entity_name, entity_type, wikidata_qid,
                      review_count, last_score, stability_days, due_at,
                      sources, key_facts, cached_question
               FROM knowledge_entities
               WHERE sources LIKE ?""",
            (f"%{vt['id']}%",),
        ).fetchall()
        # also find entities by entity_name matching entities_mentioned (for entity_capture route)
        mentioned = llm.get("entities_mentioned", []) or []
        if mentioned:
            qmarks = ",".join(["?"] * len(mentioned))
            more = conn.execute(
                f"""SELECT id, entity_id, entity_name, entity_type, wikidata_qid,
                           review_count, last_score, stability_days, due_at,
                           sources, key_facts, cached_question
                    FROM knowledge_entities WHERE entity_name IN ({qmarks})""",
                mentioned,
            ).fetchall()
            by_id = {r["id"]: r for r in kes}
            for r in more:
                if r["id"] not in by_id:
                    kes.append(r)
                    by_id[r["id"]] = r
        for r in kes:
            es = _entity_row_to_summary(r)
            # link each key_fact to its quizzes
            fact_ids = [f["id"] for f in es["key_facts"] if f.get("id")]
            if es.get("main_fact_id"):
                fact_ids.append(es["main_fact_id"])
            qmap = _quiz_rows_for_fact_ids(conn, list(set(fact_ids)))
            for f in es["key_facts"]:
                f["quiz_rows"] = qmap.get(f.get("id", ""), [])
            es["main_quiz_rows"] = qmap.get(es.get("main_fact_id", ""), []) if es.get("main_fact_id") else []
            # which transcript facts feed this entity? (by entity_name substring match)
            feeding = [f["idx"] for f in facts if es["entity_name"].lower() in (f["text"] + " " + f["source_excerpt"]).lower()]
            es["feeding_fact_indices"] = feeding
            es["touched_via_capture_id"] = f"\"capture_id\": \"{vt['id']}\"" in (r["sources"] or "")
            touched_entities.append(es)

        # unrouted facts = those whose node_ids is empty AND entities is empty
        unrouted = [f["idx"] for f in facts if not f["node_ids"] and not f["entities"]]

        result_transcripts.append({
            "id": vt["id"],
            "source": vt["source"],
            "created_at": vt["created_at"],
            "routed_node_id": vt["node_id"],
            "routed_domain_id": vt["domain_id"],
            "routed_node_title": vt["node_title"],
            "transcript": transcript_text,
            "transcript_length": len(transcript_text),
            "llm_summary": llm.get("overall_summary", "") or "",
            "facts": facts,
            "node_assessments": assessments,
            "knowledge_updates": kupdates,
            "wonderings": llm.get("wonderings", []) or [],
            "entities_mentioned": mentioned,
            "confidence_tagged": conf_tagged,
            "touched_nodes": touched_nodes,
            "touched_entities": touched_entities,
            "unrouted_fact_indices": unrouted,
        })

    return {
        "generated_at": int(time.time() * 1000),
        "transcript_count": len(result_transcripts),
        "transcripts": result_transcripts,
    }
