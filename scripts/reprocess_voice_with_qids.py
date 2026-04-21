#!/usr/bin/env python3
"""Scaffold for PR 4: resolve a voice transcript's entities to Wikidata QIDs.

This is the scaffolding for wiring the Wikidata resolver into
`process_voice_capture()`. For safety during the overnight autonomous
run, it's a STANDALONE script — it does NOT modify the live voice-capture
pipeline. Instead, it:

  1. Loads a voice transcript (by id, from petrarca.db).
  2. Extracts entity mentions via Gemini Flash (names + type hints + dates).
  3. Resolves each mention through the limbic Wikidata resolver, using
     dependency-order two-pass resolution so later mentions can anchor
     against earlier confident QIDs.
  4. Applies LLM disambiguation for ambiguous cases (same pattern as
     `scripts/backfill_wikidata.py`).
  5. Prints a coverage report: which mentions resolved to which QID,
     which fell through, which were hallucinations rejected by the guard.
  6. Optionally writes an entity_resolutions audit row per mention tagged
     with capture_id=<transcript_id> (use --write).

Usage:
    # Dry-run on the Rollo/Normandy canonical test case:
    python3 scripts/reprocess_voice_with_qids.py vt_1776097010_8381

    # With DB writes (audit trail only — never modifies shared_entities):
    python3 scripts/reprocess_voice_with_qids.py vt_1776097010_8381 --write

This smoke-tests the full resolver pipeline against the transcript that
triggered the entire Wikidata resolution project. Expected picks (from
the corrected-QID table in memory/project_hallucinated_qids_incident.md):

  Rollo             → Q273773
  Richard I         → Q333359  (Richard I of Normandy)
  Gunnor            → Q270777
  Æthelred          → Q183499  (Æthelred the Unready)
  Emma              → Q40061   (Emma of Normandy)
  Normandy          → Q18677   (Duchy of Normandy — or Q11046)
  Paris             → Q90
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from limbic.amygdala.embed import EmbeddingModel
from limbic.amygdala.temporal import DateRange
from limbic.amygdala.wikidata import WikidataClient
from limbic.hippocampus.wikidata_resolve import WikidataResolver, validate_chosen_qid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reprocess_voice")


USER_AGENT = "Petrarca/0.1 (mailto:stian@haklev.com)"


EXTRACT_PROMPT = """\
Extract named entities from this voice transcript. For each entity, identify:
- The exact mention text as it appears
- The entity type (person, place, event, work, concept, other)
- Approximate date range (if clear from context — use null if not)

Transcript:
{transcript}

Return ONLY a JSON object:
{{
  "mentions": [
    {{"mention": "...", "type": "person|place|event|work|concept|other",
      "date_start": year or null, "date_end": year or null}},
    ...
  ]
}}

Rules:
- Return the SPECIFIC named entity, not the generic type ("Æthelred" not "king").
- Skip purely generic terms ("the king", "the chronicler") — only real named
  entities with a proper noun (or a regnal number).
- Dates are historical years (negative for BCE). Use null if the context
  is vague — "medieval period" should not get specific dates.
- Deduplicate: if the transcript mentions "Rollo" and "Rollo the Viking",
  return just one entry with the more specific mention.
- Keep the list under 25 entries.
"""


DISAMBIG_PROMPT = """\
You are disambiguating an entity mention to the correct Wikidata entity.

MENTION: {mention}
TYPE: {type_hint}
DATE HINT: {date_hint}
CONTEXT (from the transcript):
{context}

CANDIDATES:
{candidates}

Pick the QID that best matches in context. If none fit, return null.
Never invent a QID not in the list.

Return JSON: {{"chosen_qid": "Q123" or null, "confidence": 0.0-1.0, "reasoning": "brief"}}
"""


def extract_mentions(transcript: str) -> list[dict]:
    """LLM-based mention extraction. Returns list of {mention, type, date_start, date_end}."""
    sys.path.insert(0, str(Path(__file__).parent))
    from claude_llm import call_claude_json

    data = call_claude_json(
        EXTRACT_PROMPT.format(transcript=transcript[:4000]),
        timeout=120, model='sonnet',
    )
    if not isinstance(data, dict):
        log.error("LLM extraction returned empty or wrong shape")
        return []
    mentions = data.get("mentions") or []
    # Normalize.
    clean = []
    seen = set()
    for m in mentions:
        name = (m.get("mention") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        clean.append({
            "mention": name,
            "type_hint": m.get("type"),
            "date_start": m.get("date_start"),
            "date_end": m.get("date_end"),
        })
    return clean


def date_hint_from(m: dict) -> DateRange | None:
    """Build a DateRange (mirror the missing bound)."""
    s = m.get("date_start")
    e = m.get("date_end")
    if s is None and e is None:
        return None
    if s is None:
        s = e
    if e is None:
        e = s
    return DateRange(start=min(s, e), end=max(s, e))


def run(transcript_id: str, db_path: Path, *, write: bool) -> None:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")

    row = conn.execute(
        "SELECT id, transcript FROM voice_transcripts WHERE id = ?",
        (transcript_id,),
    ).fetchone()
    if not row:
        log.error("transcript %s not found", transcript_id)
        sys.exit(2)
    transcript = row["transcript"]
    log.info("transcript %s (%d chars)", transcript_id, len(transcript))

    # Step 1: extract mentions via LLM.
    log.info("extracting entity mentions...")
    mentions = extract_mentions(transcript)
    log.info("  %d distinct mentions", len(mentions))
    for m in mentions:
        d = ""
        if m["date_start"] is not None or m["date_end"] is not None:
            d = f" [dates: {m['date_start']}..{m['date_end']}]"
        log.info("    %-30s type=%-8s%s", m["mention"], m["type_hint"] or "?", d)

    # Step 2: resolve each via limbic. Two-pass ordering — confident picks
    # become anchors for later ambiguous ones.
    client = WikidataClient(user_agent=USER_AGENT)
    embedder = EmbeddingModel()  # MiniLM default
    resolver = WikidataResolver(client=client, embedder=embedder)

    anchors: dict[str, str] = {}  # mention → QID for coherence scoring
    resolutions: list[tuple[dict, object]] = []

    log.info("pass 1 — deterministic resolution...")
    for m in mentions:
        try:
            res = resolver.resolve(
                m["mention"],
                context_text=transcript[:800],  # give the transcript as context
                type_hint=m["type_hint"],
                date_hint=date_hint_from(m),
                already_resolved=anchors,
            )
        except Exception as e:
            log.exception("resolve failed for %r", m["mention"])
            resolutions.append((m, None))
            continue
        if res.status == "resolved":
            anchors[m["mention"]] = res.chosen_qid
        resolutions.append((m, res))

    # Step 3: LLM disambiguation for ambiguous cases.
    log.info("pass 2 — LLM disambiguation...")
    sys.path.insert(0, str(Path(__file__).parent))
    from claude_llm import call_claude_json

    for i, (m, res) in enumerate(resolutions):
        if res is None or res.status != "ambiguous":
            continue
        candidates = res.candidates[:5]
        cand_block = "\n".join(
            f"{j+1}. {c.qid}: {c.label} — {(c.description or '(no desc)')[:200]} "
            f"[score {c.total:.2f}]"
            for j, c in enumerate(candidates)
        )
        prompt = DISAMBIG_PROMPT.format(
            mention=m["mention"],
            type_hint=m["type_hint"] or "(unknown)",
            date_hint=f"{m['date_start']}..{m['date_end']}"
            if (m["date_start"] or m["date_end"]) else "(none)",
            context=transcript[:500],
            candidates=cand_block,
        )
        answer = call_claude_json(prompt, timeout=60, model='sonnet')
        if not isinstance(answer, dict):
            continue
        chosen = answer.get("chosen_qid")
        if chosen is None:
            continue
        if not validate_chosen_qid(candidates, chosen):
            log.warning("  %r: HALLUCINATION — LLM proposed %s not in candidates",
                        m["mention"], chosen)
            continue
        # Success — rewrite the resolution summary for reporting.
        chosen_cand = next(c for c in candidates if c.qid == chosen)
        res.status = "resolved"
        res.chosen_qid = chosen
        res.confidence = float(answer.get("confidence") or 0.7)
        res.reasoning = f"LLM disambiguation: {answer.get('reasoning') or ''}"
        anchors[m["mention"]] = chosen

    # Step 4: report.
    log.info("=" * 60)
    log.info("RESOLUTION REPORT")
    log.info("=" * 60)
    resolved = 0
    ambiguous = 0
    no_match = 0
    for m, res in resolutions:
        if res is None:
            log.info("  %-30s ERROR", m["mention"])
            continue
        if res.status == "resolved":
            label = ""
            if res.candidates:
                chosen = next(
                    (c for c in res.candidates if c.qid == res.chosen_qid), None
                )
                if chosen:
                    label = f" ({chosen.label})"
            log.info("  %-30s → %-10s%s conf=%.2f",
                     m["mention"], res.chosen_qid or "?", label, res.confidence)
            resolved += 1
        elif res.status == "ambiguous":
            top = res.candidates[0] if res.candidates else None
            log.info("  %-30s AMBIGUOUS (top=%s %s, conf=%.2f)",
                     m["mention"],
                     top.qid if top else "-",
                     top.label[:30] if top else "",
                     res.confidence)
            ambiguous += 1
        else:
            log.info("  %-30s %s", m["mention"], res.status.upper())
            no_match += 1

    total = len(resolutions)
    log.info("-" * 60)
    log.info("summary: %d resolved, %d ambiguous, %d no_match (of %d)",
             resolved, ambiguous, no_match, total)

    # Step 5: optionally write audit rows.
    if write:
        log.info("writing %d audit rows with capture_id=%s", total, transcript_id)
        for m, res in resolutions:
            if res is None:
                continue
            rid = f"er_{uuid.uuid4().hex[:12]}"
            cand_payload = [
                {"qid": c.qid, "label": c.label, "description": c.description,
                 "total": c.total, "scores": c.scores, "rank": c.rank}
                for c in (res.candidates or [])[:10]
            ]
            conn.execute(
                """
                INSERT INTO entity_resolutions (
                    id, entity_id, capture_id, mention_text, context_excerpt,
                    type_hint, date_hint_start, date_hint_end, candidate_qids,
                    chosen_qid, confidence, status, resolver_model, reasoning,
                    cost_usd, created_at
                ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid, transcript_id, res.mention,
                    res.context_text[:500] if res.context_text else "",
                    res.type_hint,
                    res.date_hint.start if res.date_hint else None,
                    res.date_hint.end if res.date_hint else None,
                    json.dumps(cand_payload),
                    res.chosen_qid, res.confidence, res.status,
                    "voice-scaffold+gemini", res.reasoning, 0.0,
                    int(time.time()),
                ),
            )
        conn.commit()
        log.info("wrote %d rows", total)

    conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("transcript_id", help="voice_transcripts.id (e.g., vt_1776097010_8381)")
    p.add_argument("--db", type=Path, default=Path("/opt/petrarca/data/petrarca.db"))
    p.add_argument("--write", action="store_true",
                   help="Write entity_resolutions audit rows (does NOT modify shared_entities)")
    args = p.parse_args()

    if not args.db.exists():
        log.error("DB not found: %s", args.db)
        sys.exit(2)

    run(args.transcript_id, args.db, write=args.write)


if __name__ == "__main__":
    main()
