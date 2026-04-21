#!/usr/bin/env python3
"""Backfill Wikidata QIDs for existing shared_entities.

Two-pass resolver run per the PR 3 plan:

    Pass 1 — independent resolution, no anchors. Writes entity_resolutions,
             sets shared_entities.wikidata_qid on confident matches, flags
             ambiguous/no_match as 'needs_review' in the batch state.

    Pass 2 — re-run over needs_review items with pass-1 confident QIDs as
             coherence anchors. The resolver uses `already_resolved` to boost
             candidates connected (P22/P25/P26/P40/…) to resolved entities.

Resumable. Runs BatchProcessor with a SQLite state store. Ctrl-C is safe;
re-invoking picks up where it left off.

Usage:
    python3 scripts/backfill_wikidata.py [DB_PATH] [--max-cost 20.0]
                                         [--limit N] [--pass {1,2,both}]
                                         [--state STATE_DB]
                                         [--dry-run]
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
from typing import Any

# Make limbic importable — assume ~/src/limbic on $PYTHONPATH via editable install.
from limbic.amygdala.embed import EmbeddingModel
from limbic.amygdala.temporal import DateRange
from limbic.amygdala.wikidata import WikidataClient
from limbic.cerebellum.batch import BatchProcessor, ItemResult, StateStore
from limbic.hippocampus.wikidata_resolve import Resolution, WikidataResolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill_wikidata")


# External ID Wikidata properties we capture at resolve time.
# See research/wikidata-entity-resolution-plan.md for the rationale.
EXTERNAL_ID_PROPS = (
    "P214",   # VIAF
    "P227",   # GND
    "P244",   # LCCN
    "P1566",  # GeoNames
    "P1584",  # Pleiades
    "P1667",  # Getty TGN
    "P434",   # MusicBrainz
    "P245",   # Getty ULAN
    "P268",   # BnF
)


def _now() -> int:
    return int(time.time())


def _date_range_from_entity(row: sqlite3.Row) -> DateRange | None:
    """Build a DateRange from shared_entities date_start/date_end year columns.

    DateRange requires both bounds as ints. If only one is present, mirror it
    to the other end (matches limbic resolver's own `_extract_dates` pattern).
    """
    start = row["date_start"] if "date_start" in row.keys() else None
    end = row["date_end"] if "date_end" in row.keys() else None
    if start is None and end is None:
        return None
    if start is None:
        start = end
    if end is None:
        end = start
    return DateRange(start=min(start, end), end=max(start, end))


def _context_text(row: sqlite3.Row, curriculum_titles: list[str]) -> str:
    """Concatenate everything we know about the entity as context for embedding."""
    parts: list[str] = []
    if row["description"]:
        parts.append(row["description"])
    if row["location"]:
        parts.append(f"Location: {row['location']}.")
    if row["dates"]:
        parts.append(f"Dates: {row['dates']}.")
    if curriculum_titles:
        parts.append("Appears in: " + ", ".join(curriculum_titles) + ".")
    if row["aliases"]:
        try:
            aliases = json.loads(row["aliases"])
            if aliases:
                parts.append("Also known as: " + ", ".join(aliases) + ".")
        except (json.JSONDecodeError, TypeError):
            pass
    return " ".join(parts)


def _load_entities(conn: sqlite3.Connection, limit: int | None) -> list[dict[str, Any]]:
    """Load all shared_entities lacking a wikidata_qid, with their curriculum links."""
    q = """
        SELECT e.entity_id, e.name, e.dates, e.location, e.description,
               e.entity_type, e.aliases, e.date_start, e.date_end, e.wikidata_qid
        FROM shared_entities e
        WHERE e.wikidata_qid IS NULL
        ORDER BY e.nexus_score DESC, e.entity_id
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()

    # Pre-fetch curriculum link titles per entity for context building.
    link_rows = conn.execute(
        """
        SELECT l.entity_id, l.lens_title, n.title AS node_title
        FROM entity_curriculum_links l
        LEFT JOIN curriculum_nodes n ON n.id = l.node_id AND n.domain_id = l.domain_id
        """
    ).fetchall()
    links_by_entity: dict[str, list[str]] = {}
    for r in link_rows:
        eid = r["entity_id"]
        title = r["lens_title"] or r["node_title"]
        if title:
            links_by_entity.setdefault(eid, []).append(title)

    entities: list[dict[str, Any]] = []
    for r in rows:
        titles = links_by_entity.get(r["entity_id"], [])
        entities.append(
            {
                "row": r,
                "id": r["entity_id"],
                "name": r["name"],
                "type_hint": r["entity_type"],
                "date_hint": _date_range_from_entity(r),
                "context_text": _context_text(r, titles),
                "curriculum_titles": titles,
            }
        )
    return entities


def _write_resolution(
    conn: sqlite3.Connection,
    resolution: Resolution,
    entity_id: str,
    *,
    capture_id: str,
    resolver_model: str,
) -> str:
    """Insert an entity_resolutions row. Returns the new resolution id."""
    rid = f"er_{uuid.uuid4().hex[:12]}"
    candidate_payload = [
        {
            "qid": c.qid,
            "label": c.label,
            "description": c.description,
            "total": c.total,
            "scores": c.scores,
            "rank": c.rank,
            "dates": (
                {"start": c.dates.start, "end": c.dates.end}
                if c.dates is not None
                else None
            ),
            "external_ids": c.external_ids,
            "aliases": c.aliases[:8],
        }
        for c in resolution.candidates[:10]
    ]
    # Supersede any prior un-superseded rows for this entity so the view
    # query (admin/entity-queue-data) naturally shows only the latest verdict.
    if entity_id:
        conn.execute(
            "UPDATE entity_resolutions SET superseded_by = ? "
            "WHERE entity_id = ? AND superseded_by IS NULL",
            (rid, entity_id),
        )
    conn.execute(
        """
        INSERT INTO entity_resolutions (
            id, entity_id, capture_id, mention_text, context_excerpt, type_hint,
            date_hint_start, date_hint_end, candidate_qids, chosen_qid,
            confidence, status, resolver_model, reasoning, cost_usd, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rid,
            entity_id,
            capture_id,
            resolution.mention,
            resolution.context_text[:2000],
            resolution.type_hint,
            resolution.date_hint.start if resolution.date_hint else None,
            resolution.date_hint.end if resolution.date_hint else None,
            json.dumps(candidate_payload),
            resolution.chosen_qid,
            resolution.confidence,
            resolution.status,
            resolver_model,
            resolution.reasoning,
            0.0,
            _now(),
        ),
    )
    return rid


def _commit_external_ids(
    conn: sqlite3.Connection, entity_id: str, external_ids: dict | None
) -> None:
    """external_ids: {property_id: value_or_list}. Only EXTERNAL_ID_PROPS kept."""
    if not external_ids:
        return
    for prop, value in external_ids.items():
        if prop not in EXTERNAL_ID_PROPS:
            continue
        vals = value if isinstance(value, list) else [value]
        for v in vals:
            conn.execute(
                """
                INSERT OR IGNORE INTO entity_external_ids (entity_id, property_id, value, source)
                VALUES (?, ?, ?, 'wikidata')
                """,
                (entity_id, prop, str(v)),
            )


def _apply_resolution(
    conn: sqlite3.Connection,
    entity: dict[str, Any],
    resolution: Resolution,
    *,
    capture_id: str,
    resolver_model: str,
    dry_run: bool,
) -> str:
    """Write audit row + (if resolved) set wikidata_qid + external IDs.

    Returns the batch ItemResult status: 'done' | 'needs_review'.
    """
    if dry_run:
        log.info(
            "DRY entity=%s → status=%s qid=%s confidence=%.3f",
            entity["id"], resolution.status, resolution.chosen_qid, resolution.confidence,
        )
        return "done" if resolution.status in ("resolved", "kb_hit") else "needs_review"

    # Dedup check BEFORE writing the audit row: if another entity already
    # claimed this QID, we need to record the resolver's decision honestly
    # (status='needs_review' for the UI) and not commit the QID on this row.
    dedup_owner: str | None = None
    if resolution.status in ("resolved", "kb_hit") and resolution.chosen_qid:
        existing = conn.execute(
            "SELECT entity_id FROM shared_entities "
            "WHERE wikidata_qid = ? AND entity_id != ?",
            (resolution.chosen_qid, entity["id"]),
        ).fetchone()
        if existing:
            dedup_owner = existing["entity_id"]

    if dedup_owner:
        # Rewrite resolution for the audit row to reflect deferral.
        resolution.status = "needs_review"
        resolution.reasoning = (
            f"Deterministic resolver chose {resolution.chosen_qid}; "
            f"entity '{dedup_owner}' already owns that QID. Merge candidate — "
            f"triage via review UI. Original reasoning: {resolution.reasoning}"
        )
        # Keep chosen_qid in the audit row so UI can suggest the merge.
        _write_resolution(
            conn, resolution, entity["id"],
            capture_id=capture_id, resolver_model=resolver_model,
        )
        log.warning(
            "dedup candidate: %s and %s both resolve to %s (queued for review)",
            dedup_owner, entity["id"], resolution.chosen_qid,
        )
        conn.commit()
        return "needs_review"

    _write_resolution(
        conn, resolution, entity["id"],
        capture_id=capture_id, resolver_model=resolver_model,
    )

    if resolution.status in ("resolved", "kb_hit") and resolution.chosen_qid:
        conn.execute(
            "UPDATE shared_entities SET wikidata_qid = ? WHERE entity_id = ?",
            (resolution.chosen_qid, entity["id"]),
        )
        # Fan out the chosen candidate's external IDs.
        chosen_cand = next(
            (c for c in resolution.candidates if c.qid == resolution.chosen_qid),
            None,
        )
        if chosen_cand is not None:
            _commit_external_ids(conn, entity["id"], chosen_cand.external_ids)
        conn.commit()
        return "done"

    conn.commit()
    return "needs_review"


def _build_kb_lookup(conn: sqlite3.Connection):
    """Returns a fn (mention, type_hint) -> QID that reads shared_entities.

    Used by pass 2 so that entities we resolved in pass 1 short-circuit as
    kb_hit without making another API call.
    """
    def lookup(mention: str, type_hint: str | None) -> str | None:
        row = conn.execute(
            "SELECT wikidata_qid FROM shared_entities "
            "WHERE name = ? AND wikidata_qid IS NOT NULL LIMIT 1",
            (mention,),
        ).fetchone()
        return row["wikidata_qid"] if row else None
    return lookup


def _already_resolved_map(conn: sqlite3.Connection) -> dict[str, str]:
    """Build {name: qid} for every entity already resolved — used as anchors."""
    rows = conn.execute(
        "SELECT name, wikidata_qid FROM shared_entities WHERE wikidata_qid IS NOT NULL"
    ).fetchall()
    return {r["name"]: r["wikidata_qid"] for r in rows}


USER_AGENT = "Petrarca/0.1 (mailto:stian@haklev.com)"


# ----------------------------------------------------------------------------
# LLM disambiguation pass
# ----------------------------------------------------------------------------
#
# The deterministic resolver is conservative by design — it flags `ambiguous`
# whenever the top candidate can't clear the 1.25x margin over #2 (in 110+ of
# our cases, the right answer IS the top candidate but the margin is narrow).
# For backfill, we follow up with a cheap LLM pick step: Gemini Flash picks
# from the top K candidates with the full context we have. Guarded by
# `validate_chosen_qid` so any QID hallucination is rejected.

LLM_PROMPT = """\
You are disambiguating an entity mention to the correct Wikidata entity for
a reading-companion app focused on history, classics, philosophy, literature,
music, architecture, and related humanities domains.

MENTION: {mention}
TYPE HINT: {type_hint}
DATE HINT: {date_hint}
CONTEXT:
{context}

CANDIDATES:
{candidates}

Instructions:
- Pick the QID that best matches the mention in its context.
- Pay attention to dates, domain (history/classics/music/etc.), and the
  curriculum links mentioned in the context.
- If NONE of the candidates is a clear match for the mention as it appears
  in this context, return null.
- Never invent a QID that isn't in the candidate list.

Return ONLY a JSON object:
{{"chosen_qid": "Q123" or null, "confidence": 0.0-1.0, "reasoning": "brief"}}
"""


def _format_candidate_for_llm(c: dict, idx: int) -> str:
    dates = c.get("dates") or {}
    date_str = ""
    if dates and (dates.get("start") is not None or dates.get("end") is not None):
        date_str = f" [dates: {dates.get('start', '?')}..{dates.get('end', '?')}]"
    aliases = c.get("aliases") or []
    alias_str = f" (aka {', '.join(aliases[:3])})" if aliases else ""
    return (
        f"{idx}. {c['qid']}: {c.get('label', '')}{alias_str} — "
        f"{(c.get('description') or '(no description)')[:250]}"
        f"{date_str} [score {c.get('total', 0):.2f}]"
    )


def run_llm_disambiguation(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    top_k: int = 5,
    min_confidence: float = 0.5,
) -> dict[str, int]:
    """Call Gemini Flash to disambiguate `ambiguous` resolutions.

    For each latest-ambiguous resolution: format top-K candidates + context,
    ask Flash to pick one, validate against the candidate set, commit on
    successful pick with an audit row superseding the old ambiguous row.

    Returns counts: {picked, null_answer, invalid_qid, dedup_deferred, errors}.
    """
    # Import lazily so the resolver pass doesn't depend on the Claude CLI.
    sys.path.insert(0, str(Path(__file__).parent))  # scripts/ on path
    from claude_llm import call_claude_json

    q = """
        SELECT er.id, er.entity_id, er.mention_text, er.context_excerpt,
               er.type_hint, er.date_hint_start, er.date_hint_end,
               er.candidate_qids, er.confidence AS det_confidence,
               se.description AS entity_description
        FROM entity_resolutions er
        JOIN shared_entities se ON se.entity_id = er.entity_id
        JOIN (
            SELECT entity_id, MAX(created_at) AS latest
            FROM entity_resolutions
            WHERE superseded_by IS NULL AND entity_id IS NOT NULL
            GROUP BY entity_id
        ) l ON l.entity_id = er.entity_id AND l.latest = er.created_at
        WHERE er.status = 'ambiguous'
          AND er.superseded_by IS NULL
          AND se.wikidata_qid IS NULL
        ORDER BY er.confidence DESC
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()
    log.info("llm disambiguation: %d ambiguous items to re-resolve", len(rows))

    stats = {"picked": 0, "null_answer": 0, "invalid_qid": 0,
             "dedup_deferred": 0, "low_confidence": 0, "errors": 0}

    for i, r in enumerate(rows):
        entity_id = r["entity_id"]
        mention = r["mention_text"]
        try:
            candidates = json.loads(r["candidate_qids"] or "[]")
        except json.JSONDecodeError:
            candidates = []
        if not candidates:
            stats["errors"] += 1
            continue

        top = candidates[:top_k]
        candidate_qids = {c["qid"] for c in top}
        candidate_block = "\n".join(
            _format_candidate_for_llm(c, i + 1) for i, c in enumerate(top)
        )

        context_bits = []
        if r["entity_description"]:
            context_bits.append(r["entity_description"])
        if r["context_excerpt"] and r["context_excerpt"] != r["entity_description"]:
            context_bits.append(r["context_excerpt"])
        context = "\n".join(context_bits) or "(no additional context available)"

        date_hint = "(none)"
        if r["date_hint_start"] is not None or r["date_hint_end"] is not None:
            date_hint = f"{r['date_hint_start']}..{r['date_hint_end']}"

        prompt = LLM_PROMPT.format(
            mention=mention,
            type_hint=r["type_hint"] or "(unknown)",
            date_hint=date_hint,
            context=context[:2000],
            candidates=candidate_block,
        )

        if i % 25 == 0 and i > 0:
            log.info("  llm progress: %d/%d (picked=%d null=%d invalid=%d)",
                     i, len(rows), stats["picked"], stats["null_answer"],
                     stats["invalid_qid"])

        answer = call_claude_json(prompt, timeout=60, model='sonnet')
        if not isinstance(answer, dict):
            stats["errors"] += 1
            continue

        chosen = answer.get("chosen_qid")
        llm_conf = float(answer.get("confidence") or 0.0)
        reasoning = answer.get("reasoning") or ""

        if chosen is None:
            stats["null_answer"] += 1
            continue

        # Hallucination guard — must be in candidate set.
        if chosen not in candidate_qids:
            log.warning("  %s: LLM returned QID %s not in candidate set; discarding",
                        entity_id, chosen)
            stats["invalid_qid"] += 1
            continue

        if llm_conf < min_confidence:
            stats["low_confidence"] += 1
            continue

        # Dedup guard — does another entity already own this QID?
        existing = conn.execute(
            "SELECT entity_id FROM shared_entities "
            "WHERE wikidata_qid = ? AND entity_id != ?",
            (chosen, entity_id),
        ).fetchone()
        if existing:
            log.warning(
                "  %s: LLM chose %s but %s already owns it; queuing as dedup",
                entity_id, chosen, existing["entity_id"],
            )
            stats["dedup_deferred"] += 1
            # Still write a needs_review audit row so the UI knows.
            if not dry_run:
                fake_resolution_row(
                    conn, entity_id, mention, r, chosen,
                    status="needs_review", confidence=llm_conf,
                    reasoning=(f"LLM chose {chosen}; {existing['entity_id']} "
                               f"already owns it. {reasoning}"),
                )
                conn.commit()
            continue

        # Find the winning candidate's rich data.
        chosen_cand = next(c for c in top if c["qid"] == chosen)

        if dry_run:
            log.info("  DRY %s → %s (%s) conf=%.2f", entity_id, chosen,
                     chosen_cand.get("label", ""), llm_conf)
        else:
            fake_resolution_row(
                conn, entity_id, mention, r, chosen,
                status="resolved", confidence=llm_conf, reasoning=reasoning,
            )
            conn.execute(
                "UPDATE shared_entities SET wikidata_qid = ? WHERE entity_id = ?",
                (chosen, entity_id),
            )
            # External ID fan-out from the cached candidate payload.
            ext = chosen_cand.get("external_ids") or {}
            _commit_external_ids(conn, entity_id, ext)
            conn.commit()

        stats["picked"] += 1

    log.info("llm disambiguation done: %s", stats)
    return stats


# ----------------------------------------------------------------------------
# No-match rescue via alternate search terms
# ----------------------------------------------------------------------------
#
# Wikidata's wbsearchentities is prefix-matching and often misses compound
# mentions ("Seljuk Turks", "Hyphasis River", "The First Fitna") that DO
# exist in Wikidata under a slightly different name. Ask the LLM for 2-3
# alternate search queries, then re-run the deterministic resolver on each
# candidate set. QIDs still come from the search API → no hallucination risk.

RESCUE_PROMPT = """\
You are helping rescue a Wikidata search that returned no results or only
disambiguation pages.

MENTION: {mention}
TYPE: {type_hint}
CONTEXT: {context}

Wikidata's search is prefix-based, biased toward modern names with high
sitelink counts, and sometimes misses historical figures whose canonical
Wikidata entry is labeled in a non-English script. Suggest 3-5 alternate
search queries. Examples:

- "Seljuk Turks" → ["Seljuk Empire", "Seljuk dynasty", "Seljuk"]
- "The First Fitna" → ["First Fitna", "First Muslim Civil War"]
- "Abu Bakr" (1st Rashidun caliph) → ["Abu Bakr al-Siddiq", "أبو بكر",
                                       "Hazrat Abu Bakr", "Abu Bakr caliph"]
- "Augustan Satire" → []  (this is a curriculum category, not a Wikidata entity)
- "British Palladianism" → ["Palladian architecture", "Palladianism"]

Strategies to include:
- Strip articles ("The Reconquista" → "Reconquista")
- Add disambiguating epithets for common names (kings, caliphs, etc.)
- Try the original-language form for historical figures with non-English
  canonical labels (Arabic for early Islamic figures, Greek for classical,
  etc.) — Wikidata is multilingual but search is label-sensitive
- For compound events, try the proper noun core

If the mention is a curriculum-internal label with no corresponding entity,
return an empty list.

Return JSON: {{"queries": ["...", "..."]}}
"""


def _is_disambiguation_only(candidate_qids_json: str | None) -> bool:
    """True iff every candidate is a Wikimedia disambiguation page.

    Pattern: `wbsearchentities` for "Council of Nicaea" returns only
    the disambiguation page Q232572 because the real entity's title is
    longer ("First Council of Nicaea"). These cases look like `ambiguous`
    at write-time but are functionally `no_match` — the disambig page
    has no useful P31/P569/description signal to disambiguate against.
    """
    try:
        candidates = json.loads(candidate_qids_json or "[]")
    except json.JSONDecodeError:
        return False
    if not candidates:
        return False
    return all(
        "disambiguation page" in (c.get("description") or "").lower()
        for c in candidates
    )


def run_no_match_rescue(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    top_k: int = 5,
    min_confidence: float = 0.5,
) -> dict[str, int]:
    """Retry no_match resolutions with LLM-suggested alternate queries.

    Also retries `ambiguous` cases where every candidate is a Wikimedia
    disambiguation page — the resolver has no way to score those and the
    LLM can only hallucinate. Alternate-query rescue gets to a real entity.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    from claude_llm import call_claude_json

    # Fetch latest-per-entity resolutions that are no_match OR ambiguous.
    # Then filter in Python to keep: no_match | ambiguous-with-only-disambig-candidates.
    q = """
        SELECT er.id, er.entity_id, er.mention_text, er.type_hint, er.status,
               er.context_excerpt, er.date_hint_start, er.date_hint_end,
               er.candidate_qids,
               se.description AS entity_description, se.aliases
        FROM entity_resolutions er
        JOIN shared_entities se ON se.entity_id = er.entity_id
        JOIN (
            SELECT entity_id, MAX(created_at) AS latest FROM entity_resolutions
            WHERE superseded_by IS NULL AND entity_id IS NOT NULL
            GROUP BY entity_id
        ) l ON l.entity_id = er.entity_id AND l.latest = er.created_at
        WHERE er.status IN ('no_match', 'ambiguous')
          AND se.wikidata_qid IS NULL
          AND er.superseded_by IS NULL
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    all_rows = conn.execute(q).fetchall()
    rows = [
        r for r in all_rows
        if r["status"] == "no_match"
        or _is_disambiguation_only(r["candidate_qids"])
    ]
    no_match_n = sum(1 for r in rows if r["status"] == "no_match")
    disambig_n = len(rows) - no_match_n
    log.info(
        "no-match rescue: %d items to retry (%d no_match + %d disambig-only)",
        len(rows), no_match_n, disambig_n,
    )

    client = WikidataClient(user_agent=USER_AGENT)
    resolver = WikidataResolver(client=client, embedder=None)

    stats = {"rescued": 0, "still_no_match": 0, "curriculum_label": 0,
             "ambiguous_queued": 0, "errors": 0}

    for i, r in enumerate(rows):
        entity_id = r["entity_id"]
        mention = r["mention_text"]

        prompt = RESCUE_PROMPT.format(
            mention=mention,
            type_hint=r["type_hint"] or "(unknown)",
            context=(r["entity_description"] or r["context_excerpt"] or "(none)")[:500],
        )
        data = call_claude_json(prompt, timeout=60, model='sonnet')
        if not isinstance(data, dict):
            stats["errors"] += 1
            continue
        alternates = [q for q in (data.get("queries") or []) if isinstance(q, str)]

        if not alternates:
            stats["curriculum_label"] += 1
            continue

        # Try each alternate search query and pick the best result.
        date_hint = _date_range_from_entity(r) if ("date_start" in r.keys()) else None
        best_resolution = None
        for alt in alternates[:3]:
            try:
                res = resolver.resolve(
                    alt,
                    context_text=(r["entity_description"] or "")[:500],
                    type_hint=r["type_hint"],
                    date_hint=date_hint,
                )
            except Exception:
                continue
            if res.status in ("resolved", "kb_hit"):
                best_resolution = res
                break
            if (res.status == "ambiguous" and
                    (best_resolution is None or res.confidence > best_resolution.confidence)):
                best_resolution = res

        if i % 10 == 0 and i > 0:
            log.info("  rescue progress: %d/%d (rescued=%d curriculum=%d)",
                     i, len(rows), stats["rescued"], stats["curriculum_label"])

        if best_resolution is None:
            stats["still_no_match"] += 1
            continue

        # Same commit path as main resolver, but via fake_resolution_row for audit.
        if best_resolution.status in ("resolved", "kb_hit"):
            chosen = best_resolution.chosen_qid
            chosen_cand = next(
                (c for c in best_resolution.candidates if c.qid == chosen), None
            )

            # Dedup guard.
            existing = conn.execute(
                "SELECT entity_id FROM shared_entities "
                "WHERE wikidata_qid = ? AND entity_id != ?",
                (chosen, entity_id),
            ).fetchone()
            if existing:
                log.warning("  %s: rescue found %s (owned by %s) → dedup",
                            entity_id, chosen, existing["entity_id"])
                if not dry_run:
                    _rescue_write_row(
                        conn, entity_id, mention, r, best_resolution,
                        status="needs_review",
                        reasoning=(f"Rescue via alt-query '{alternates[0]}' found "
                                   f"{chosen}, but {existing['entity_id']} owns it. "
                                   f"{best_resolution.reasoning}"),
                    )
                    conn.commit()
                stats["ambiguous_queued"] += 1
                continue

            if dry_run:
                log.info("  DRY %s → %s via '%s'", entity_id, chosen, alternates[0])
            else:
                _rescue_write_row(
                    conn, entity_id, mention, r, best_resolution,
                    status="resolved",
                    reasoning=(f"Rescue via alt-query '{alternates[0]}'. "
                               f"{best_resolution.reasoning}"),
                )
                conn.execute(
                    "UPDATE shared_entities SET wikidata_qid = ? WHERE entity_id = ?",
                    (chosen, entity_id),
                )
                if chosen_cand is not None:
                    _commit_external_ids(conn, entity_id, chosen_cand.external_ids)
                conn.commit()
            stats["rescued"] += 1
        else:
            stats["ambiguous_queued"] += 1

    log.info("no-match rescue done: %s", stats)
    return stats


def _rescue_write_row(
    conn: sqlite3.Connection,
    entity_id: str,
    mention: str,
    source_row: sqlite3.Row,
    resolution,
    *,
    status: str,
    reasoning: str,
) -> str:
    """Write a rescue-generated resolution row, superseding prior no_match."""
    rid = f"er_{uuid.uuid4().hex[:12]}"
    # Serialize candidates for audit.
    cand_payload = [
        {
            "qid": c.qid, "label": c.label, "description": c.description,
            "total": c.total, "scores": c.scores, "rank": c.rank,
            "dates": ({"start": c.dates.start, "end": c.dates.end}
                      if c.dates is not None else None),
            "external_ids": c.external_ids, "aliases": c.aliases[:8],
        } for c in resolution.candidates[:10]
    ]
    conn.execute(
        "UPDATE entity_resolutions SET superseded_by = ? "
        "WHERE entity_id = ? AND superseded_by IS NULL",
        (rid, entity_id),
    )
    conn.execute(
        """
        INSERT INTO entity_resolutions (
            id, entity_id, capture_id, mention_text, context_excerpt,
            type_hint, date_hint_start, date_hint_end, candidate_qids,
            chosen_qid, confidence, status, resolver_model, reasoning,
            cost_usd, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rid, entity_id, "backfill:rescue", mention,
            source_row["context_excerpt"], source_row["type_hint"],
            source_row["date_hint_start"], source_row["date_hint_end"],
            json.dumps(cand_payload),
            resolution.chosen_qid, resolution.confidence, status,
            "rescue-gemini+deterministic",
            reasoning, 0.0, _now(),
        ),
    )
    return rid


def fake_resolution_row(
    conn: sqlite3.Connection,
    entity_id: str,
    mention: str,
    source_row: sqlite3.Row,
    chosen_qid: str,
    *,
    status: str,
    confidence: float,
    reasoning: str,
) -> str:
    """Write an entity_resolutions row for an LLM-decided pick, superseding prior."""
    rid = f"er_{uuid.uuid4().hex[:12]}"
    conn.execute(
        "UPDATE entity_resolutions SET superseded_by = ? "
        "WHERE entity_id = ? AND superseded_by IS NULL",
        (rid, entity_id),
    )
    conn.execute(
        """
        INSERT INTO entity_resolutions (
            id, entity_id, capture_id, mention_text, context_excerpt,
            type_hint, date_hint_start, date_hint_end, candidate_qids,
            chosen_qid, confidence, status, resolver_model, reasoning,
            cost_usd, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rid, entity_id, "backfill:llm", mention,
            source_row["context_excerpt"], source_row["type_hint"],
            source_row["date_hint_start"], source_row["date_hint_end"],
            source_row["candidate_qids"],  # reuse same candidate payload
            chosen_qid, confidence, status, "gemini-2.5-flash",
            reasoning, 0.0, _now(),
        ),
    )
    return rid


def run_pass(
    conn: sqlite3.Connection,
    pass_num: int,
    state_path: Path,
    *,
    embedder: EmbeddingModel,
    limit: int | None,
    max_cost: float | None,
    dry_run: bool,
    batch_size: int,
) -> dict[str, int]:
    """Run a single pass. Returns counts by status."""
    client = WikidataClient(
        user_agent=USER_AGENT,
        cache_db_path=str(state_path.parent / "wikidata_cache.db"),
    )

    if pass_num == 1:
        kb_lookup = None
        anchors: dict[str, str] = {}
        capture_prefix = "backfill:pass1"
    else:
        kb_lookup = _build_kb_lookup(conn)
        anchors = _already_resolved_map(conn)
        log.info("pass 2: %d anchor entities from pass 1", len(anchors))
        capture_prefix = "backfill:pass2"

    resolver = WikidataResolver(
        client=client,
        embedder=embedder,
        existing_kb_lookup=kb_lookup,
    )

    entities = _load_entities(conn, limit=limit)
    if pass_num == 2:
        # Pass 2 only touches items that pass 1 left as needs_review. Reuse the
        # same StateStore: get_pending returns items NOT in {done, verified,
        # applied, skipped}, which means needs_review items come back through.
        pass

    log.info("pass %d: %d entities pending", pass_num, len(entities))

    def process_batch(batch: list[dict[str, Any]]) -> list[ItemResult]:
        results: list[ItemResult] = []
        batch_id = uuid.uuid4().hex[:8]
        capture_id = f"{capture_prefix}:{batch_id}"
        for ent in batch:
            try:
                resolution = resolver.resolve(
                    ent["name"],
                    context_text=ent["context_text"],
                    type_hint=ent["type_hint"],
                    date_hint=ent["date_hint"],
                    already_resolved=anchors if pass_num == 2 else None,
                )
            except Exception as e:  # pragma: no cover - defensive
                log.exception("resolve failed for %s", ent["id"])
                results.append(
                    ItemResult(
                        id=ent["id"],
                        status="error",
                        cost=0.0,
                        metadata={"error": str(e)[:200]},
                    )
                )
                continue

            status = _apply_resolution(
                conn, ent, resolution,
                capture_id=capture_id, resolver_model="deterministic-0.1",
                dry_run=dry_run,
            )
            results.append(
                ItemResult(
                    id=ent["id"],
                    status=status,
                    cost=0.0,  # deterministic resolver uses $0 — only LLM disambig would cost
                    metadata={
                        "qid": resolution.chosen_qid or "",
                        "resolver_status": resolution.status,
                        "confidence": round(resolution.confidence, 3),
                    },
                )
            )
        return results

    store = StateStore(state_path)
    proc = BatchProcessor(store, max_cost=max_cost, batch_size=batch_size)
    result = proc.process(entities, process_batch, id_fn=lambda e: e["id"])
    log.info(
        "pass %d complete: processed=%d skipped=%d errors=%d cost=$%.2f",
        pass_num, result.processed, result.skipped, result.errors, result.total_cost,
    )
    return store.get_status_counts()


def dedup_report(conn: sqlite3.Connection) -> list[tuple[str, list[str]]]:
    """Return [(qid, [canonical_entity_id, duplicate_entity_id, ...]), ...].

    Live DB `shared_entities.wikidata_qid` is UNIQUE (idx_shared_entities_qid)
    so the canonical owner is in `shared_entities`. Duplicates show up in
    `entity_resolutions` as needs_review rows with `chosen_qid` set to a QID
    another entity already owns. We list both sides.
    """
    rows = conn.execute(
        """
        SELECT er.chosen_qid,
               se.entity_id AS canonical,
               GROUP_CONCAT(DISTINCT er.entity_id) AS duplicates
        FROM entity_resolutions er
        JOIN shared_entities se ON se.wikidata_qid = er.chosen_qid
        WHERE er.status = 'needs_review'
          AND er.superseded_by IS NULL
          AND er.entity_id IS NOT NULL
          AND er.entity_id != se.entity_id
          AND er.chosen_qid IS NOT NULL
        GROUP BY er.chosen_qid, se.entity_id
        """
    ).fetchall()
    return [
        (r["chosen_qid"], [r["canonical"]] + (r["duplicates"] or "").split(","))
        for r in rows
    ]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "db_path",
        type=Path,
        nargs="?",
        default=Path("/opt/petrarca/data/petrarca.db"),
    )
    p.add_argument("--max-cost", type=float, default=None, help="Budget cap in USD (default: unlimited)")
    p.add_argument("--limit", type=int, default=None, help="Limit number of entities processed")
    p.add_argument(
        "--pass", dest="which_pass",
        choices=("1", "2", "llm", "rescue", "both", "all"), default="both",
        help=("1/2 = deterministic passes, llm = LLM disambiguation for ambiguous, "
              "rescue = LLM alt-query retry for no_match, both = 1+2, all = 1+2+llm+rescue"),
    )
    p.add_argument(
        "--llm-top-k", type=int, default=5,
        help="How many top candidates to show the LLM (default 5)",
    )
    p.add_argument(
        "--llm-min-confidence", type=float, default=0.5,
        help="Minimum LLM-reported confidence to commit (default 0.5)",
    )
    p.add_argument(
        "--state",
        type=Path,
        default=None,
        help="BatchProcessor state DB (default: DB_PATH's parent / wikidata_backfill_state.db)",
    )
    p.add_argument(
        "--cache",
        type=Path,
        default=None,
        help="Embedding cache DB (default: DB_PATH's parent / wikidata_embed_cache.db)",
    )
    p.add_argument("--batch-size", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.db_path.exists():
        log.error("DB not found: %s", args.db_path)
        sys.exit(2)

    state_path = args.state or args.db_path.parent / "wikidata_backfill_state.db"
    cache_path = args.cache or args.db_path.parent / "wikidata_embed_cache.db"

    # Main DB — WAL + timeout per project SQLite discipline.
    conn = sqlite3.connect(str(args.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")

    embedder = EmbeddingModel(cache_path=str(cache_path))

    log.info("backfill starting: db=%s state=%s cache=%s", args.db_path, state_path, cache_path)

    if args.which_pass in ("1", "both", "all"):
        counts = run_pass(
            conn, 1, state_path,
            embedder=embedder, limit=args.limit, max_cost=args.max_cost,
            dry_run=args.dry_run, batch_size=args.batch_size,
        )
        log.info("post-pass-1 state counts: %s", counts)

    if args.which_pass in ("2", "both", "all"):
        counts = run_pass(
            conn, 2, state_path,
            embedder=embedder, limit=args.limit, max_cost=args.max_cost,
            dry_run=args.dry_run, batch_size=args.batch_size,
        )
        log.info("post-pass-2 state counts: %s", counts)

    if args.which_pass in ("llm", "all"):
        run_llm_disambiguation(
            conn,
            limit=args.limit,
            dry_run=args.dry_run,
            top_k=args.llm_top_k,
            min_confidence=args.llm_min_confidence,
        )

    if args.which_pass in ("rescue", "all"):
        run_no_match_rescue(
            conn,
            limit=args.limit,
            dry_run=args.dry_run,
            top_k=args.llm_top_k,
            min_confidence=args.llm_min_confidence,
        )

    # Dedup report.
    dupes = dedup_report(conn)
    if dupes:
        log.warning("=== %d dedup candidates ===", len(dupes))
        for qid, eids in dupes:
            log.warning("  %s ← %s", qid, ", ".join(eids))
    else:
        log.info("no dedup candidates found")

    # Coverage report.
    total = conn.execute("SELECT COUNT(*) FROM shared_entities").fetchone()[0]
    resolved = conn.execute(
        "SELECT COUNT(*) FROM shared_entities WHERE wikidata_qid IS NOT NULL"
    ).fetchone()[0]
    needs_review = conn.execute(
        "SELECT COUNT(DISTINCT entity_id) FROM entity_resolutions "
        "WHERE status IN ('ambiguous', 'no_match', 'needs_review') "
        "  AND entity_id IS NOT NULL AND superseded_by IS NULL"
    ).fetchone()[0]
    log.info(
        "coverage: %d/%d resolved (%.1f%%), %d in review queue",
        resolved, total, (100 * resolved / total) if total else 0, needs_review,
    )

    conn.close()


if __name__ == "__main__":
    main()
